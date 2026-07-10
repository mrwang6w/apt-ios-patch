#!/usr/bin/env python3
"""Remove AWZ's injected card-license loader and force the shared auth state."""

from __future__ import annotations

import argparse
import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path


ORIGINAL_AWZZ_SHA256 = (
    "6878500f6a3d0da338b0ffb4dac5d2c445a8b9b1a78293f90351e41d425c0359"
)
CARD_DYLIB_PATH = b"/Applications/AWZ.app/mapsdk.bundle"
ARM64_TRUE_RET = bytes.fromhex("20008052 c0035fd6")
THUMB_TRUE_RET = bytes.fromhex("0120 7047")


@dataclass(frozen=True)
class Patch:
    arch: str
    name: str
    va: int
    slice_file_offset: int
    original_fat_file_offset: int
    old: bytes
    new: bytes


PATCHES = (
    Patch(
        "armv7",
        "shared authorization predicate",
        0x40926,
        0x3C926,
        0x40926,
        bytes.fromhex("f0b503af"),
        THUMB_TRUE_RET,
    ),
    Patch(
        "armv7",
        "global authorization-state getter",
        0xAA970,
        0xA6970,
        0xAA970,
        bytes.fromhex("4ff63420"),
        THUMB_TRUE_RET,
    ),
    Patch(
        "armv7",
        "authorization model status getter",
        0x10DD58,
        0x109D58,
        0x10DD58,
        bytes.fromhex("4cf60801"),
        THUMB_TRUE_RET,
    ),
    Patch(
        "arm64",
        "shared authorization predicate",
        0x100040F2C,
        0x40F2C,
        0x3DCF2C,
        bytes.fromhex("f85fbca9 f65701a9"),
        ARM64_TRUE_RET,
    ),
    Patch(
        "arm64",
        "global authorization-state getter",
        0x1000B0FE8,
        0xB0FE8,
        0x44CFE8,
        bytes.fromhex("881b00b0 008940b9"),
        ARM64_TRUE_RET,
    ),
    Patch(
        "arm64",
        "authorization model status getter",
        0x100121314,
        0x121314,
        0x4BD314,
        bytes.fromhex("081700f0 08298ab9"),
        ARM64_TRUE_RET,
    ),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fat_slice_offsets(data: bytes) -> dict[str, int]:
    if data[:4] != bytes.fromhex("cafebabe"):
        raise ValueError("expected a 32-bit big-endian FAT Mach-O header")
    (count,) = struct.unpack_from(">I", data, 4)
    if count != 2 or 8 + count * 20 > len(data):
        raise ValueError(f"unexpected or truncated FAT architecture table: count={count}")
    result: dict[str, int] = {}
    cpu_names = {12: "armv7", 0x0100000C: "arm64"}
    macho_magics = {
        "armv7": bytes.fromhex("cefaedfe"),
        "arm64": bytes.fromhex("cffaedfe"),
    }
    for index in range(count):
        cputype, _cpusubtype, offset, size, _align = struct.unpack_from(
            ">IIIII", data, 8 + index * 20
        )
        name = cpu_names.get(cputype)
        if name:
            if name in result:
                raise ValueError(f"duplicate FAT architecture: {name}")
            if offset + size > len(data):
                raise ValueError(f"{name} slice exceeds the FAT file")
            if data[offset : offset + 4] != macho_magics[name]:
                raise ValueError(f"{name} slice has an unexpected Mach-O magic")
            result[name] = offset
    if set(result) != {"armv7", "arm64"}:
        raise ValueError(f"unexpected FAT architecture set: {sorted(result)}")
    return result


def verify_patched(data: bytes) -> None:
    if CARD_DYLIB_PATH in data:
        raise ValueError("card-license dylib path is still present")
    if data.count(b"__RESTRICT") != 0:
        raise ValueError("__RESTRICT was not fully neutralized")
    if data.count(b"__XESTRICT") != 4:
        raise ValueError("expected four __XESTRICT header strings")

    slice_offsets = fat_slice_offsets(data)
    for item in PATCHES:
        start = slice_offsets[item.arch] + item.slice_file_offset
        actual = data[start : start + len(item.new)]
        if actual != item.new:
            raise ValueError(
                f"patched-byte mismatch for {item.arch} {item.name} at "
                f"fat offset 0x{start:X}: got {actual.hex()}, "
                f"expected {item.new.hex()}"
            )


def patch(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    source_hash = sha256(data)
    if source_hash != ORIGINAL_AWZZ_SHA256:
        raise SystemExit(
            f"unexpected AWZZ SHA256: {source_hash}; expected {ORIGINAL_AWZZ_SHA256}"
        )
    if CARD_DYLIB_PATH in data:
        raise SystemExit("AWZZ unexpectedly contains the injected mapsdk load path")
    if data.count(b"__RESTRICT") != 4 or data.count(b"__XESTRICT") != 0:
        raise SystemExit("unexpected AWZZ restriction-header layout")
    slice_offsets = fat_slice_offsets(data)

    # Keep substrate injection working while omitting AWZ's added mapsdk load command.
    data[:] = data.replace(b"__RESTRICT", b"__XESTRICT")

    for item in PATCHES:
        start = slice_offsets[item.arch] + item.slice_file_offset
        if start != item.original_fat_file_offset:
            raise SystemExit(
                f"unexpected original FAT layout for {item.arch}: "
                f"0x{start:X} != 0x{item.original_fat_file_offset:X}"
            )
        actual = bytes(data[start : start + len(item.old)])
        if actual != item.old:
            raise SystemExit(
                f"old-byte mismatch for {item.arch} {item.name} at "
                f"fat offset 0x{start:X}: got {actual.hex()}, expected {item.old.hex()}"
            )
        data[start : start + len(item.old)] = item.new

    verify_patched(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)

    print(f"patched: {output}")
    print(f"unsigned SHA256: {sha256(data)}")
    for item in PATCHES:
        print(
            f"{item.arch:5} {item.name}: VA=0x{item.va:X} "
            f"slice_off=0x{item.slice_file_offset:X} "
            f"fat_off=0x{item.original_fat_file_offset:X} "
            f"{item.old.hex()} -> {item.new.hex()}"
        )


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
