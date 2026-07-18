#!/usr/bin/env python3
"""Call CTW.dylib's Swift lk.Encryption.decrypt for a JSON data field."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import frida


def javascript_for(value: str, slot: int | None) -> str:
    return r"""
'use strict';
const input = __INPUT__;
function native(name, result, argumentTypes) {
  return new NativeFunction(Module.getGlobalExportByName(name), result, argumentTypes);
}
function cString(value) { return Memory.allocUtf8String(value); }
const dlopen = native('dlopen', 'pointer', ['pointer', 'int']);
dlopen(cString('/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib'), 2);
const objcGetClass = native('objc_getClass', 'pointer', ['pointer']);
const selRegisterName = native('sel_registerName', 'pointer', ['pointer']);
const objcMsgSend1 = native('objc_msgSend', 'pointer', ['pointer', 'pointer', 'pointer']);
const objcMsgSend0 = native('objc_msgSend', 'pointer', ['pointer', 'pointer']);
const objcMsgSendLength = native('objc_msgSend', 'ulong', ['pointer', 'pointer']);
const nsString = objcMsgSend1(
  objcGetClass(cString('NSString')),
  selRegisterName(cString('stringWithUTF8String:')),
  cString(input)
);
const toSwift = new NativeFunction(
  Module.getGlobalExportByName('$sSS10FoundationE36_unconditionallyBridgeFromObjectiveCySSSo8NSStringCSgFZ'),
  ['uint64', 'uint64'],
  ['pointer']
);
const toObjC = new NativeFunction(
  Module.getGlobalExportByName('$sSS10FoundationE19_bridgeToObjectiveCSo8NSStringCyF'),
  'pointer',
  ['uint64', 'uint64']
);
const swiftInput = toSwift(nsString);
const ctw = Process.getModuleByName('CTW.dylib');
const forcedSlot = __SLOT__;
if (forcedSlot !== null) {
  Interceptor.replace(
    ctw.base.add(0x1cb5c),
    new NativeCallback(function () { return forcedSlot; }, 'int64', [])
  );
}
const decrypt = new NativeFunction(
  ctw.base.add(0x1e200),
  ['uint64', 'uint64'],
  ['uint64', 'uint64']
);
const swiftOutput = decrypt(swiftInput[0], swiftInput[1]);
const outputString = toObjC(swiftOutput[0], swiftOutput[1]);
const outputData = objcMsgSend1(
  outputString,
  selRegisterName(cString('dataUsingEncoding:')),
  ptr('4')
);
const length = Number(objcMsgSendLength(outputData, selRegisterName(cString('length'))));
const bytes = objcMsgSend0(outputData, selRegisterName(cString('bytes')));
send({ kind: 'decrypted', inputLength: input.length, outputLength: length, slot: forcedSlot }, bytes.readByteArray(length));
""".replace("__INPUT__", json.dumps(value)).replace("__SLOT__", json.dumps(slot))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--key", default="data")
    parser.add_argument("--slot", type=int)
    parser.add_argument("--wait", type=float, default=30)
    args = parser.parse_args()

    document = json.loads(args.input.read_text())
    value = document[args.key]
    if not isinstance(value, str):
        raise TypeError(f"{args.key!r} is not a string")

    device = frida.get_usb_device(timeout=5)
    for process in device.enumerate_processes():
        if process.name == "Tips":
            try:
                device.kill(process.pid)
            except frida.InvalidOperationError:
                pass
    pid = device.spawn(["com.apple.tips"])
    session = device.attach(pid)
    finished = False

    def on_message(message: dict, data: bytes | None) -> None:
        nonlocal finished
        print(json.dumps(message.get("payload", message), ensure_ascii=False), flush=True)
        if message.get("type") == "error":
            finished = True
            return
        payload = message.get("payload", {})
        if payload.get("kind") == "decrypted" and data is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
            finished = True

    script = session.create_script(javascript_for(value, args.slot))
    script.on("message", on_message)
    script.load()
    device.resume(pid)
    deadline = time.monotonic() + args.wait
    while not finished and time.monotonic() < deadline:
        time.sleep(0.1)
    session.detach()
    if not finished:
        raise TimeoutError("Swift decrypt did not finish")


if __name__ == "__main__":
    main()
