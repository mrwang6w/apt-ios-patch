#!/usr/bin/env python3
"""Insert and verify CTW Pro's strong fix.dylib load command."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


ORIGINAL_MAIN_SHA256 = (
    "00b2494dcca8c759fb2c77c40beb6df027436bf49827d84554255e11618407f5"
)
LOAD_COMMAND_OFFSET = 0x1440
MOVED_CODE_SIGNATURE_OFFSET = 0x1478
LC_LOAD_DYLIB = 0xC
LC_CODE_SIGNATURE = 0x1D
DYLIB_COMMAND_SIZE = 0x38
DYLIB_NAME_OFFSET = 0x18
FIX_PATH = b"@executable_path/fix.dylib"
NOP = bytes.fromhex("1f2003d5")
EXIT_SETUP = bytes.fromhex("200180d2300080d2")

# performeMachineStub is registered at 0x53DE04 and ends before
# performeMachine: at 0x546CD4. These are all direct exit(9) syscall
# instructions in that exact function; the surrounding state machine remains.
STUB_EXIT_SYSCALLS = {
    0x53DEEC: bytes.fromhex("812705d4"),
    0x53E2AC: bytes.fromhex("214d08d4"),
    0x53EB9C: bytes.fromhex("214d08d4"),
    0x53ED70: bytes.fromhex("c1ae08d4"),
    0x53F0D0: bytes.fromhex("c1ae08d4"),
    0x53F280: bytes.fromhex("017517d4"),
    0x53F3B4: bytes.fromhex("81db18d4"),
    0x53F650: bytes.fromhex("81db18d4"),
    0x53F878: bytes.fromhex("e14808d4"),
    0x53FD78: bytes.fromhex("81f21dd4"),
    0x53FF78: bytes.fromhex("81f21dd4"),
    0x5400E8: bytes.fromhex("815819d4"),
    0x540774: bytes.fromhex("813b09d4"),
    0x541068: bytes.fromhex("813b09d4"),
    0x541270: bytes.fromhex("41ce01d4"),
    0x541324: bytes.fromhex("41ce01d4"),
    0x541E8C: bytes.fromhex("a18318d4"),
    0x542154: bytes.fromhex("815200d4"),
    0x5421A0: bytes.fromhex("a18318d4"),
    0x5421F4: bytes.fromhex("815200d4"),
    0x543C64: bytes.fromhex("41cf03d4"),
    0x544918: bytes.fromhex("41cf03d4"),
    0x545D7C: bytes.fromhex("817f01d4"),
    0x545F68: bytes.fromhex("817f01d4"),
}

# These are the main-executable IMPs checked by CTWProDeepPatch.m. The hashes
# bind this injector to the exact implementation that was runtime-tested.
EXPECTED_IMP_SHA256 = {
    0x4DCCB0: "8f7df076267d16a839440bcd5af6a1156acd90c49b872f78907e2d38b12e2db4",
    0x4E1C8C: "dc8d58baa8fe34af72ec48128bb720d93f7f8e20286cc98bbaf9208cc159e55d",
    0x4E2530: "61dc1a732031e463f1b9163aff6cc739f6190b38e63df7734435e560e1d1c75b",
    0x4E6700: "b560e0838b1b91475c394f714f4c501af178a4e71dd28f849d94051396a96feb",
    0x5025C0: "08354da1328853dc268a4b22ae3365b301af15950f78364cb3b8a25d67bf8830",
    0x50C684: "31165d4c6138ce111cc21309ce2b479ddb432ee2ca9dcfd9200aa6de6fd40bcc",
    0x515AF0: "46e5cb6af29ff0bee4245e277bf99c569a7bd5c3fca3c0ef0503bb3e0bfeb9b6",
    0x557560: "3a97c2b0d7f781cea1deed54a759927d2a8d43724dbbba71c852573828bb7de1",
    0x557BC0: "7861ee01e2b7c798716b0a6659a8ad5ebed09c9dc2052226d560ef4fe6bbed8b",
    0x56CFB0: "f4ad079b5a5ffbe24f889ab3e61220ce3cb6d31f341bda69649dfda5e9e5e687",
    0x56D67C: "18d36a23f63b4356df96b96b379501f54f4d1247c22dd198b926817f2998862d",
    0x56DD44: "1b906e1bfe0d56e753fc64e312d7455abd1ba3b678d86492e905c1ca09d48554",
    0x56E438: "60f9de43b60519054865d0f474db8ae8b869647a4419677a3da09b1fff0762bf",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dylib_command(path: bytes) -> bytes:
    if len(path) + 1 > DYLIB_COMMAND_SIZE - DYLIB_NAME_OFFSET:
        raise ValueError(f"load path is too long: {path!r}")
    fields = struct.pack(
        "<6I",
        LC_LOAD_DYLIB,
        DYLIB_COMMAND_SIZE,
        DYLIB_NAME_OFFSET,
        2,
        0,
        0,
    )
    return fields + (path + b"\0").ljust(DYLIB_COMMAND_SIZE - len(fields), b"\0")


FIX_COMMAND = dylib_command(FIX_PATH)


def load_commands(data: bytes) -> list[tuple[int, int, bytes]]:
    if len(data) < 32 or data[:4] != bytes.fromhex("cffaedfe"):
        raise ValueError("expected a thin little-endian Mach-O 64 binary")
    ncmds, sizeofcmds = struct.unpack_from("<2I", data, 16)
    end = 32 + sizeofcmds
    if end > len(data):
        raise ValueError("Mach-O load-command table exceeds the file")

    result: list[tuple[int, int, bytes]] = []
    offset = 32
    for _index in range(ncmds):
        if offset + 8 > end:
            raise ValueError(f"truncated load command at 0x{offset:X}")
        command, command_size = struct.unpack_from("<2I", data, offset)
        if command_size < 8 or offset + command_size > end:
            raise ValueError(f"invalid load command at 0x{offset:X}")
        result.append((offset, command, bytes(data[offset : offset + command_size])))
        offset += command_size
    if offset != end:
        raise ValueError("load commands do not consume sizeofcmds")
    return result


def verify_imp_bytes(data: bytes) -> None:
    for offset, expected in EXPECTED_IMP_SHA256.items():
        if offset + 64 > len(data):
            raise ValueError(f"IMP window exceeds binary at 0x{offset:X}")
        actual = sha256(data[offset : offset + 64])
        if actual != expected:
            raise ValueError(
                f"IMP byte mismatch at 0x{offset:X}: got {actual}, expected {expected}"
            )


def verify_original_stub_exits(data: bytes) -> None:
    for offset, expected in STUB_EXIT_SYSCALLS.items():
        if data[offset - len(EXIT_SETUP) : offset] != EXIT_SETUP:
            raise ValueError(f"exit(9) setup mismatch at 0x{offset - 8:X}")
        actual = data[offset : offset + len(expected)]
        if actual != expected:
            raise ValueError(
                f"exit syscall mismatch at 0x{offset:X}: "
                f"got {actual.hex()}, expected {expected.hex()}"
            )


def verify_patched_stub_exits(data: bytes) -> None:
    for offset in STUB_EXIT_SYSCALLS:
        if data[offset - len(EXIT_SETUP) : offset] != EXIT_SETUP:
            raise ValueError(f"patched exit(9) setup mismatch at 0x{offset - 8:X}")
        if data[offset : offset + len(NOP)] != NOP:
            raise ValueError(f"exit syscall remains at 0x{offset:X}")


def verify_patched(data: bytes) -> None:
    verify_imp_bytes(data)
    verify_patched_stub_exits(data)
    commands = load_commands(data)
    matches = [
        item for item in commands if item[1] == LC_LOAD_DYLIB and FIX_PATH in item[2]
    ]
    if len(matches) != 1 or matches[0][0] != LOAD_COMMAND_OFFSET:
        raise ValueError(f"unexpected fix.dylib load commands: {matches!r}")
    if data[LOAD_COMMAND_OFFSET : LOAD_COMMAND_OFFSET + DYLIB_COMMAND_SIZE] != FIX_COMMAND:
        raise ValueError("fix.dylib load command bytes differ")
    code_signatures = [item for item in commands if item[1] == LC_CODE_SIGNATURE]
    if len(code_signatures) != 1 or code_signatures[0][0] != MOVED_CODE_SIGNATURE_OFFSET:
        raise ValueError(f"unexpected LC_CODE_SIGNATURE state: {code_signatures!r}")
    if commands[-1] != code_signatures[0]:
        raise ValueError("LC_CODE_SIGNATURE is not the final load command")


def patch(source: Path, output: Path) -> None:
    data = bytearray(source.read_bytes())
    actual_hash = sha256(data)
    if actual_hash != ORIGINAL_MAIN_SHA256:
        raise SystemExit(
            f"unexpected CTW Pro SHA256: {actual_hash}; expected {ORIGINAL_MAIN_SHA256}"
        )
    verify_imp_bytes(data)
    verify_original_stub_exits(data)

    commands = load_commands(data)
    final_offset, final_command, final_bytes = commands[-1]
    if (final_offset, final_command, len(final_bytes)) != (
        LOAD_COMMAND_OFFSET,
        LC_CODE_SIGNATURE,
        0x10,
    ):
        raise SystemExit(
            f"unexpected final load command: offset=0x{final_offset:X}, "
            f"command=0x{final_command:X}, size=0x{len(final_bytes):X}"
        )
    padding_start = LOAD_COMMAND_OFFSET + len(final_bytes)
    padding_end = MOVED_CODE_SIGNATURE_OFFSET + len(final_bytes)
    if any(data[padding_start:padding_end]):
        raise SystemExit("load-command insertion padding is not empty")

    ncmds, sizeofcmds = struct.unpack_from("<2I", data, 16)
    struct.pack_into("<2I", data, 16, ncmds + 1, sizeofcmds + DYLIB_COMMAND_SIZE)
    data[LOAD_COMMAND_OFFSET : LOAD_COMMAND_OFFSET + DYLIB_COMMAND_SIZE] = FIX_COMMAND
    data[
        MOVED_CODE_SIGNATURE_OFFSET : MOVED_CODE_SIGNATURE_OFFSET + len(final_bytes)
    ] = final_bytes
    for offset in STUB_EXIT_SYSCALLS:
        data[offset : offset + len(NOP)] = NOP
    verify_patched(data)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    print(f"patched: {output}")
    print(f"unsigned SHA256: {sha256(data)}")
    print(f"inserted LC_LOAD_DYLIB at 0x{LOAD_COMMAND_OFFSET:X}: {FIX_PATH.decode()}")
    print(f"disabled performeMachineStub exit(9) syscalls: {len(STUB_EXIT_SYSCALLS)}")


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
