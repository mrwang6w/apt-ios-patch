#!/usr/bin/env python3
"""Disable CTW Pro's injected extend.bin license layer at its load boundary."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


ORIGINAL_MAIN_SHA256 = (
    "8f28fe5e4e44f533902ffe4992e91a1a16da7e68aaeae84ee7632cf443ba10bc"
)
LOAD_COMMAND_OFFSET = 0x1440
OLD_PATH = b"@executable_path/extend.bin"
NEW_PATH = b"@executable_path/.nolicense"

LC_LOAD_DYLIB = 0xC
LC_LOAD_WEAK_DYLIB = 0x80000018
DYLIB_COMMAND_SIZE = 0x38
DYLIB_NAME_OFFSET = 0x18


def dylib_command(command: int, path: bytes) -> bytes:
    if len(path) + 1 > DYLIB_COMMAND_SIZE - DYLIB_NAME_OFFSET:
        raise ValueError(f"load path is too long: {path!r}")
    fields = struct.pack(
        "<6I",
        command,
        DYLIB_COMMAND_SIZE,
        DYLIB_NAME_OFFSET,
        2,  # Original linker timestamp.
        0,
        0,
    )
    return fields + (path + b"\0").ljust(DYLIB_COMMAND_SIZE - len(fields), b"\0")


OLD_COMMAND = dylib_command(LC_LOAD_DYLIB, OLD_PATH)
NEW_COMMAND = dylib_command(LC_LOAD_WEAK_DYLIB, NEW_PATH)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_dylibs(data: bytes) -> list[tuple[int, int, bytes]]:
    if len(data) < 32 or data[:4] != bytes.fromhex("cffaedfe"):
        raise ValueError("expected a thin little-endian Mach-O 64 binary")
    (ncmds,) = struct.unpack_from("<I", data, 16)
    (sizeofcmds,) = struct.unpack_from("<I", data, 20)
    if 32 + sizeofcmds > len(data):
        raise ValueError("Mach-O load-command table exceeds the file")

    dylib_commands = {
        LC_LOAD_DYLIB,
        LC_LOAD_WEAK_DYLIB,
        0x20,  # LC_LAZY_LOAD_DYLIB
        0x8000001F,  # LC_REEXPORT_DYLIB
        0x80000023,  # LC_LOAD_UPWARD_DYLIB
    }
    result: list[tuple[int, int, bytes]] = []
    offset = 32
    for _index in range(ncmds):
        if offset + 8 > 32 + sizeofcmds:
            raise ValueError("truncated Mach-O load command")
        command, command_size = struct.unpack_from("<2I", data, offset)
        if command_size < 8 or offset + command_size > 32 + sizeofcmds:
            raise ValueError(f"invalid Mach-O load command size at 0x{offset:X}")
        if command in dylib_commands:
            if command_size < 24:
                raise ValueError(f"truncated dylib command at 0x{offset:X}")
            (name_offset,) = struct.unpack_from("<I", data, offset + 8)
            if name_offset >= command_size:
                raise ValueError(f"invalid dylib name offset at 0x{offset:X}")
            start = offset + name_offset
            end = data.find(b"\0", start, offset + command_size)
            if end < 0:
                raise ValueError(f"unterminated dylib name at 0x{offset:X}")
            result.append((offset, command, bytes(data[start:end])))
        offset += command_size
    if offset != 32 + sizeofcmds:
        raise ValueError("Mach-O load commands do not consume sizeofcmds")
    return result


def verify_patched(data: bytes) -> None:
    actual = data[LOAD_COMMAND_OFFSET : LOAD_COMMAND_OFFSET + len(NEW_COMMAND)]
    if actual != NEW_COMMAND:
        raise ValueError(
            f"patched load-command mismatch at 0x{LOAD_COMMAND_OFFSET:X}: "
            f"got {actual.hex()}, expected {NEW_COMMAND.hex()}"
        )
    if OLD_PATH in data:
        raise ValueError("the required extend.bin load path is still present")
    if data.count(NEW_PATH) != 1:
        raise ValueError(
            f"unexpected weak replacement path count: {data.count(NEW_PATH)}"
        )

    matches = [item for item in load_dylibs(data) if item[2] in {OLD_PATH, NEW_PATH}]
    expected = [(LOAD_COMMAND_OFFSET, LC_LOAD_WEAK_DYLIB, NEW_PATH)]
    if matches != expected:
        raise ValueError(f"unexpected extend load-command state: {matches!r}")


def patch(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    source_hash = sha256(data)
    if source_hash != ORIGINAL_MAIN_SHA256:
        raise SystemExit(
            f"unexpected CTW Pro SHA256: {source_hash}; expected {ORIGINAL_MAIN_SHA256}"
        )
    actual = bytes(data[LOAD_COMMAND_OFFSET : LOAD_COMMAND_OFFSET + len(OLD_COMMAND)])
    if actual != OLD_COMMAND:
        raise SystemExit(
            f"old load-command mismatch at 0x{LOAD_COMMAND_OFFSET:X}: "
            f"got {actual.hex()}, expected {OLD_COMMAND.hex()}"
        )
    matches = [item for item in load_dylibs(data) if item[2] == OLD_PATH]
    if matches != [(LOAD_COMMAND_OFFSET, LC_LOAD_DYLIB, OLD_PATH)]:
        raise SystemExit(f"unexpected original extend load-command state: {matches!r}")

    data[LOAD_COMMAND_OFFSET : LOAD_COMMAND_OFFSET + len(OLD_COMMAND)] = NEW_COMMAND
    verify_patched(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)

    print(f"patched: {output}")
    print(f"unsigned SHA256: {sha256(data)}")
    print(
        f"arm64 load command: file_off=0x{LOAD_COMMAND_OFFSET:X} "
        f"{OLD_COMMAND[:4].hex()} -> {NEW_COMMAND[:4].hex()}"
    )
    print(
        f"arm64 load path: file_off=0x{LOAD_COMMAND_OFFSET + DYLIB_NAME_OFFSET:X} "
        f"{OLD_PATH.decode()} -> {NEW_PATH.decode()}"
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
