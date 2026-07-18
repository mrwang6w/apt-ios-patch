#!/usr/bin/env python3
"""Materialize validated JSON plaintexts from CTW runtime evidence."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from Crypto.Cipher import AES


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EMBEDDED = ROOT / "ctwpro-5.6.0/embedded-json"
OUTPUT = EMBEDDED / "decrypted"
UI_RUNTIME = OUTPUT / "ui-runtime"
VD_RUNTIME = OUTPUT / "vd-runtime"
UI_KEY = b"CTW_UICONFIG_KEY"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unpad_pkcs7(data: bytes) -> bytes:
    padding = data[-1]
    if not 1 <= padding <= 16 or data[-padding:] != bytes([padding]) * padding:
        raise ValueError("invalid PKCS#7 padding")
    return data[:-padding]


def load_json(data: bytes) -> object:
    return json.loads(data.decode("utf-8"))


def write_pretty(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def recover_ui_plaintext() -> tuple[Path, dict]:
    calibration_response = load_json((UI_RUNTIME / "001-json-input.bin").read_bytes())
    calibration_cipher = next(
        (VD_RUNTIME / "record-00").glob("*-cccrypt-input.bin")
    ).read_bytes()
    standard = base64.b64encode(calibration_cipher).decode("ascii")
    custom = calibration_response["data"]
    if len(standard) != len(custom):
        raise ValueError("UI calibration lengths do not match")

    mapping: dict[str, str] = {}
    for source, target in zip(custom, standard):
        previous = mapping.setdefault(source, target)
        if previous != target:
            raise ValueError(f"conflicting UI mapping for {source!r}")

    document = load_json((EMBEDDED / "embedded-data-response.json").read_bytes())
    translated = "".join(mapping[character] for character in document["data"])
    cipher = base64.b64decode(translated, validate=True)
    plain = unpad_pkcs7(AES.new(UI_KEY, AES.MODE_ECB).decrypt(cipher))
    value = load_json(plain)
    path = OUTPUT / "embedded-data-plaintext.json"
    write_pretty(path, value)
    return path, {
        "source": "embedded-data-response.json",
        "output": path.name,
        "mapping_size": len(mapping),
        "cipher": "AES-128-ECB/PKCS#7",
        "key_ascii": UI_KEY.decode("ascii"),
        "plaintext_bytes": len(plain),
        "plaintext_sha256": sha256(plain),
    }


def runtime_json_candidates(directory: Path) -> list[bytes]:
    artifacts = {
        int(path.name.split("-", 1)[0]): path
        for path in directory.glob("[0-9][0-9][0-9]-*.bin")
    }
    candidates: list[bytes] = []
    for index, path in sorted(artifacts.items()):
        if "evp-decrypt-update" not in path.name:
            continue
        update = path.read_bytes()
        for candidate in (update, update + artifacts.get(index + 1, path).read_bytes()):
            try:
                value = load_json(candidate)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and candidate not in candidates:
                candidates.append(candidate)
    return candidates


def recover_vd_plaintexts() -> tuple[list[Path], list[dict]]:
    paths: list[Path] = []
    manifest: list[dict] = []
    for index in range(11):
        directory = VD_RUNTIME / f"record-{index:02d}"
        candidates = runtime_json_candidates(directory)
        unique = sorted({data for data in candidates}, key=len, reverse=True)
        if len(unique) < 2:
            raise ValueError(f"record {index:02d} has only {len(unique)} JSON layer(s)")
        outer, inner = unique[:2]
        record_paths = []
        for layer, data in (("outer", outer), ("inner", inner)):
            value = load_json(data)
            path = OUTPUT / f"vd-record-{index:02d}-{layer}.json"
            write_pretty(path, value)
            paths.append(path)
            record_paths.append(path.name)
        manifest.append({
            "record": index,
            "outputs": record_paths,
            "outer_plaintext_bytes": len(outer),
            "outer_plaintext_sha256": sha256(outer),
            "inner_plaintext_bytes": len(inner),
            "inner_plaintext_sha256": sha256(inner),
        })
    return paths, manifest


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ui_path, ui_manifest = recover_ui_plaintext()
    vd_paths, vd_manifest = recover_vd_plaintexts()
    manifest_path = OUTPUT / "manifest.json"
    write_pretty(manifest_path, {
        "ui_config": ui_manifest,
        "vd_records": vd_manifest,
    })
    print(ui_path)
    for path in vd_paths:
        print(path)
    print(manifest_path)


if __name__ == "__main__":
    main()
