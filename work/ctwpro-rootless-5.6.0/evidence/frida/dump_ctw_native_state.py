#!/usr/bin/env python3
"""Export CTW's already-parsed runtime config without requiring Frida's ObjC bridge."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import frida


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "ctw_native_state_dump.js"
OUTPUT = (
    HERE.parent.parent.parent
    / "ctwpro-5.6.0"
    / "embedded-json"
    / "decrypted"
    / "runtime-state"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-id", default="com.xxdevice.CTWPro")
    parser.add_argument("--spawn", action="store_true")
    parser.add_argument("--load-tweaks", action="store_true")
    parser.add_argument("--invoke-local-random", action="store_true")
    parser.add_argument("--wait", type=float, default=45.0)
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    device = frida.get_usb_device(timeout=5)
    spawned_pid = None
    if args.spawn:
        for process in device.enumerate_processes():
            if process.name == "CTW Pro":
                try:
                    device.kill(process.pid)
                except frida.InvalidOperationError:
                    pass
        time.sleep(0.5)
        spawned_pid = device.spawn([args.bundle_id])
        session = device.attach(spawned_pid)
    else:
        process = next(p for p in device.enumerate_processes() if p.name == "CTW Pro")
        session = device.attach(process.pid)
    finished = False

    def on_message(message: dict, data: bytes | None) -> None:
        nonlocal finished
        if message.get("type") == "error":
            print(json.dumps(message, ensure_ascii=False), flush=True)
            finished = True
            return
        payload = message.get("payload", {})
        kind = payload.get("kind", "message")
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        if data is not None:
            suffix = ".json" if kind.startswith(("device-", "vd-")) else ".bin"
            path = OUTPUT / f"{kind}{suffix}"
            path.write_bytes(data)
            print(f"saved {len(data)} bytes: {path}", flush=True)
        if kind == "complete":
            finished = True

    javascript = SCRIPT.read_text().replace(
        "__INVOKE_LOCAL_RANDOM__",
        "true" if args.invoke_local_random else "false",
    ).replace(
        "__LOAD_TWEAKS__",
        "true" if args.load_tweaks else "false",
    )
    script = session.create_script(javascript)
    script.on("message", on_message)
    script.load()
    if spawned_pid is not None:
        device.resume(spawned_pid)
    deadline = time.monotonic() + args.wait
    while not finished and time.monotonic() < deadline:
        time.sleep(0.1)
    session.detach()
    if not finished:
        raise TimeoutError("runtime state dump timed out")


if __name__ == "__main__":
    main()
