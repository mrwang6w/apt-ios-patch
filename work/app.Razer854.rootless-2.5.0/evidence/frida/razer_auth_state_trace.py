#!/usr/bin/env python3
"""Trace Razer's actual authorization-state reads without changing behavior."""
from __future__ import annotations

import datetime as dt
import json
import argparse
import time

import frida


DURATION = 180.0

SCRIPT = r'''
'use strict';
function emit(text) { send({text: String(text)}); }
function safeCString(pointer) {
  try { return pointer.isNull() ? '<null>' : pointer.readCString(); }
  catch (_) { return '<unreadable>'; }
}
const app = Process.enumerateModules().find(function (m) { return m.name === 'Razer'; });
if (!app) throw new Error('Razer module not found');
const appEnd = app.base.add(app.size);
function inApp(address) {
  try { return address.compare(app.base) >= 0 && address.compare(appEnd) < 0; }
  catch (_) { return false; }
}
const cfStringGetCString = Module.findGlobalExportByName('CFStringGetCString');
const getCString = cfStringGetCString ? new NativeFunction(cfStringGetCString, 'bool', ['pointer', 'pointer', 'ulong', 'uint']) : null;
function cfString(pointer) {
  if (!pointer || pointer.isNull() || !getCString) return '<null-or-no-cfstring>';
  try {
    const out = Memory.alloc(1024);
    return getCString(pointer, out, 1024, 0x08000100) ? out.readUtf8String() : '<non-utf8>';
  } catch (_) { return '<unreadable>'; }
}
function ptrValue(pointer) { try { return pointer.toString(); } catch (_) { return '<invalid>'; } }
// Resolve and hook only the concrete target methods. A global objc_msgSend hook
// is too invasive on this device: CoreFoundation/ColorSync also use it during
// UIKit initialization and can terminate the app through an exception path.
const objcGetClass = new NativeFunction(
  Module.findGlobalExportByName('objc_getClass'), 'pointer', ['pointer']);
const selRegisterName = new NativeFunction(
  Module.findGlobalExportByName('sel_registerName'), 'pointer', ['pointer']);
const classGetInstanceMethod = new NativeFunction(
  Module.findGlobalExportByName('class_getInstanceMethod'), 'pointer', ['pointer', 'pointer']);
const methodGetImplementation = new NativeFunction(
  Module.findGlobalExportByName('method_getImplementation'), 'pointer', ['pointer']);
const classGetClassMethod = new NativeFunction(
  Module.findGlobalExportByName('class_getClassMethod'), 'pointer', ['pointer', 'pointer']);
const actionClass = objcGetClass(Memory.allocUtf8String('UIAlertAction'));
const actionTitleSelector = selRegisterName(Memory.allocUtf8String('title'));
const actionTitleMethod = actionClass.isNull() ? ptr(0) : classGetInstanceMethod(actionClass, actionTitleSelector);
const actionTitleImplementation = actionTitleMethod.isNull() ? ptr(0) : methodGetImplementation(actionTitleMethod);
const actionTitle = actionTitleImplementation.isNull()
  ? null : new NativeFunction(actionTitleImplementation, 'pointer', ['pointer', 'pointer']);
function actionTitleText(pointer) {
  if (!actionTitle || !pointer || pointer.isNull()) return '<no-title>';
  try { return cfString(actionTitle(pointer, actionTitleSelector)); } catch (_) { return '<title-unreadable>'; }
}
function hookTargetMethod(className, selector) {
  const classPtr = objcGetClass(Memory.allocUtf8String(className));
  const selectorPtr = selRegisterName(Memory.allocUtf8String(selector));
  if (classPtr.isNull() || selectorPtr.isNull()) {
    emit('METHOD missing-class-or-selector class=' + className + ' sel=' + selector);
    return;
  }
  const method = classGetInstanceMethod(classPtr, selectorPtr);
  if (method.isNull()) {
    emit('METHOD missing class=' + className + ' sel=' + selector);
    return;
  }
  const implementation = methodGetImplementation(method);
  try {
    Interceptor.attach(implementation, {
      onEnter(args) {
        if (!inApp(this.returnAddress)) return;
        const keyArg = selector === 'setObject:forKey:' || selector === 'setValue:forKey:' ? args[3] : args[2];
        const key = /ForKey|Subscript/.test(selector) ? cfString(keyArg) : '';
        const keyPointer = /ForKey|Subscript/.test(selector) ? ptrValue(keyArg) : '';
        if (key && !/(license|auth|expire|expiry|deadline|endtime|time|date|valid)/i.test(key) &&
            key !== '<non-utf8>' && key !== '<unreadable>') return;
        this.watch = true;
        this.key = key;
        this.keyPointer = keyPointer;
        const payload = selector === 'setMessage:' ? ' message=' + cfString(args[2])
          : selector === 'addAction:' ? ' actionTitle=' + actionTitleText(args[2])
          : /setObject:forKey:|setValue:forKey:/.test(selector) ? ' setValue=' + safeObjectDescription(args[2]) : '';
        emit('ENTER class=' + className + ' sel=' + selector + ' key=' + key + ' keyptr=' + keyPointer + payload + ' caller=' + this.returnAddress);
      },
      onLeave(retval) {
        if (!this.watch) return;
        const value = selector === 'boolForKey:' || selector === 'integerForKey:' || selector === 'doubleForKey:'
          ? retval.toString() : (cfString(retval) + ' (' + ptrValue(retval) + ')');
        emit('LEAVE class=' + className + ' sel=' + selector + ' key=' + this.key + ' keyptr=' + this.keyPointer + ' value=' + value);
      }
    });
    emit('HOOK class=' + className + ' sel=' + selector + ' imp=' + implementation);
  } catch (error) { emit('HOOK error class=' + className + ' sel=' + selector + ' error=' + error); }
}

function safeObjectDescription(pointer) {
  if (!pointer || pointer.isNull()) return '<null>';
  const textValue = cfString(pointer);
  if (textValue !== '<unreadable>' && textValue !== '<non-utf8>' && textValue !== '<null-or-no-cfstring>') {
    return textValue;
  }
  return ptrValue(pointer);
}

for (const className of [
  'NSUserDefaults', 'NSDictionary', '__NSDictionaryI', '__NSDictionaryM',
  '__NSSingleEntryDictionaryI', '__NSDictionary0', '__NSDictionary1',
  'UIAlertController', 'UIAlertAction'
]) {
  for (const selector of [
    'objectForKey:', 'objectForKeyedSubscript:', 'boolForKey:', 'stringForKey:',
    'integerForKey:', 'doubleForKey:', 'setObject:forKey:', 'setValue:forKey:',
    'setMessage:', 'addAction:', 'title'
  ]) hookTargetMethod(className, selector);
}

function hookClassMethod(className, selector) {
  const classPtr = objcGetClass(Memory.allocUtf8String(className));
  const selectorPtr = selRegisterName(Memory.allocUtf8String(selector));
  if (classPtr.isNull() || selectorPtr.isNull()) return;
  const method = classGetClassMethod(classPtr, selectorPtr);
  if (method.isNull()) return;
  const implementation = methodGetImplementation(method);
  try {
    Interceptor.attach(implementation, {
      onEnter(args) {
        if (!inApp(this.returnAddress)) return;
        this.watch = true;
        this.argument = safeObjectDescription(args[2]);
        emit('ENTER class+' + className + ' sel=' + selector + ' arg=' + this.argument + ' caller=' + this.returnAddress);
      },
      onLeave(retval) {
        if (!this.watch) return;
        emit('LEAVE class+' + className + ' sel=' + selector + ' arg=' + this.argument + ' ret=' + safeObjectDescription(retval));
      }
    });
    emit('HOOK class+' + className + ' sel=' + selector + ' imp=' + implementation);
  } catch (error) { emit('HOOK class+ error class=' + className + ' sel=' + selector + ' error=' + error); }
}
hookClassMethod('UIAlertAction', 'actionWithTitle:style:handler:');
hookClassMethod('AppDelegate', 'RR:');
hookClassMethod('AppDelegate', 'RRSet:value:');
hookClassMethod('AppDelegate', 'RReload');

// Hook the known VM entry offsets independently of ObjC bridge availability.
for (const [label, offset] of [
  ['requestlicense', 0x3d2018], ['main-showAlert', 0x3d2fe0],
  ['buttonAuthTapped', 0xd97694], ['license-showAlert', 0xd9b8c0],
  ['main-cleanDataClicked', 0x3d1ea8], ['license-cleanDataClicked', 0xd9b91c]
]) {
  const address = app.base.add(offset);
  try {
    Interceptor.attach(address, { onEnter() {
      emit('METHOD ' + label + ' entered caller=' + this.returnAddress);
    } });
  } catch (error) { emit('METHOD ' + label + ' hook-error=' + error); }
}
const seenModules = new Set();
function emitAuthModules() {
  Process.enumerateModules().forEach(function (module) {
    if (/RazerAuth2099|TweakInject/i.test(module.name + ' ' + module.path) && !seenModules.has(module.path)) {
      seenModules.add(module.path);
      emit('MODULE name=' + module.name + ' base=' + module.base + ' path=' + module.path);
    }
  });
}
emitAuthModules();
const moduleTimer = setInterval(emitAuthModules, 500);
setTimeout(function () { clearInterval(moduleTimer); }, 15000);
emit('ready base=' + app.base + ' size=' + app.size);
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attach", action="store_true", help="attach to an already-running Razer")
    parser.add_argument("--duration", type=float, default=DURATION)
    args = parser.parse_args()

    device = frida.get_usb_device(timeout=10)
    spawned_pid = None
    session = None
    try:
        if args.attach:
            target = next(process for process in device.enumerate_processes() if process.name == "Razer")
            pid = target.pid
            print(f"attach pid={pid}", flush=True)
        else:
            pid = device.spawn(["Razer"])
            spawned_pid = pid
            print(f"spawn pid={pid}", flush=True)
        output = __file__.replace(
            "razer_auth_state_trace.py",
            f"razer-auth-state-trace-{dt.datetime.now():%Y%m%d-%H%M%S}.log",
        )
        print(f"output={output}", flush=True)
        session = device.attach(pid)
        with open(output, "w", encoding="utf-8") as log:
            def on_message(message: dict, _data: bytes | None) -> None:
                now = dt.datetime.now().isoformat(timespec="seconds")
                if message.get("type") == "send":
                    payload = message.get("payload", {})
                    text = payload.get("text", payload) if isinstance(payload, dict) else payload
                else:
                    text = json.dumps(message, ensure_ascii=False)
                line = f"[{now}] {text}"
                print(line, flush=True)
                log.write(line + "\n")
                log.flush()

            def on_destroyed() -> None:
                line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] SCRIPT DESTROYED"
                print(line, flush=True)

            script = session.create_script(SCRIPT)
            script.on("message", on_message)
            script.on("destroyed", on_destroyed)
            script.load()
            if spawned_pid is not None:
                device.resume(spawned_pid)
                print("resumed; interact with Razer now", flush=True)
            time.sleep(args.duration)
    finally:
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
        if spawned_pid is not None:
            try:
                device.kill(spawned_pid)
            except Exception:
                pass


if __name__ == "__main__":
    main()
