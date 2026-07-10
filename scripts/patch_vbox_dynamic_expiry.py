#!/usr/bin/env python3
"""Patch VBox 5.5's main-program expiry UI and home-page expiry label."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ORIGINAL_SHA256 = "ad38cd8e805e9781a2528a239cfbab7aba58f80857fed576cc3c9d03a01e6f31"
SECONDS_100Y_CURRENT_WINDOW = 3_155_673_600  # 36524 days: 2026-07-10 -> 2126-07-10

PATCHES = {
    0x500E5C: (
        bytes.fromhex("f44fbea9"),
        bytes.fromhex("c0035fd6"),
    ),
    0x5F6ED4: (
        bytes.fromhex(
            "006969f8 481900d0 01fd41f9 1f810a94 "
            "604e40f9 481900d0 017d41f9 1b810a94"
        ),
        bytes.fromhex(
            "604e40f9 08409852 e882b772 0001631e "
            "481900d0 018141f9 1f2003d5 1b810a94"
        ),
    ),
    0x5F7FB4: (
        bytes.fromhex(
            "006969f8 481900b0 01fd41f9 e77c0a94 "
            "601e40f9 481900b0 017d41f9 e37c0a94"
        ),
        bytes.fromhex(
            "601e40f9 08409852 e882b772 0001631e "
            "481900b0 018141f9 1f2003d5 e37c0a94"
        ),
    ),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    source_hash = sha256(data)
    if source_hash != ORIGINAL_SHA256:
        raise SystemExit(
            f"unexpected source SHA256: {source_hash}; expected {ORIGINAL_SHA256}"
        )

    for offset, (old, new) in PATCHES.items():
        actual = bytes(data[offset : offset + len(old)])
        if actual != old:
            raise SystemExit(
                f"old-byte mismatch at file offset 0x{offset:X}: "
                f"got {actual.hex()}, expected {old.hex()}"
            )
        data[offset : offset + len(old)] = new

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"patched: {output}")
    print(f"seconds from now: {SECONDS_100Y_CURRENT_WINDOW}")
    print(f"unsigned binary SHA256: {sha256(data)}")


def verify_patched(path: Path) -> None:
    data = path.read_bytes()
    for offset, (_old, new) in PATCHES.items():
        actual = data[offset : offset + len(new)]
        if actual != new:
            raise SystemExit(
                f"patched-byte mismatch at file offset 0x{offset:X}: "
                f"got {actual.hex()}, expected {new.hex()}"
            )
        print(f"verified VBox main patch @ 0x{offset:X}: {actual.hex()}")
    print(f"verified patched binary: {path}")
    print(f"patched binary SHA256: {sha256(data)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path, metavar="PATCHED")
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    args = parser.parse_args()
    if args.verify is not None:
        if args.source is not None or args.output is not None:
            parser.error("--verify cannot be combined with source/output")
        verify_patched(args.verify)
        return
    if args.source is None or args.output is None:
        parser.error("source and output are required unless --verify is used")
    patch(args.source, args.output)


if __name__ == "__main__":
    main()
