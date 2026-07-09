#!/usr/bin/env python3
"""Create a deterministic Debian ar container without requiring GNU ar."""

from __future__ import annotations

import argparse
from pathlib import Path


AR_MAGIC = b"!<arch>\n"


def ar_member(name: str, data: bytes) -> bytes:
    if not name or len(name.encode("ascii")) > 15:
        raise ValueError(f"ar member name must be 1-15 ASCII bytes: {name!r}")
    header = (
        f"{name:<16}"
        f"{0:<12}"
        f"{0:<6}"
        f"{0:<6}"
        f"{0o100644:<8o}"
        f"{len(data):<10}"
        "`\n"
    ).encode("ascii")
    if len(header) != 60:
        raise AssertionError(f"invalid ar header length: {len(header)}")
    return header + data + (b"\n" if len(data) % 2 else b"")


def build(output: Path, members: list[Path]) -> None:
    payload = bytearray(AR_MAGIC)
    for member in members:
        payload.extend(ar_member(member.name, member.read_bytes()))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(f"built: {output} ({len(payload)} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("members", nargs="+", type=Path)
    args = parser.parse_args()
    build(args.output, args.members)


if __name__ == "__main__":
    main()
