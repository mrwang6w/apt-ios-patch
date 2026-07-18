'use strict';

const injectedResponse = __INJECTED_RESPONSE__;
const forcedAesKeyHex = __FORCED_AES_KEY__;
const forcedCipherLength = __FORCED_CIPHER_LENGTH__;
const targetUrlPattern = new RegExp(__TARGET_URL_PATTERN__);
const shouldInvokeRandom = __INVOKE_RANDOM__;
const spoofEpochMs = __SPOOF_EPOCH_MS__;
const forceParseState = __FORCE_PARSE_STATE__;
const pendingInnerParseThreads = new Set();

send({
  kind: 'initial-modules',
  data: Process.enumerateModules()
    .filter(module => /ctw|fix/i.test(module.name))
    .map(module => ({ name: module.name, path: module.path }))
});

function emit(kind, data, bytes) {
  send({ kind: kind, data: data }, bytes);
}

function native(name, returnType, argumentTypes) {
  const address = Module.findGlobalExportByName(name);
  if (address === null) return null;
  return new NativeFunction(address, returnType, argumentTypes);
}

function cString(value) { return Memory.allocUtf8String(value); }

const objcGetClass = native('objc_getClass', 'pointer', ['pointer']);
const selRegisterName = native('sel_registerName', 'pointer', ['pointer']);
const classGetClassMethod = native('class_getClassMethod', 'pointer', ['pointer', 'pointer']);
const classGetInstanceMethod = native('class_getInstanceMethod', 'pointer', ['pointer', 'pointer']);
const methodGetImplementation = native('method_getImplementation', 'pointer', ['pointer']);
const objcMsgSend0 = native('objc_msgSend', 'pointer', ['pointer', 'pointer']);
const objcMsgSend1 = native('objc_msgSend', 'pointer', ['pointer', 'pointer', 'pointer']);
const objcMsgSend2 = native('objc_msgSend', 'pointer', ['pointer', 'pointer', 'pointer', 'ulong']);
const objcMsgSendObject = native(
  'objc_msgSend',
  'pointer',
  ['pointer', 'pointer', 'pointer']
);
const objcMsgSend4 = native(
  'objc_msgSend',
  'pointer',
  ['pointer', 'pointer', 'pointer', 'long', 'pointer', 'pointer']
);
const objcMsgSendLength = native('objc_msgSend', 'ulong', ['pointer', 'pointer']);
const objcMsgSendBool = native('objc_msgSend', 'bool', ['pointer', 'pointer']);
const objcMsgSendDouble = native('objc_msgSend', 'pointer', ['pointer', 'pointer', 'double']);

function selector(value) { return selRegisterName(cString(value)); }
function getClass(value) { return objcGetClass(cString(value)); }

function location(address) {
  const module = Process.findModuleByAddress(address);
  if (module === null) return address.toString();
  return module.name + '+0x' + address.sub(module.base).toString(16);
}

function nativeBacktrace(context) {
  try {
    return Thread.backtrace(context, Backtracer.ACCURATE)
      .slice(0, 20)
      .map(location);
  } catch (_) {
    return [];
  }
}

function scanRuntimeSeeds() {
  const main = Process.mainModule;
  const lower = main.base;
  const upper = main.base.add(0x16d4000);
  let count = 0;
  for (const range of Process.enumerateRanges('rw-')) {
    if (range.base.compare(lower) < 0 || range.base.compare(upper) >= 0) continue;
    try {
      emit('runtime-range', {
        base: range.base.toString(),
        size: range.size,
        protection: range.protection
      }, range.base.readByteArray(range.size));
      count += 1;
    } catch (_) {
      continue;
    }
  }
  emit('runtime-range-complete', {
    mainBase: main.base.toString(),
    mainSize: main.size,
    rangeCount: count
  });
}

function hex(address, length) {
  if (address === null || address.isNull() || length <= 0) return null;
  return Array.from(new Uint8Array(address.readByteArray(length)), value =>
    value.toString(16).padStart(2, '0')
  ).join('');
}

function bytesFromHex(value) {
  if (value === null) return null;
  const output = Memory.alloc(value.length / 2);
  for (let index = 0; index < value.length; index += 2) {
    output.add(index / 2).writeU8(parseInt(value.slice(index, index + 2), 16));
  }
  return output;
}

function pointerSnapshot(value, length) {
  try {
    const range = Process.findRangeByAddress(value);
    if (range === null || range.protection.indexOf('r') === -1) return null;
    const size = Math.min(length, range.base.add(range.size).sub(value).toInt32());
    return size > 0 ? hex(value, size) : null;
  } catch (_) {
    return null;
  }
}

function objectLength(value) {
  try { return Number(objcMsgSendLength(value, selector('length'))); }
  catch (_) { return 0; }
}

function objectBytes(value) {
  try { return objcMsgSend0(value, selector('bytes')); }
  catch (_) { return ptr('0'); }
}

function isMainCaller(address) {
  const module = Process.findModuleByAddress(address);
  return module !== null && module.name === Process.mainModule.name;
}

function methodImplementation(className, methodName, isClassMethod) {
  const cls = getClass(className);
  if (cls === null || cls.isNull()) return null;
  const method = (isClassMethod ? classGetClassMethod : classGetInstanceMethod)(
    cls,
    selector(methodName)
  );
  return method.isNull() ? null : methodGetImplementation(method);
}

function makeData(text) {
  const bytes = cString(text);
  return objcMsgSend2(
    getClass('NSData'),
    selector('dataWithBytes:length:'),
    bytes,
    text.length
  );
}

function makeSuccessResponse(originalResponse, explicitUrl) {
  let url = explicitUrl || ptr('0');
  if (url.isNull()) {
    try { url = objcMsgSend0(originalResponse, selector('URL')); }
    catch (_) {}
  }
  const version = objcMsgSend1(
    getClass('NSString'),
    selector('stringWithUTF8String:'),
    cString('HTTP/1.1')
  );
  const allocated = objcMsgSend0(getClass('NSHTTPURLResponse'), selector('alloc'));
  return objcMsgSend4(
    allocated,
    selector('initWithURL:statusCode:HTTPVersion:headerFields:'),
    url,
    200,
    version,
    ptr('0')
  );
}

function hookJson() {
  const address = methodImplementation(
    'NSJSONSerialization',
    'JSONObjectWithData:options:error:',
    true
  );
  if (address === null) return;
  Interceptor.attach(address, {
    onEnter(args) {
      this.data = args[2];
      this.length = objectLength(this.data);
      this.caller = this.returnAddress;
    },
    onLeave(_) {
      if (this.length < 256 || this.length > 16 * 1024 * 1024) return;
      const bytes = objcMsgSend0(this.data, selector('bytes'));
      emit('json-input', {
        length: this.length,
        caller: location(this.caller),
        headHex: hex(bytes, Math.min(this.length, 64))
      }, bytes.readByteArray(this.length));
    }
  });
  emit('hook', { name: 'NSJSONSerialization', location: location(address) });
}

const trackedJsonKeys = new Set([
  '6076a46b', '2b8ce2af', 'd81e6868', '438c96bb', 'dbf37831',
  '1f352e32', 'f91138fe', '1e244b84', 'd65a2f9f'
]);

function objectString(value) {
  if (value === null || value.isNull()) return null;
  try {
    const description = objcMsgSend0(value, selector('description'));
    const utf8 = objcMsgSend0(description, selector('UTF8String'));
    return utf8.isNull() ? null : utf8.readCString();
  } catch (_) {
    return null;
  }
}

function hookDictionaryLookups() {
  const hooked = new Set();
  for (const className of ['NSDictionary', '__NSDictionaryI', '__NSDictionaryM']) {
    for (const methodName of ['objectForKeyedSubscript:', 'objectForKey:']) {
      const address = methodImplementation(className, methodName, false);
      if (address === null || hooked.has(address.toString())) continue;
      hooked.add(address.toString());
      Interceptor.attach(address, {
        onEnter(args) {
          this.key = objectString(args[2]);
          this.caller = this.returnAddress;
        },
        onLeave(retval) {
          if (!trackedJsonKeys.has(this.key)) return;
          const value = objectString(retval);
          emit('json-key-read', {
            key: this.key,
            caller: location(this.caller),
            valueLength: value === null ? null : value.length,
            valueHead: value === null ? null : value.slice(0, 96)
          });
        }
      });
      emit('hook', {
        name: className + ' ' + methodName,
        location: location(address)
      });
    }
  }
}

function hookResponseTime() {
  if (spoofEpochMs === null) return;
  const address = methodImplementation('NSDate', 'date', true);
  if (address === null) return;
  const fixedDate = objcMsgSendDouble(
    getClass('NSDate'),
    selector('dateWithTimeIntervalSince1970:'),
    spoofEpochMs / 1000.0
  );
  Interceptor.attach(address, {
    onEnter(_) {
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      if (!isMainCaller(this.caller)) return;
      retval.replace(fixedDate);
      emit('date-spoofed', {
        epochMs: spoofEpochMs,
        caller: location(this.caller)
      });
    }
  });
  emit('hook', { name: 'NSDate date time spoof', location: location(address) });
}

function hookInflate() {
  const init = Module.findGlobalExportByName('inflateInit2_');
  const update = Module.findGlobalExportByName('inflate');
  if (init === null || update === null) return;
  const streams = new Map();
  Interceptor.attach(init, {
    onEnter(args) {
      this.stream = args[0];
      this.windowBits = args[1].toInt32();
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      streams.set(this.stream.toString(), {
        windowBits: this.windowBits,
        initCaller: location(this.caller)
      });
      emit('inflate-init', {
        windowBits: this.windowBits,
        caller: location(this.caller),
        status: retval.toInt32()
      });
    }
  });
  Interceptor.attach(update, {
    onEnter(args) {
      this.stream = args[0];
      this.caller = this.returnAddress;
      this.output = this.stream.add(Process.pointerSize * 3).readPointer();
      this.before = Number(this.stream.add(Process.pointerSize * 5).readU64());
    },
    onLeave(retval) {
      const after = Number(this.stream.add(Process.pointerSize * 5).readU64());
      const produced = after - this.before;
      const state = streams.get(this.stream.toString()) || {};
      if (produced <= 0 || produced > 16 * 1024 * 1024) return;
      emit('inflate-output', {
        outputLength: produced,
        windowBits: state.windowBits || null,
        initCaller: state.initCaller || null,
        caller: location(this.caller),
        status: retval.toInt32()
      }, this.output.readByteArray(produced));
    }
  });
  emit('hook', { name: 'inflate', location: location(update) });
}

function hookCCCrypt() {
  const address = Module.findGlobalExportByName('CCCrypt');
  if (address === null) return;
  const forcedAesKey = bytesFromHex(forcedAesKeyHex);
  Interceptor.attach(address, {
    onEnter(args) {
      this.operation = args[0].toInt32();
      this.algorithm = args[1].toInt32();
      this.options = args[2].toInt32();
      this.key = args[3];
      this.keyLength = Number(args[4]);
      this.inputLength = Number(args[7]);
      this.input = args[6];
      this.originalKeyHex = hex(this.key, Math.min(this.keyLength, 64));
      this.forced = false;
      if (forcedAesKey !== null && this.operation === 1 &&
          this.keyLength === 16 && this.inputLength === forcedCipherLength) {
        args[3] = forcedAesKey;
        this.key = forcedAesKey;
        this.forced = true;
      }
      this.keyHex = hex(this.key, Math.min(this.keyLength, 64));
      if (this.keyHex === '4354575f5549434f4e4649475f4b4559' && this.inputLength >= 256) {
        emit('cccrypt-input', {
          inputLength: this.inputLength,
          keyHex: this.keyHex,
          caller: location(this.returnAddress)
        }, this.input.readByteArray(this.inputLength));
      }
      this.output = this.context.sp.readPointer();
      this.outputMoved = this.context.sp.add(Process.pointerSize * 2).readPointer();
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      if (this.operation !== 1 || this.inputLength < 256) return;
      const moved = retval.toInt32() === 0 ? Number(this.outputMoved.readU64()) : 0;
      const event = {
        operation: this.operation,
        algorithm: this.algorithm,
        options: this.options,
        keyHex: this.keyHex,
        originalKeyHex: this.originalKeyHex,
        forced: this.forced,
        inputLength: this.inputLength,
        moved: moved,
        status: retval.toInt32(),
        caller: location(this.caller)
      };
      emit(
        'cccrypt-decrypt',
        event,
        moved > 0 ? this.output.readByteArray(moved) : undefined
      );
    }
  });
  emit('hook', { name: 'CCCrypt', location: location(address) });
}

function emitRelevantObjcMethods() {
  if (typeof ObjC === 'undefined' || !ObjC.available) return;
  const main = Process.mainModule;
  const lower = main.base.add(0x990000);
  const upper = main.base.add(0x9a2000);
  const matches = [];
  for (const className of Object.keys(ObjC.classes)) {
    const cls = ObjC.classes[className];
    for (const methodName of cls.$ownMethods) {
      try {
        const implementation = cls[methodName].implementation;
        if (implementation.compare(lower) >= 0 && implementation.compare(upper) < 0) {
          matches.push({
            className: className,
            methodName: methodName,
            location: location(implementation)
          });
        }
      } catch (_) {}
    }
  }
  emit('objc-method-map', matches);
}

function hookMainCrypto() {
  const main = Process.mainModule;
  for (const [name, address] of [
    ['memcmp', Module.findGlobalExportByName('memcmp')],
    ['CRYPTO_memcmp', main.base.add(0xa299c0)]
  ]) {
    if (address === null) continue;
    Interceptor.attach(address, {
      onEnter(args) {
        this.caller = this.returnAddress;
        this.length = Number(args[2]);
        this.left = args[0];
        this.right = args[1];
      },
      onLeave(retval) {
        if (!isMainCaller(this.caller) || this.length < 4 || this.length > 256) return;
        const offset = this.caller.sub(main.base).toUInt32();
        if (offset < 0x940000 || offset >= 0x9b0000) return;
        emit('validation-compare', {
          function: name,
          length: this.length,
          caller: location(this.caller),
          result: retval.toInt32(),
          leftHex: hex(this.left, this.length),
          rightHex: hex(this.right, this.length)
        });
      }
    });
    emit('hook', { name: name + ' validation compare', location: location(address) });
  }
  for (const offset of [0x953624, 0x9576cc]) {
    const address = main.base.add(offset);
    Interceptor.attach(address, {
      onEnter(_) {
        this.caller = this.returnAddress;
        this.x0 = this.context.x0;
        this.x1 = this.context.x1;
      },
      onLeave(retval) {
        emit('validation-helper-return', {
          helper: '0x' + offset.toString(16),
          caller: location(this.caller),
          inputX0: this.x0.toString(),
          inputX1: this.x1.toString(),
          retval: retval.toString(),
          retvalU32: retval.toUInt32()
        });
      }
    });
    emit('hook', { name: 'validation helper 0x' + offset.toString(16), location: location(address) });
  }
  for (const offset of [0x9505ec, 0x1d42b0]) {
    const address = main.base.add(offset);
    Interceptor.attach(address, {
      onEnter(_) {
        if (!isMainCaller(this.returnAddress)) return;
        emit('cpp-json-helper', {
          helper: '0x' + offset.toString(16),
          caller: location(this.returnAddress),
          x0: this.context.x0.toString(),
          x1: this.context.x1.toString(),
          x2: this.context.x2.toString(),
          x0Hex: pointerSnapshot(this.context.x0, 64),
          x1Hex: pointerSnapshot(this.context.x1, 64),
          x2Hex: pointerSnapshot(this.context.x2, 64)
        });
      }
    });
    emit('hook', { name: 'C++ JSON helper 0x' + offset.toString(16), location: location(address) });
  }
  for (const offset of [0x955520, 0x955a2c, 0x953864, 0x957890, 0x9578e4]) {
    const address = main.base.add(offset);
    Interceptor.attach(address, {
      onEnter(_) {
        const originalX0 = this.context.x0.toUInt32();
        const threadId = Process.getCurrentThreadId();
        const isInnerParse = offset === 0x955520 && pendingInnerParseThreads.has(threadId);
        if (isInnerParse && forceParseState !== null) {
          this.context.x0 = ptr(forceParseState);
        }
        if (isInnerParse) pendingInnerParseThreads.delete(threadId);
        let switchTarget = null;
        if (offset === 0x955520) {
          try {
            switchTarget = location(
              main.base.add(0x16a3738)
                .add(this.context.x0.toUInt32() * Process.pointerSize)
                .readPointer()
            );
          } catch (_) {}
        }
        emit('main-control-point', {
          point: '0x' + offset.toString(16),
          caller: location(this.returnAddress),
          x0: location(this.context.x0),
          x0u32: this.context.x0.toUInt32(),
          originalX0u32: originalX0,
          forcedParseState: forceParseState,
          isInnerParse: isInnerParse,
          switchTarget: switchTarget,
          x1: location(this.context.x1),
          x2: location(this.context.x2),
          x8: location(this.context.x8),
          lr: location(this.context.lr)
        });
      }
    });
    emit('hook', { name: 'main control point 0x' + offset.toString(16), location: location(address) });
  }
  const rsa = main.base.add(0x13f1784);
  Interceptor.attach(rsa, {
    onEnter(args) {
      this.inputLength = args[0].toInt32();
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
  emit('hook', { name: 'RSA_private_decrypt', location: location(rsa) });

  const rsaPublicEncrypt = main.base.add(0x13f13f4);
  Interceptor.attach(rsaPublicEncrypt, {
    onEnter(args) {
      const length = args[0].toInt32();
      emit('rsa-public-encrypt-input', {
        inputLength: length,
        padding: args[4].toInt32(),
        caller: location(this.returnAddress)
      }, length > 0 && length <= 4096 ? args[1].readByteArray(length) : undefined);
    }
  });
  emit('hook', { name: 'RSA_public_encrypt', location: location(rsaPublicEncrypt) });

  const setDecryptKey = main.base.add(0xa1701c);
  Interceptor.attach(setDecryptKey, {
    onEnter(args) {
      emit('aes-set-decrypt-key', {
        bits: args[1].toInt32(),
        keyHex: hex(args[0], Math.min(args[1].toInt32() / 8, 64)),
        caller: location(this.returnAddress)
      });
    }
  });
  emit('hook', { name: 'AES_set_decrypt_key', location: location(setDecryptKey) });

  const contexts = new Map();
  const decryptInit = main.base.add(0x11d00f8);
  Interceptor.attach(decryptInit, {
    onEnter(args) {
      const key = args[3];
      contexts.set(args[0].toString(), {
        keyHex: key.isNull() ? null : hex(key, 16),
        caller: location(this.returnAddress)
      });
    }
  });
  emit('hook', { name: 'EVP_DecryptInit_ex', location: location(decryptInit) });

  const decryptUpdate = main.base.add(0x11cf524);
  Interceptor.attach(decryptUpdate, {
    onEnter(args) {
      this.contextKey = args[0].toString();
      this.output = args[1];
      this.outputLength = args[2];
      this.input = args[3];
      this.inputLength = args[4].toInt32();
      this.caller = this.returnAddress;
      this.backtrace = this.inputLength >= 30000 ? nativeBacktrace(this.context) : [];
    },
    onLeave(retval) {
      if (this.inputLength < 256 || !isMainCaller(this.caller)) return;
      const outputLength = retval.toInt32() === 1 ? this.outputLength.readS32() : 0;
      const state = contexts.get(this.contextKey) || {};
      if (this.inputLength === 37856 && retval.toInt32() === 1) {
        pendingInnerParseThreads.add(Process.getCurrentThreadId());
      }
      if (outputLength > 0) {
        state.output = this.output;
        state.outputLength = outputLength;
        contexts.set(this.contextKey, state);
      }
      emit('evp-decrypt-update', {
        inputLength: this.inputLength,
        outputLength: outputLength,
        keyHex: state.keyHex || null,
        initCaller: state.caller || null,
        caller: location(this.caller),
        backtrace: this.backtrace,
        status: retval.toInt32()
      }, outputLength > 0 ? this.output.readByteArray(outputLength) : undefined);
    }
  });
  emit('hook', { name: 'EVP_DecryptUpdate', location: location(decryptUpdate) });

  const decryptFinal = main.base.add(0x11cfdc4);
  Interceptor.attach(decryptFinal, {
    onEnter(args) {
      this.contextKey = args[0].toString();
      this.output = args[1];
      this.outputLength = args[2];
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      if (!isMainCaller(this.caller)) return;
      const outputLength = retval.toInt32() === 1 ? this.outputLength.readS32() : 0;
      const state = contexts.get(this.contextKey) || {};
      if (state.output !== undefined && state.outputLength !== undefined) {
        const totalLength = state.outputLength + outputLength;
        try {
          const plaintext = state.output.readUtf8String(totalLength);
          const match = /("d65a2f9f"\s*:\s*)\d{13}/.exec(plaintext);
          if (match !== null && spoofEpochMs === null) {
            const replacement = String(Date.now());
            const offset = match.index + match[1].length;
            Memory.copy(
              state.output.add(offset),
              Memory.allocUtf8String(replacement),
              replacement.length
            );
            emit('timestamp-patched', {
              original: match[0].slice(match[1].length),
              replacement: replacement,
              offset: offset,
              totalLength: totalLength,
              keyHex: state.keyHex || null
            });
          }
        } catch (_) {}
      }
      emit('evp-decrypt-final', {
        outputLength: outputLength,
        keyHex: state.keyHex || null,
        caller: location(this.caller),
        status: retval.toInt32()
      }, outputLength > 0 ? this.output.readByteArray(outputLength) : undefined);
      contexts.delete(this.contextKey);
    }
  });
  emit('hook', { name: 'EVP_DecryptFinal_ex', location: location(decryptFinal) });

  const encryptContexts = new Map();
  const encryptInit = main.base.add(0x11cffbc);
  Interceptor.attach(encryptInit, {
    onEnter(args) {
      const key = args[3];
      encryptContexts.set(args[0].toString(), {
        keyHex: key.isNull() ? null : hex(key, 16),
        caller: location(this.returnAddress)
      });
    }
  });
  emit('hook', { name: 'EVP_EncryptInit_ex', location: location(encryptInit) });

  const encryptUpdate = main.base.add(0x11ceeb0);
  Interceptor.attach(encryptUpdate, {
    onEnter(args) {
      this.contextKey = args[0].toString();
      this.input = args[3];
      this.inputLength = args[4].toInt32();
      this.caller = this.returnAddress;
      const state = encryptContexts.get(this.contextKey) || {};
      if (this.inputLength >= 16 && isMainCaller(this.caller)) {
        emit('evp-encrypt-input', {
          inputLength: this.inputLength,
          keyHex: state.keyHex || null,
          initCaller: state.caller || null,
          caller: location(this.caller),
          backtrace: nativeBacktrace(this.context)
        }, this.input.readByteArray(this.inputLength));
      }
    }
  });
  emit('hook', { name: 'EVP_EncryptUpdate', location: location(encryptUpdate) });

  const encryptFinal = main.base.add(0x11cfc94);
  Interceptor.attach(encryptFinal, {
    onEnter(args) {
      this.contextKey = args[0].toString();
    },
    onLeave(_) {
      encryptContexts.delete(this.contextKey);
    }
  });
  emit('hook', { name: 'EVP_EncryptFinal_ex', location: location(encryptFinal) });
}

function hookDataTransform(className, methodName, isClassMethod, argumentIndex, kind) {
  const address = methodImplementation(className, methodName, isClassMethod);
  if (address === null) return;
  Interceptor.attach(address, {
    onEnter(args) {
      this.input = args[argumentIndex];
      this.inputLength = objectLength(this.input);
      this.caller = this.returnAddress;
    },
    onLeave(retval) {
      if (!isMainCaller(this.caller) || this.inputLength < 256) return;
      const outputLength = objectLength(retval);
      const output = objectBytes(retval);
      emit(kind, {
        method: className + ' ' + methodName,
        inputLength: this.inputLength,
        outputLength: outputLength,
        caller: location(this.caller)
      }, !output.isNull() && outputLength > 0
        ? output.readByteArray(outputLength)
        : undefined);
    }
  });
  emit('hook', { name: className + ' ' + methodName, location: location(address) });
}

function hookPostDecryptTransforms() {
  hookDataTransform('NSData', 'dataWithBase64EncodedString:options:', true, 2, 'base64-output');
  hookDataTransform('NSData', 'dataWithBase64EncodedData:options:', true, 2, 'base64-output');
  hookDataTransform('NSData', 'initWithBase64EncodedString:options:', false, 2, 'base64-output');
  hookDataTransform('NSData', 'initWithBase64EncodedData:options:', false, 2, 'base64-output');
  hookDataTransform('NSKeyedUnarchiver', 'unarchiveObjectWithData:', true, 2, 'unarchive-output');

  const writeAddress = methodImplementation('NSData', 'writeToFile:atomically:', false);
  if (writeAddress !== null) {
    Interceptor.attach(writeAddress, {
      onEnter(args) {
        this.data = args[0];
        this.length = objectLength(this.data);
        this.path = args[2];
        this.caller = this.returnAddress;
      },
      onLeave(retval) {
        if (!isMainCaller(this.caller) || this.length < 256) return;
        let path = null;
        try { path = objcMsgSend0(this.path, selector('UTF8String')).readCString(); }
        catch (_) {}
        const bytes = objectBytes(this.data);
        emit('data-write', {
          length: this.length,
          path: path,
          caller: location(this.caller),
          success: retval.toInt32() !== 0
        }, bytes.isNull() ? undefined : bytes.readByteArray(this.length));
      }
    });
    emit('hook', { name: 'NSData writeToFile:atomically:', location: location(writeAddress) });
  }
}

const hookedBlocks = new Set();
let injectionCount = 0;
let bootstrapCompleted = false;

function hookCompletion(block, requestUrl) {
  if (block.isNull()) return;
  const implementation = block.add(16).readPointer();
  const key = implementation.toString();
  if (hookedBlocks.has(key)) return;
  hookedBlocks.add(key);
  Interceptor.attach(implementation, {
    onEnter(args) {
      let status = null;
      try { status = Number(objcMsgSendLength(args[2], selector('statusCode'))); }
      catch (_) {}
      if (!targetUrlPattern.test(requestUrl || '')) return;
      args[1] = makeData(injectedResponse);
      args[2] = makeSuccessResponse(args[2]);
      args[3] = ptr('0');
      injectionCount += 1;
      emit('response-injected', {
        requestUrl: requestUrl,
        originalStatus: status,
        callback: location(implementation),
        length: injectedResponse.length,
        injectionCount: injectionCount
      });
    }
  });
  emit('completion-hook', { requestUrl: requestUrl, callback: location(implementation) });
}

function hookSession() {
  const address = methodImplementation(
    'NSURLSession',
    'dataTaskWithRequest:completionHandler:',
    false
  );
  if (address === null) return;
  Interceptor.attach(address, {
    onEnter(args) {
      let url = null;
      let urlObject = ptr('0');
      try {
        urlObject = objcMsgSend0(args[2], selector('URL'));
        const absolute = objcMsgSend0(urlObject, selector('absoluteString'));
        const utf8 = objcMsgSend0(absolute, selector('UTF8String'));
        url = utf8.isNull() ? null : utf8.readCString();
      } catch (_) {}
      hookCompletion(args[3], url);
      if (!bootstrapCompleted && /ctw\.amg456\.com\/ctw\.txt/.test(url || '')) {
        bootstrapCompleted = true;
        const block = args[3];
        const implementation = block.add(16).readPointer();
        const invoke = new NativeFunction(
          implementation,
          'void',
          ['pointer', 'pointer', 'pointer', 'pointer']
        );
        invoke(
          block,
          makeData('{}'),
          makeSuccessResponse(ptr('0'), urlObject),
          ptr('0')
        );
        emit('bootstrap-completion-invoked', {
          requestUrl: url,
          callback: location(implementation)
        });
      }
    }
  });
  emit('hook', { name: 'NSURLSession dataTaskWithRequest', location: location(address) });
}

function invokeRandomPreferences() {
  try {
    const cls = getClass('MachinePreferences');
    if (cls.isNull()) {
      emit('random-invoke-error', { error: 'MachinePreferences class is missing' });
      return;
    }
    const instance = objcMsgSend0(cls, selector('alloc'));
    const controller = objcMsgSend0(instance, selector('init'));
    emit('random-invoke', {
      class: cls.toString(),
      controller: controller.toString(),
      method: methodImplementation('MachinePreferences', 'randomPreferences:', false) === null
        ? null
        : location(methodImplementation('MachinePreferences', 'randomPreferences:', false))
    });
    objcMsgSendObject(controller, selector('randomPreferences:'), ptr('0'));
    emit('random-invoke-returned', {});
  } catch (error) {
    emit('random-invoke-error', { error: String(error), stack: error.stack });
  }
}

setTimeout(function () {
  hookJson();
  hookDictionaryLookups();
  hookResponseTime();
  hookCCCrypt();
  hookInflate();
  hookMainCrypto();
  hookPostDecryptTransforms();
  hookSession();
  emitRelevantObjcMethods();
  emit('ready', {});
}, 50);

if (shouldInvokeRandom) setTimeout(invokeRandomPreferences, 1200);
setTimeout(scanRuntimeSeeds, 5000);
