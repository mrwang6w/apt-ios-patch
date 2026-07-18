#!/usr/bin/env python3
"""Inject embedded /vd records into CTW Pro and collect its native decrypt outputs."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import time
from pathlib import Path

import frida


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "ctwpro-5.6.0/embedded-json/embedded-datas-response.json"
TEMPLATE = HERE / "ctw_inject_vd_response.js"
OUTPUT = ROOT / "ctwpro-5.6.0/embedded-json/decrypted/vd-runtime"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=int)
    parser.add_argument("--aes-key", help="force one AES-128 key for the injected record")
    parser.add_argument(
        "--spoof-time",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="present the record timestamp as current time without modifying signed JSON",
    )
    parser.add_argument("--force-parse-state", type=int)
    parser.add_argument("--wait", type=float, default=15)
    args = parser.parse_args()

    records = json.loads(SOURCE.read_text())["datas"]
    selected = records[args.index]
    inner_path = ROOT / (
        f"ctwpro-5.6.0/embedded-json/decrypted/vd-record-{args.index:02d}-inner.json"
    )
    spoof_epoch_ms = None
    if args.spoof_time:
        inner = json.loads(inner_path.read_text())
        spoof_epoch_ms = int(inner["d65a2f9f"]) + 1000
    record = json.dumps(selected, ensure_ascii=False, separators=(",", ":"))
    cipher_length = len(base64.b64decode(selected["data"]))
    javascript = TEMPLATE.read_text().replace(
        "__INJECTED_RESPONSE__", json.dumps(record)
    ).replace(
        "__FORCED_AES_KEY__", json.dumps(args.aes_key)
    ).replace(
        "__FORCED_CIPHER_LENGTH__", str(cipher_length)
    ).replace(
        "__TARGET_URL_PATTERN__", json.dumps(r"/vd\?")
    ).replace(
        "__INVOKE_RANDOM__", "true"
    ).replace(
        "__SPOOF_EPOCH_MS__", json.dumps(spoof_epoch_ms)
    ).replace(
        "__FORCE_PARSE_STATE__", json.dumps(args.force_parse_state)
    )

    output = OUTPUT / f"record-{args.index:02d}"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
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
            path = output / f"{artifact_index:03d}-{kind}.bin"
            artifact_index += 1
            path.write_bytes(data)
            print(f"saved {len(data)} bytes: {path}", flush=True)

    script = session.create_script(javascript)
    script.on("message", on_message)
    script.load()
    device.resume(pid)
    time.sleep(args.wait)
    (output / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2)
    )
    session.detach()


if __name__ == "__main__":
    main()
