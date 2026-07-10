#!/usr/bin/env python3
"""Trace CTW Pro's runtime-registered donation/license flow on a USB device."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

import frida


BUNDLE_ID = "com.xxdevice.CTWPro"

JAVASCRIPT = r"""
'use strict';

const main = Process.mainModule;
const invokeRecharge = __INVOKE_RECHARGE__;
const submitCodeValue = __SUBMIT_CODE__;
const nullPointer = ptr('0');

function emit(kind, data) {
  send({ kind: kind, data: data });
}

function relevant(text) {
  if (text === null || text === undefined) return false;
  return /捐|赠|码|适配|网络|节点|授权|权限|测试|激活|试用|到期|过期|donat|license|active|expire|token|status|server|node/i.test(String(text));
}

function exportAddress(name) {
  try { return Module.getGlobalExportByName(name); } catch (_) { return null; }
}

function nativeFunction(name, returnType, argumentTypes) {
  const address = exportAddress(name);
  return address === null ? null : new NativeFunction(address, returnType, argumentTypes);
}

const classGetName = nativeFunction('class_getName', 'pointer', ['pointer']);
const selGetName = nativeFunction('sel_getName', 'pointer', ['pointer']);
const selRegisterName = nativeFunction('sel_registerName', 'pointer', ['pointer']);
const objcGetClass = nativeFunction('objc_getClass', 'pointer', ['pointer']);
const objectGetClass = nativeFunction('object_getClass', 'pointer', ['pointer']);
const classGetInstanceMethod = nativeFunction('class_getInstanceMethod', 'pointer', ['pointer', 'pointer']);
const classGetClassMethod = nativeFunction('class_getClassMethod', 'pointer', ['pointer', 'pointer']);
const methodGetImplementation = nativeFunction('method_getImplementation', 'pointer', ['pointer']);
const methodGetName = nativeFunction('method_getName', 'pointer', ['pointer']);
const cfStringGetCStringPtr = nativeFunction('CFStringGetCStringPtr', 'pointer', ['pointer', 'uint32']);
const cfStringGetCString = nativeFunction('CFStringGetCString', 'bool', ['pointer', 'pointer', 'long', 'uint32']);
const objcMsgSend0 = nativeFunction('objc_msgSend', 'pointer', ['pointer', 'pointer']);
const objcMsgSend1 = nativeFunction('objc_msgSend', 'void', ['pointer', 'pointer', 'pointer']);
const objcMsgSendPointer = nativeFunction('objc_msgSend', 'pointer', ['pointer', 'pointer', 'pointer']);
const objcMsgSendIndex = nativeFunction('objc_msgSend', 'pointer', ['pointer', 'pointer', 'long']);
const objcMsgSendAlertIndex = nativeFunction('objc_msgSend', 'void', ['pointer', 'pointer', 'pointer', 'long']);
const objcMsgSendLength = nativeFunction('objc_msgSend', 'ulong', ['pointer', 'pointer']);
const dispatchGetMainQueue = nativeFunction('dispatch_get_main_queue', 'pointer', []);
const dispatchAsyncF = nativeFunction('dispatch_async_f', 'void', ['pointer', 'pointer', 'pointer']);
const mainQueue = dispatchGetMainQueue === null ? exportAddress('_dispatch_main_q') : dispatchGetMainQueue();
const UTF8_ENCODING = 0x08000100;

function cString(value) {
  return Memory.allocUtf8String(value);
}

function selector(value) {
  return selRegisterName(cString(value));
}

function getClass(value) {
  return objcGetClass(cString(value));
}

function cfString(value) {
  if (value === null || value === undefined || value.isNull()) return null;
  try {
    const direct = cfStringGetCStringPtr(value, UTF8_ENCODING);
    if (!direct.isNull()) return direct.readCString();
    const buffer = Memory.alloc(8192);
    if (cfStringGetCString(value, buffer, 8192, UTF8_ENCODING)) return buffer.readCString();
  } catch (_) {}
  return null;
}

function className(cls) {
  try {
    return classGetName(cls).readCString();
  } catch (_) {
    return '<unknown>';
  }
}

function selectorName(sel) {
  try { return selGetName(sel).readCString(); } catch (_) { return '<unknown>'; }
}

function location(address) {
  const module = Process.findModuleByAddress(address);
  if (module === null) return address.toString();
  return module.name + '+0x' + address.sub(module.base).toString(16);
}

function objectDescription(value) {
  if (value === null || value === undefined || value.isNull()) return null;
  try { return cfString(objcMsgSend0(value, selector('description'))); } catch (_) { return null; }
}

const mainCallbacks = [];

function runOnMain(callback) {
  if (dispatchAsyncF === null || mainQueue === null) {
    emit('main-callback-error', {
      dispatchAsyncF: dispatchAsyncF === null ? null : dispatchAsyncF.toString(),
      mainQueue: mainQueue === null ? null : mainQueue.toString()
    });
    return;
  }
  const nativeCallback = new NativeCallback(function(_) {
    try { callback(); } catch (error) { emit('main-callback-error', String(error)); }
  }, 'void', ['pointer']);
  mainCallbacks.push(nativeCallback);
  dispatchAsyncF(mainQueue, nullPointer, nativeCallback);
}

function fromMain(context) {
  try { return main.contains(context.returnAddress); } catch (_) { return false; }
}

function hookNative(name, callbacks) {
  const address = exportAddress(name);
  if (address === null) return;
  Interceptor.attach(address, callbacks);
  emit('hook', name + '=' + address);
}

const hookedImplementations = new Set();
let autoEntryTriggered = false;
let autoSubmitTriggered = false;

function textFieldValue(alert) {
  try {
    const field = objcMsgSendIndex(alert, selector('textFieldAtIndex:'), 0);
    if (field.isNull()) return null;
    return cfString(objcMsgSend0(field, selector('text')));
  } catch (_) {
    return null;
  }
}

function hookBusinessImplementation(cls, sel, implementation, types) {
  const watched = new Set([
    'handleAppWillEnterForeground',
    'uploadCloudConfig',
    'recharge:',
    'alertView:clickedButtonAtIndex:',
    'showQRCodeView:',
    'scanQRCode:',
    'qrCodeScannerDidScanResult:',
    'JvgnSRHcrHmZxNJocXZHWQYSFjPrglVHvpybVYfpfuMZRgoCejVYdqxxTCjtzbfDwaNkQ',
    'viewDidLoad',
    'viewDidAppear:',
    'isInNetwork',
    'writeCTWCacheEnv',
    'performeMachineStub',
    'performeMachine:',
    'nativeMachine:',
    'lockUI:'
  ]);
  if (!watched.has(sel)) return;
  const key = implementation.toString();
  if (hookedImplementations.has(key)) return;
  hookedImplementations.add(key);
  try {
    Interceptor.attach(implementation, {
      onEnter(args) {
        this.selector = sel;
        if (cls === 'ViewController' && sel === 'viewDidLoad') {
          lastController = args[0];
        }
        const event = {
          className: cls,
          selector: sel,
          implementation: location(implementation),
          caller: location(this.returnAddress),
          arg2: args[2].toString(),
          arg3: args[3].toString(),
          types: types
        };
        if (/^(set|performeMachine:|nativeMachine:|lockUI:|qrCodeScannerDidScanResult:)/.test(sel) && /@16/.test(String(types))) {
          event.arg2Description = objectDescription(args[2]);
        }
        if (sel === 'alertView:clickedButtonAtIndex:') {
          event.buttonIndex = args[3].toInt32();
          event.input = textFieldValue(args[2]);
        }
        emit('flow-enter', event);
      },
      onLeave(retval) {
        const event = {
          className: cls,
          selector: this.selector,
          result: retval.toString(),
          implementation: location(implementation)
        };
        if (types !== null && types !== undefined && String(types)[0] === '@') {
          event.resultDescription = objectDescription(retval);
        } else if (types !== null && /^[BciIsSlLqQ]/.test(String(types))) {
          event.resultInteger = retval.toInt32();
        }
        emit('flow-leave', event);
        if (sel === 'viewDidAppear:' && invokeRecharge && !autoEntryTriggered) {
          autoEntryTriggered = true;
          snapshotState('pre-entry');
          invokeDonationEntry();
          snapshotState('post-entry');
        }
      }
    });
    emit('business-hook', { className: cls, selector: sel, implementation: location(implementation) });
  } catch (error) {
    emit('business-hook-error', { className: cls, selector: sel, error: String(error) });
  }
}

hookNative('sel_registerName', {
  onEnter(args) {
    this.name = null;
    try { this.name = args[0].readCString(); } catch (_) {}
    if (relevant(this.name) || /recharge:|perform:|scanQRCode:|showQRCodeView:|viewDidLoad|viewDidAppear/i.test(this.name || '')) {
      emit('selector', this.name);
    }
  }
});

for (const api of ['class_addMethod', 'class_replaceMethod']) {
  hookNative(api, {
    onEnter(args) {
      const cls = className(args[0]);
      const sel = selectorName(args[1]);
      const implementation = args[2];
      const types = args[3].isNull() ? null : args[3].readCString();
      this.businessMethod = { cls: cls, sel: sel, implementation: implementation, types: types };
      if (/ViewController|CTW/i.test(cls) || relevant(sel) || /recharge:|perform:|scanQRCode:|showQRCodeView:/i.test(sel)) {
        emit('method-register', {
          api: api,
          className: cls,
          selector: sel,
          implementation: implementation.toString(),
          location: location(implementation),
          types: types
        });
      }
    },
    onLeave(_) {
      const method = this.businessMethod;
      setImmediate(function() {
        hookBusinessImplementation(method.cls, method.sel, method.implementation, method.types);
      });
    }
  });
}

hookNative('method_setImplementation', {
  onEnter(args) {
    let sel = '<unknown>';
    try { sel = selectorName(methodGetName(args[0])); } catch (_) {}
    if (/^(viewDidLoad|updateUITimer|alertView:clickedButtonAtIndex:|recharge:|showQRCodeView:|scanQRCode:|qrCodeScannerDidScanResult:|JvgnSRHcrHmZxNJocXZHWQYSFjPrglVHvpybVYfpfuMZRgoCejVYdqxxTCjtzbfDwaNkQ|lockUI:|isNeedCheckIP|setIsNeedCheckIP:|isNeedFlushIP|setIsNeedFlushIP:|setText:)$/.test(sel)) {
      emit('method-set-implementation', {
        selector: sel,
        replacement: location(args[1]),
        caller: location(this.returnAddress)
      });
    }
  }
});

function hookObjC(classNameValue, selectorValue, isClassMethod, handler) {
  try {
    const cls = getClass(classNameValue);
    if (cls.isNull()) return;
    const sel = selector(selectorValue);
    const method = isClassMethod ? classGetClassMethod(cls, sel) : classGetInstanceMethod(cls, sel);
    if (method.isNull()) return;
    const implementation = methodGetImplementation(method);
    Interceptor.attach(implementation, { onEnter: handler });
    emit('hook', classNameValue + ' ' + (isClassMethod ? '+' : '-') + selectorValue + '=' + location(implementation));
  } catch (error) {
    emit('hook-error', classNameValue + ' ' + selectorValue + ': ' + error);
  }
}

hookObjC('UILabel', 'setText:', false, function(args) {
  const text = cfString(args[2]);
  if (relevant(text)) emit('ui-label', { text: text, caller: location(this.returnAddress) });
});
hookObjC('UITextField', 'setPlaceholder:', false, function(args) {
  const text = cfString(args[2]);
  if (relevant(text)) emit('ui-placeholder', { text: text, caller: location(this.returnAddress) });
});
hookObjC('UITextField', 'setText:', false, function(args) {
  const value = cfString(args[2]);
  if (value !== null && relevant(value)) emit('ui-input', { text: value, caller: location(this.returnAddress) });
});
hookObjC('UIAlertController', 'alertControllerWithTitle:message:preferredStyle:', true, function(args) {
  emit('alert', { title: cfString(args[2]), message: cfString(args[3]), caller: location(this.returnAddress) });
});
let lastAlert = nullPointer;
let lastController = nullPointer;
let submitButtonIndex = 1;

try {
  const alertClass = getClass('UIAlertView');
  const alertMethod = classGetInstanceMethod(alertClass, selector('initWithTitle:message:delegate:cancelButtonTitle:otherButtonTitles:'));
  if (!alertMethod.isNull()) {
    const alertImplementation = methodGetImplementation(alertMethod);
    Interceptor.attach(alertImplementation, {
      onEnter(args) {
        this.title = cfString(args[2]);
        this.message = cfString(args[3]);
        this.delegate = args[4];
        this.cancelButtonTitle = cfString(args[5]);
        this.otherButtonTitle = cfString(args[6]);
        this.caller = location(this.returnAddress);
      },
      onLeave(retval) {
        lastAlert = retval;
        if (!this.delegate.isNull() && className(objectGetClass(this.delegate)) === 'ViewController') {
          lastController = this.delegate;
        }
        if (/确定|确认|提交|验证|捐赠|充值/.test(this.cancelButtonTitle || '')) submitButtonIndex = 0;
        else if (/确定|确认|提交|验证|捐赠|充值/.test(this.otherButtonTitle || '')) submitButtonIndex = 1;
        emit('alert', {
          title: this.title,
          message: this.message,
          cancelButtonTitle: this.cancelButtonTitle,
          otherButtonTitle: this.otherButtonTitle,
          submitButtonIndex: submitButtonIndex,
          delegate: this.delegate.toString(),
          caller: this.caller,
          pointer: retval.toString()
        });
      }
    });
    emit('hook', 'UIAlertView -initWithTitle:message:delegate:cancelButtonTitle:otherButtonTitles:=' + location(alertImplementation));
  }
} catch (error) { emit('hook-error', 'UIAlertView init: ' + error); }
try {
  const alertClass = getClass('UIAlertView');
  const showMethod = classGetInstanceMethod(alertClass, selector('show'));
  if (!showMethod.isNull()) {
    const showImplementation = methodGetImplementation(showMethod);
    Interceptor.attach(showImplementation, {
      onEnter(args) {
        this.alert = args[0];
        emit('alert-show', { pointer: args[0].toString(), caller: location(this.returnAddress) });
      },
      onLeave(_) {
        lastAlert = this.alert;
        if (submitCodeValue !== null && !autoSubmitTriggered) {
          autoSubmitTriggered = true;
          snapshotState('pre-submit');
          submitDonationCode();
          snapshotState('post-submit-dispatch');
        }
      }
    });
    emit('hook', 'UIAlertView -show=' + location(showImplementation));
  }
} catch (error) { emit('hook-error', 'UIAlertView show: ' + error); }
hookObjC('NSURL', 'URLWithString:', true, function(args) {
  const value = cfString(args[2]);
  if (value !== null && (fromMain(this) || /https?:/i.test(value))) {
    emit('url-create', { url: value, caller: location(this.returnAddress) });
  }
});
const hookedCompletionInvokes = new Set();

function hookCompletionBlock(block, requestUrl) {
  if (block.isNull()) return;
  try {
    const implementation = block.add(16).readPointer();
    const key = implementation.toString();
    if (hookedCompletionInvokes.has(key)) return;
    hookedCompletionInvokes.add(key);
    Interceptor.attach(implementation, {
      onEnter(args) {
        let length = 0;
        let sample = null;
        try {
          length = Number(objcMsgSendLength(args[1], selector('length')));
          const bytes = objcMsgSend0(args[1], selector('bytes'));
          if (!bytes.isNull() && length > 0 && length <= 16 * 1024 * 1024) {
            sample = bytes.readUtf8String(Math.min(length, 16384));
          }
        } catch (_) {}
        let responseUrl = null;
        let statusCode = null;
        try {
          const url = objcMsgSend0(args[2], selector('URL'));
          responseUrl = cfString(objcMsgSend0(url, selector('absoluteString')));
          statusCode = Number(objcMsgSendLength(args[2], selector('statusCode')));
        } catch (_) {}
        emit('response', {
          requestUrl: requestUrl,
          responseUrl: responseUrl,
          statusCode: statusCode,
          length: length,
          sample: sample,
          error: objectDescription(args[3]),
          callback: location(implementation),
          caller: location(this.returnAddress)
        });
      }
    });
    emit('completion-hook', { requestUrl: requestUrl, implementation: location(implementation) });
  } catch (error) { emit('completion-hook-error', String(error)); }
}

hookObjC('NSURLSession', 'dataTaskWithRequest:completionHandler:', false, function(args) {
  try {
    const url = objcMsgSend0(args[2], selector('URL'));
    const absolute = url.isNull() ? nullPointer : objcMsgSend0(url, selector('absoluteString'));
    const method = objcMsgSend0(args[2], selector('HTTPMethod'));
    const body = objcMsgSend0(args[2], selector('HTTPBody'));
    let bodySample = null;
    if (!body.isNull()) {
      const bodyLength = Number(objcMsgSendLength(body, selector('length')));
      const bodyBytes = objcMsgSend0(body, selector('bytes'));
      if (!bodyBytes.isNull() && bodyLength > 0 && bodyLength <= 1024 * 1024) {
        bodySample = bodyBytes.readUtf8String(Math.min(bodyLength, 16384));
      }
    }
    const urlText = cfString(absolute);
    emit('request', {
      url: urlText,
      method: cfString(method),
      body: bodySample,
      headers: objectDescription(objcMsgSend0(args[2], selector('allHTTPHeaderFields'))),
      caller: location(this.returnAddress)
    });
    hookCompletionBlock(args[3], urlText);
  } catch (error) { emit('request-error', String(error)); }
});
hookObjC('NSURLSession', 'dataTaskWithURL:completionHandler:', false, function(args) {
  const absolute = args[2].isNull() ? nullPointer : objcMsgSend0(args[2], selector('absoluteString'));
  const urlText = cfString(absolute);
  emit('request', { url: urlText, method: 'GET', caller: location(this.returnAddress) });
  hookCompletionBlock(args[3], urlText);
});
hookObjC('NSJSONSerialization', 'JSONObjectWithData:options:error:', true, function(args) {
  this.caller = location(this.returnAddress);
  this.sample = null;
  try {
    const data = args[2];
    const length = Number(objcMsgSendLength(data, selector('length')));
    const bytes = objcMsgSend0(data, selector('bytes'));
    if (!bytes.isNull() && length > 0) {
      const sample = bytes.readUtf8String(Math.min(length, 8192));
      this.sample = sample;
      if (fromMain(this) || relevant(sample)) {
        emit('json-input', { length: length, sample: sample, caller: location(this.returnAddress) });
      }
    }
  } catch (error) { emit('json-error', String(error)); }
});
hookObjC('NSUserDefaults', 'setObject:forKey:', false, function(args) {
  const key = cfString(args[3]);
  if (relevant(key) || fromMain(this)) {
    emit('defaults-write', { key: key, caller: location(this.returnAddress) });
  }
});
hookObjC('NSUserDefaults', 'objectForKey:', false, function(args) {
  const key = cfString(args[2]);
  if (relevant(key)) emit('defaults-read', { key: key, caller: location(this.returnAddress) });
});
for (const hud of [
  ['SVProgressHUD', 'showWithStatus:', true],
  ['SVProgressHUD', 'setStatus:', true],
  ['JGProgressHUD', 'setText:', false]
]) {
  hookObjC(hud[0], hud[1], hud[2], function(args) {
    emit('hud', { className: hud[0], selector: hud[1], text: cfString(args[2]), caller: location(this.returnAddress) });
  });
}

for (const name of ['kill', 'exit', '_exit', 'abort']) {
  hookNative(name, {
    onEnter(args) {
      emit('termination', {
        api: name,
        arg0: args[0].toInt32(),
        caller: location(this.returnAddress),
        backtrace: Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 12).map(location)
      });
    }
  });
}

function topController() {
  const app = objcMsgSend0(getClass('UIApplication'), selector('sharedApplication'));
  const window = objcMsgSend0(app, selector('keyWindow'));
  const root = objcMsgSend0(window, selector('rootViewController'));
  let top = root;
  try {
    const topSelector = selector('topViewController');
    const topMethod = classGetInstanceMethod(objectGetClass(root), topSelector);
    if (!topMethod.isNull()) top = objcMsgSend0(root, topSelector);
  } catch (_) {}
  return top;
}

function invokeDonationEntry() {
  if (!invokeRecharge) return;
  try {
    const top = topController();
    lastController = top;
    emit('top-controller', { className: className(objectGetClass(top)), pointer: top.toString() });
    const recharge = selector('recharge:');
    const method = classGetInstanceMethod(objectGetClass(top), recharge);
    if (!method.isNull()) {
      emit('invoke', { selector: 'recharge:', implementation: location(methodGetImplementation(method)) });
      objcMsgSend1(top, recharge, nullPointer);
    } else {
      emit('invoke-error', 'top controller does not respond to recharge:');
    }
  } catch (error) { emit('invoke-error', String(error)); }
}

function snapshotState(label) {
  try {
    let controller = lastController;
    if (controller.isNull() || className(objectGetClass(controller)) !== 'ViewController') {
      controller = topController();
    }
    if (controller.isNull()) {
      emit('state-snapshot', { label: label, controller: null });
      return;
    }
    const controllerClass = className(objectGetClass(controller));
    if (controllerClass === 'ViewController') lastController = controller;
    const objects = {};
    for (const name of ['statusDescription', 'expireDate', 'machineState', 'manageredApd', 'ipAddress']) {
      try { objects[name] = objectDescription(objcMsgSend0(controller, selector(name))); }
      catch (error) { objects[name] = '<error: ' + error + '>'; }
    }
    const booleans = {};
    for (const name of ['isIsolateMode', 'isNeedCheckIP', 'isNeedFlushIP', 'isForce', 'isFirmware']) {
      try { booleans[name] = objcMsgSend0(controller, selector(name)).toInt32(); }
      catch (error) { booleans[name] = '<error: ' + error + '>'; }
    }
    emit('state-snapshot', {
      label: label,
      controller: controller.toString(),
      controllerClass: controllerClass,
      objects: objects,
      booleans: booleans
    });
  } catch (error) { emit('state-snapshot-error', { label: label, error: String(error) }); }
}

function submitDonationCode() {
  if (submitCodeValue === null || lastAlert.isNull() || lastController.isNull()) {
    emit('submit-skip', {
      hasCode: submitCodeValue !== null,
      alert: lastAlert.toString(),
      controller: lastController.toString()
    });
    return;
  }
  const field = objcMsgSendIndex(lastAlert, selector('textFieldAtIndex:'), 0);
  const value = objcMsgSendPointer(getClass('NSString'), selector('stringWithUTF8String:'), cString(submitCodeValue));
  objcMsgSend1(field, selector('setText:'), value);
  emit('submit', {
    code: submitCodeValue,
    buttonIndex: submitButtonIndex,
    alert: lastAlert.toString(),
    controller: lastController.toString()
  });
  objcMsgSendAlertIndex(lastController, selector('alertView:clickedButtonAtIndex:'), lastAlert, submitButtonIndex);
}

setTimeout(function() {
  const module = Process.findModuleByName('fix.dylib');
  emit('deep-patch-module', module === null ? null : {
    name: module.name,
    path: module.path,
    base: module.base.toString(),
    size: module.size
  });
}, 0);

for (const delay of [8000, 15000, 30000, 55000]) {
  setTimeout(function() {
    runOnMain(function() { snapshotState('timer-' + delay + 'ms'); });
  }, delay);
}

emit('ready', { main: main.path, pid: Process.id });
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--invoke-recharge", action="store_true")
    parser.add_argument("--submit-code")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def record(kind: str, data: object) -> None:
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        line = json.dumps({"time": stamp, "kind": kind, "data": data}, ensure_ascii=False)
        print(line, flush=True)
        lines.append(line)

    def on_message(message: dict[str, object], data: bytes | None) -> None:
        if message.get("type") == "send":
            payload = message.get("payload", {})
            if isinstance(payload, dict):
                record(str(payload.get("kind", "send")), payload.get("data"))
            else:
                record("send", payload)
        else:
            record("frida", message)

    device = frida.get_usb_device(timeout=5)
    pid = device.spawn([BUNDLE_ID])
    record("spawn", {"bundle": BUNDLE_ID, "pid": pid, "device": device.id})
    session = device.attach(pid)
    javascript = JAVASCRIPT.replace(
        "__INVOKE_RECHARGE__", "true" if args.invoke_recharge else "false"
    ).replace("__SUBMIT_CODE__", json.dumps(args.submit_code))
    script = session.create_script(javascript)
    script.on("message", on_message)
    script.load()
    device.resume(pid)
    record("resume", {"pid": pid})

    try:
        time.sleep(args.duration)
    finally:
        try:
            device.kill(pid)
            record("kill-after-probe", {"pid": pid})
        except frida.InvalidOperationError:
            record("process-ended", {"pid": pid})
        try:
            session.detach()
        except frida.InvalidOperationError:
            pass
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
