#!/usr/bin/env python3
"""Spawn CTW Pro and retain the Frida session while launch probes run."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import frida


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-id", default="com.xxdevice.CTWPro")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument(
        "--script",
        type=Path,
        default=Path(__file__).with_name("ctw_launch_black_probe.js"),
    )
    args = parser.parse_args()

    device = frida.get_usb_device(timeout=10)
    pid = device.spawn([args.bundle_id])
    print(json.dumps({"kind": "spawned", "pid": pid}), flush=True)
    session = device.attach(pid)

    def on_detached(reason, crash):
        crash_text = None if crash is None else str(crash)
        print(
            json.dumps(
                {"kind": "detached", "reason": reason, "crash": crash_text},
                ensure_ascii=False,
            ),
            flush=True,
        )

    session.on("detached", on_detached)
    script = session.create_script(args.script.read_text())

    def on_message(message, data):
        print(
            json.dumps(
                {"kind": "frida-message", "message": message},
                ensure_ascii=False,
            ),
            flush=True,
        )

    script.on("message", on_message)
    script.load()
    device.resume(pid)
    print(json.dumps({"kind": "resumed", "pid": pid}), flush=True)
    time.sleep(args.duration)
    print(json.dumps({"kind": "duration-complete", "pid": pid}), flush=True)
    try:
        session.detach()
    except frida.InvalidOperationError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
