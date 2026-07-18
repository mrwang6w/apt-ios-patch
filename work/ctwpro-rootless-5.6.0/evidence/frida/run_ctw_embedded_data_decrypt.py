#!/usr/bin/env python3
"""Inject the embedded UI-config response and collect its runtime plaintext."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import frida


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "ctwpro-5.6.0/embedded-json/embedded-data-response.json"
TEMPLATE = HERE / "ctw_inject_vd_response.js"
OUTPUT = ROOT / "ctwpro-5.6.0/embedded-json/decrypted/ui-runtime"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", type=float, default=180)
    args = parser.parse_args()

    response = SOURCE.read_text()
    javascript = TEMPLATE.read_text().replace(
        "__INJECTED_RESPONSE__", json.dumps(response)
    ).replace(
        "__FORCED_AES_KEY__", "null"
    ).replace(
        "__FORCED_CIPHER_LENGTH__", "-1"
    ).replace(
        "__TARGET_URL_PATTERN__", json.dumps(r"/upload3")
    ).replace(
        "__INVOKE_RANDOM__", "false"
    )

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    events: list[dict] = []
    artifact_index = 0

    device = frida.get_usb_device(timeout=5)
    for process in device.enumerate_processes():
        if process.name == "CTW Pro":
            try:
                device.kill(process.pid)
            except frida.InvalidOperationError:
                pass
    time.sleep(0.5)
    pid = device.spawn(["com.xxdevice.CTWPro"])
    session = device.attach(pid)

    def on_message(message: dict, data: bytes | None) -> None:
        nonlocal artifact_index
        events.append(message)
        payload = message.get("payload", message)
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        if data is not None:
            kind = payload.get("kind", "artifact")
            path = OUTPUT / f"{artifact_index:03d}-{kind}.bin"
            artifact_index += 1
            path.write_bytes(data)
            print(f"saved {len(data)} bytes: {path}", flush=True)

    script = session.create_script(javascript)
    script.on("message", on_message)
    script.load()
    device.resume(pid)
    time.sleep(args.wait)
    (OUTPUT / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2)
    )
    session.detach()


if __name__ == "__main__":
    main()
