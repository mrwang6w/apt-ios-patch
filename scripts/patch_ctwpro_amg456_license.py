#!/usr/bin/env python3
"""Patch and verify CTW Pro 5.6.0's injected online-license layer."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ORIGINAL_SHA256 = "e8a554baaa1f7e431ab98baf601ab7fdc0c9fb8a3cc019da959e455012e8c97a"
RET = bytes.fromhex("c0035fd6")

PATCHES = (
    (
        0x11920,
        bytes.fromhex("ff4301d1fd7b04a9"),
        bytes.fromhex("20008052c0035fd6"),
        "authorization getter -> true",
    ),
    (
        0x1315C,
        bytes.fromhex("fc6fbda9"),
        RET,
        "disable initial authorization request",
    ),
    (0x13CF4, bytes.fromhex("f44fbea9"), RET, "disable heartbeat scheduler"),
    (0x143A8, bytes.fromhex("ff0301d1"), RET, "disable queued heartbeat callback"),
    (0x1441C, bytes.fromhex("f44fbea9"), RET, "disable activation dialog"),
    (
        0x15378,
        bytes.fromhex("f44fbea9"),
        RET,
        "disable authorization network-error dialog",
    ),
    (
        0x16ED0,
        bytes.fromhex("f44fbea9"),
        RET,
        "disable activation request/response path",
    ),
    (
        0x17280,
        bytes.fromhex("f44fbea9"),
        RET,
        "disable authorization alert-and-exit path",
    ),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_patched(data: bytes) -> None:
    for offset, _old, new, reason in PATCHES:
        actual = bytes(data[offset : offset + len(new)])
        if actual != new:
            raise ValueError(
                f"patch mismatch at 0x{offset:X} ({reason}): "
                f"expected {new.hex()}, got {actual.hex()}"
            )


def patch(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    digest = sha256(data)
    if digest != ORIGINAL_SHA256:
        raise SystemExit(f"unexpected CTW.dylib SHA256: {digest}")

    for offset, old, new, reason in PATCHES:
        actual = bytes(data[offset : offset + len(old)])
        if actual != old:
            raise SystemExit(
                f"old-byte mismatch at 0x{offset:X}: "
                f"expected {old.hex()}, got {actual.hex()}"
            )
        if len(old) != len(new):
            raise SystemExit(f"patch size mismatch at 0x{offset:X}")
        data[offset : offset + len(new)] = new
        print(f"0x{offset:06x}: {old.hex()} -> {new.hex()}  {reason}")

    verify_patched(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"patched: {output}")
    print(f"unsigned SHA256: {sha256(data)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    patch_parser = subparsers.add_parser("patch")
    patch_parser.add_argument("source", type=Path)
    patch_parser.add_argument("output", type=Path)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("binary", type=Path)

    args = parser.parse_args()
    if args.command == "patch":
        patch(args.source, args.output)
    else:
        data = args.binary.read_bytes()
        verify_patched(data)
        print(f"verified: {args.binary}")
        print(f"SHA256: {sha256(data)}")


if __name__ == "__main__":
    main()
