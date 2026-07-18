'use strict';

function emit(kind, data) {
  send({ kind: kind, data: data });
}

function native(name, returnType, argumentTypes) {
  const address = Module.findGlobalExportByName(name);
  return address === null ? null : new NativeFunction(address, returnType, argumentTypes);
}

function hex(address, length) {
  if (address === null || address.isNull() || length <= 0) return null;
  const bytes = new Uint8Array(address.readByteArray(length));
  return Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('');
}

function location(address) {
  const module = Process.findModuleByAddress(address);
  if (module === null) return address.toString();
  return module.name + '+0x' + address.sub(module.base).toString(16);
}

const objcGetClass = native('objc_getClass', 'pointer', ['pointer']);
const selRegisterName = native('sel_registerName', 'pointer', ['pointer']);
const classGetClassMethod = native('class_getClassMethod', 'pointer', ['pointer', 'pointer']);
const methodGetImplementation = native('method_getImplementation', 'pointer', ['pointer']);
const objcMsgSend0 = native('objc_msgSend', 'pointer', ['pointer', 'pointer']);
const objcMsgSendLength = native('objc_msgSend', 'ulong', ['pointer', 'pointer']);
const cfStringGetCStringPtr = native('CFStringGetCStringPtr', 'pointer', ['pointer', 'uint32']);
const cfStringGetCString = native('CFStringGetCString', 'bool', ['pointer', 'pointer', 'long', 'uint32']);
const UTF8_ENCODING = 0x08000100;

function cString(value) {
  return Memory.allocUtf8String(value);
}

function selector(value) {
  return selRegisterName(cString(value));
}

function cfString(value, limit) {
  if (value === null || value.isNull()) return null;
  const max = limit || 4096;
  try {
    const direct = cfStringGetCStringPtr(value, UTF8_ENCODING);
    if (!direct.isNull()) return direct.readUtf8String(max);
    const buffer = Memory.alloc(max + 1);
    if (cfStringGetCString(value, buffer, max + 1, UTF8_ENCODING)) {
      return buffer.readUtf8String(max);
    }
  } catch (_) {}
  return null;
}

function objectDescription(value, limit) {
  if (value === null || value.isNull()) return null;
  try { return cfString(objcMsgSend0(value, selector('description')), limit); }
  catch (_) { return null; }
}

function objectLength(value) {
  if (value === null || value.isNull()) return null;
  try { return Number(objcMsgSendLength(value, selector('length'))); }
  catch (_) { return null; }
}

function attach(address, name, callbacks) {
  if (address === null) return;
  Interceptor.attach(address, callbacks);
  emit('hook', { name: name, address: address.toString(), location: location(address) });
}

function methodImplementation(className, methodName) {
  const cls = objcGetClass(cString(className));
  if (cls.isNull()) return null;
  const method = classGetClassMethod(cls, selector(methodName));
  return method.isNull() ? null : methodGetImplementation(method);
}

function hookFoundationJson() {
  const address = methodImplementation('NSJSONSerialization', 'JSONObjectWithData:options:error:');
  attach(address, 'NSJSONSerialization +JSONObjectWithData:options:error:', {
    onEnter(args) {
      this.data = args[2];
      this.length = objectLength(this.data);
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      if (this.length !== null && this.length >= 1000) {
        emit('json-parse', {
          length: this.length,
          caller: location(this.caller),
          resultHead: objectDescription(retval, 2048)
        });
      }
    }
  });
}

function hookCommonCrypto() {
  const address = Module.findGlobalExportByName('CCCrypt');
  attach(address, 'CCCrypt', {
    onEnter(args) {
      this.operation = args[0].toInt32();
      this.algorithm = args[1].toInt32();
      this.options = args[2].toInt32();
      this.key = args[3];
      this.keyLength = Number(args[4]);
      this.input = args[6];
      this.inputLength = Number(args[7]);
      this.output = this.context.sp.readPointer();
      this.outputMoved = this.context.sp.add(Process.pointerSize * 2).readPointer();
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      if (this.inputLength < 256) return;
      const moved = retval.toInt32() === 0 ? Number(this.outputMoved.readU64()) : 0;
      const event = {
        operation: this.operation,
        algorithm: this.algorithm,
        options: this.options,
        keyHex: hex(this.key, Math.min(this.keyLength, 64)),
        inputLength: this.inputLength,
        status: retval.toInt32(),
        moved: moved,
        outputHeadHex: moved > 0 ? hex(this.output, Math.min(moved, 128)) : null,
        caller: location(this.caller)
      };
      if (this.operation === 1 && moved >= 256) {
        send({ kind: 'cccrypt-plaintext', data: event }, this.output.readByteArray(moved));
      } else {
        emit('cccrypt', event);
      }
    }
  });
}

function hookLoadedCrypto(module) {
  const rsa = module.findExportByName('RSA_private_decrypt');
  attach(rsa, 'RSA_private_decrypt', {
    onEnter(args) {
      this.inputLength = args[0].toInt32();
      this.input = args[1];
      this.output = args[2];
      this.padding = args[4].toInt32();
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      const length = retval.toInt32();
      emit('rsa-private-decrypt', {
        inputLength: this.inputLength,
        padding: this.padding,
        resultLength: length,
        resultHex: length > 0 ? hex(this.output, Math.min(length, 256)) : null,
        caller: location(this.caller)
      });
    }
  });

  for (const entry of [
    ['NSString AES method 0', 0x183560],
    ['NSString AES method 1', 0x183e84],
    ['NSData AES method 0', 0x1e99d8],
    ['NSData AES method 1', 0x1ea7c0],
    ['NSData dataWithBase64EncodedString', 0x1eb7e0],
    ['MemHooks getDecryptedFJMemory', 0x43c78]
  ]) {
    attach(module.base.add(entry[1]), entry[0], {
      onEnter(args) {
        this.receiver = args[0];
        this.argument = args[2];
        this.caller = this.returnAddress;
        emit('objc-crypto-enter', {
          name: entry[0],
          receiverLength: objectLength(this.receiver),
          receiverHead: objectDescription(this.receiver, 512),
          argumentLength: objectLength(this.argument),
          argumentHead: objectDescription(this.argument, 512),
          caller: location(this.caller)
        });
      },
      onLeave(retval) {
        emit('objc-crypto-leave', {
          name: entry[0],
          resultLength: objectLength(retval),
          resultHead: objectDescription(retval, 1024)
        });
      }
    });
  }
}

hookFoundationJson();
hookCommonCrypto();

setTimeout(function () {
  const dlopen = native('dlopen', 'pointer', ['pointer', 'int']);
  const ctw = dlopen(cString('/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib'), 2);
  emit('dlopen', { name: 'CTW.dylib', handle: ctw.toString() });
  const zero = dlopen(cString('/var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib'), 2);
  emit('dlopen', { name: '0CTW.dylib', handle: zero.toString() });
  const module = Process.findModuleByName('0CTW.dylib');
  if (module !== null) hookLoadedCrypto(module);
}, 1200);

setTimeout(function () { emit('complete', {}); }, 12000);
