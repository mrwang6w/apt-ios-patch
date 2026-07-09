#!/usr/bin/env python3
"""Attach to Sileo and record APT/dpkg child process launches and result codes."""
from __future__ import annotations

import datetime as dt
import sys
import time

import frida


DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
OUTPUT = f"sileo-install-trace-{dt.datetime.now():%Y%m%d-%H%M%S}.log"

SCRIPT = r'''
'use strict';
function emit(text) { send({ text: String(text) }); }
function argvAt(ptr) {
  const out = [];
  if (ptr.isNull()) return out;
  for (let i = 0; i < 32; i++) {
    const p = ptr.add(i * Process.pointerSize).readPointer();
    if (p.isNull()) break;
    try { out.push(p.readUtf8String()); } catch (_) { out.push('<unreadable>'); }
  }
  return out;
}
function hookSpawn(name) {
  const p = Module.findGlobalExportByName(name);
  if (!p) { emit('missing ' + name); return; }
  Interceptor.attach(p, {
    onEnter(args) {
      this.path = args[1].isNull() ? '<null>' : args[1].readUtf8String();
      this.argv = argvAt(args[4]);
      emit(name + ' path=' + this.path + ' argv=' + JSON.stringify(this.argv));
    },
    onLeave(retval) { emit(name + ' result=' + retval.toInt32() + ' path=' + this.path); }
  });
}
['posix_spawn', 'posix_spawnp'].forEach(hookSpawn);
for (const name of ['execve', 'system']) {
  const p = Module.findGlobalExportByName(name);
  if (!p) continue;
  Interceptor.attach(p, {
    onEnter(args) {
      let detail = '<unreadable>';
      try { detail = name === 'execve' ? JSON.stringify(argvAt(args[1])) : args[0].readUtf8String(); } catch (_) {}
      emit(name + ' ' + detail);
    },
    onLeave(retval) { emit(name + ' result=' + retval.toInt32()); }
  });
}
if (typeof ObjC !== 'undefined' && ObjC.available) {
  const task = ObjC.classes.NSTask;
  if (task) {
    for (const selector of ['- launch', '- launchAndReturnError:', '- waitUntilExit']) {
      const method = task[selector];
      if (!method) continue;
      Interceptor.attach(method.implementation, {
        onEnter() {
          try { emit('NSTask ' + selector + ' path=' + new ObjC.Object(this.context.x0).launchPath().toString() + ' args=' + new ObjC.Object(this.context.x0).arguments().toString()); } catch (_) {}
        }
      });
    }
  }
}
emit('ready pid=' + Process.id);
'''


def main() -> None:
    device = frida.get_usb_device(timeout=10)
    target = next(
        process
        for process in device.enumerate_processes()
        if process.name == "Sileo" or process.parameters.get("identifier") == "org.coolstar.SileoStore"
    )
    session = device.attach(target.pid)
    log_path = __file__.replace("sileo_install_trace.py", OUTPUT)
    with open(log_path, "w", encoding="utf-8") as log:
        def on_message(message: dict, _data: bytes | None) -> None:
            now = dt.datetime.now().isoformat(timespec="seconds")
            if message.get("type") == "send":
                line = str(message["payload"].get("text", message["payload"]))
            else:
                line = repr(message)
            print(f"[{now}] {line}", flush=True)
            log.write(f"[{now}] {line}\n")
            log.flush()

        script = session.create_script(SCRIPT)
        script.on("message", on_message)
        script.load()
        time.sleep(DURATION)
        session.detach()
    print(log_path, flush=True)


if __name__ == "__main__":
    main()
