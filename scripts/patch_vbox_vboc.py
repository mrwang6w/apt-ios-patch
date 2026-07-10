#!/usr/bin/env python3
"""Patch VBox 5.5's activation, heartbeat, and delayed-exit paths."""

from __future__ import annotations

import argparse
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path


ORIGINAL_SHA256 = "e2aa03f6c409e2b564f5698d06e555f6724f6e903e7ecfccd6dabbe5f478f2d6"
FAT_MAGIC = 0xCAFEBABE
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_MASK = 0x00FFFFFF
CPU_SUBTYPE_ARM64_ALL = 0
CPU_SUBTYPE_ARM64E = 2


@dataclass(frozen=True)
class Patch:
    name: str
    offset: int
    old: bytes
    new: bytes


@dataclass(frozen=True)
class SliceSpec:
    sha256: str
    patches: tuple[Patch, ...]


RET = bytes.fromhex("c0035fd6")
PACIBSP_RETAB = bytes.fromhex("7f2303d5 ff0f5fd6")

SLICES = {
    "arm64": SliceSpec(
        sha256="7ab78851f98116498aadc8d3da10dc583b2a62f4289acd5ceee754078d792ed5",
        patches=(
            Patch("delayed-exit scheduler aaaaavvvvv", 0xB02C, bytes.fromhex("f44fbea9"), RET),
            Patch("60-second delayed-exit closure", 0xB700, bytes.fromhex("ff0301d1"), RET),
            Patch("startAutoHeartbeat", 0xB99C, bytes.fromhex("f44fbea9"), RET),
            Patch("heartbeat timer closure", 0xBED0, bytes.fromhex("ffc300d1"), RET),
            Patch("heartbeat_action", 0xBF6C, bytes.fromhex("ff8300d1"), RET),
            Patch("showActivationAlert", 0xBFAC, bytes.fromhex("f44fbea9"), RET),
        ),
    ),
    "arm64e": SliceSpec(
        sha256="2e39ff684d530b2c05fddb04cc2910020fc146707931081511a6f0a75d33c3db",
        patches=(
            Patch(
                "delayed-exit scheduler aaaaavvvvv",
                0xB8A8,
                bytes.fromhex("7f2303d5 f44fbea9"),
                PACIBSP_RETAB,
            ),
            Patch(
                "60-second delayed-exit closure",
                0xC1A0,
                bytes.fromhex("7f2303d5 ff0301d1"),
                PACIBSP_RETAB,
            ),
            Patch(
                "startAutoHeartbeat",
                0xC480,
                bytes.fromhex("7f2303d5 f44fbea9"),
                PACIBSP_RETAB,
            ),
            Patch(
                "heartbeat timer closure",
                0xCA44,
                bytes.fromhex("7f2303d5 ffc300d1"),
                PACIBSP_RETAB,
            ),
            Patch(
                "heartbeat_action",
                0xCAEC,
                bytes.fromhex("7f2303d5 ff8300d1"),
                PACIBSP_RETAB,
            ),
            Patch(
                "showActivationAlert",
                0xCB40,
                bytes.fromhex("7f2303d5 f44fbea9"),
                PACIBSP_RETAB,
            ),
        ),
    ),
}


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def fat_slices(data: bytes | bytearray) -> dict[str, tuple[int, int]]:
    if len(data) < 8:
        raise SystemExit("source is too small to contain a fat Mach-O header")
    magic, count = struct.unpack_from(">II", data, 0)
    if magic != FAT_MAGIC:
        raise SystemExit(f"unexpected fat Mach-O magic: 0x{magic:08X}")
    if count != 2:
        raise SystemExit(f"expected two architectures, found {count}")

    result: dict[str, tuple[int, int]] = {}
    for index in range(count):
        entry_offset = 8 + index * 20
        if entry_offset + 20 > len(data):
            raise SystemExit("truncated fat architecture table")
        cputype, cpusubtype, offset, size, _align = struct.unpack_from(">IIIII", data, entry_offset)
        if cputype != CPU_TYPE_ARM64:
            raise SystemExit(f"unexpected CPU type in fat slice {index}: 0x{cputype:08X}")
        subtype = cpusubtype & CPU_SUBTYPE_MASK
        if subtype == CPU_SUBTYPE_ARM64_ALL:
            arch = "arm64"
        elif subtype == CPU_SUBTYPE_ARM64E:
            arch = "arm64e"
        else:
            raise SystemExit(f"unexpected arm64 CPU subtype in fat slice {index}: {subtype}")
        if arch in result:
            raise SystemExit(f"duplicate {arch} slice")
        if offset + size > len(data):
            raise SystemExit(f"{arch} slice extends beyond source file")
        result[arch] = (offset, size)

    if set(result) != set(SLICES):
        raise SystemExit(f"unexpected architecture set: {sorted(result)}")
    return result


def patch(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    source_hash = sha256(data)
    if source_hash != ORIGINAL_SHA256:
        raise SystemExit(
            f"unexpected source SHA256: {source_hash}; expected {ORIGINAL_SHA256}"
        )

    slices = fat_slices(data)
    for arch, spec in SLICES.items():
        slice_offset, slice_size = slices[arch]
        slice_hash = sha256(data[slice_offset : slice_offset + slice_size])
        if slice_hash != spec.sha256:
            raise SystemExit(
                f"unexpected {arch} slice SHA256: {slice_hash}; expected {spec.sha256}"
            )
        for item in spec.patches:
            if len(item.old) != len(item.new):
                raise SystemExit(f"{arch} {item.name}: patch changes binary size")
            if item.offset + len(item.old) > slice_size:
                raise SystemExit(f"{arch} {item.name}: patch lies outside slice")
            absolute = slice_offset + item.offset
            actual = bytes(data[absolute : absolute + len(item.old)])
            if actual != item.old:
                raise SystemExit(
                    f"{arch} {item.name}: old-byte mismatch at slice offset "
                    f"0x{item.offset:X}: got {actual.hex()}, expected {item.old.hex()}"
                )
            data[absolute : absolute + len(item.old)] = item.new
            print(
                f"{arch}: {item.name} @ 0x{item.offset:X}: "
                f"{item.old.hex()} -> {item.new.hex()}"
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"patched: {output}")
    print(f"unsigned fat binary SHA256: {sha256(data)}")


def verify_patched(path: Path) -> None:
    data = path.read_bytes()
    slices = fat_slices(data)
    for arch, spec in SLICES.items():
        slice_offset, slice_size = slices[arch]
        for item in spec.patches:
            if item.offset + len(item.new) > slice_size:
                raise SystemExit(f"{arch} {item.name}: patch lies outside slice")
            absolute = slice_offset + item.offset
            actual = data[absolute : absolute + len(item.new)]
            if actual != item.new:
                raise SystemExit(
                    f"{arch} {item.name}: patched-byte mismatch at slice offset "
                    f"0x{item.offset:X}: got {actual.hex()}, expected {item.new.hex()}"
                )
            print(f"{arch}: verified {item.name} @ 0x{item.offset:X}: {actual.hex()}")
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
