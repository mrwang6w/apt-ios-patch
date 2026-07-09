#!/usr/bin/env python3
"""Reject tar.gz members that require PAX/GNU extensions unsupported by dpkg."""
from __future__ import annotations

import argparse
import gzip
from pathlib import Path


def tar_size(field: bytes) -> int:
    field = field.rstrip(b"\0 ")
    if not field:
        return 0
    if field[0] & 0x80:
        raise ValueError("base-256 tar sizes are not allowed")
    return int(field, 8)


def scan(path: Path) -> None:
    raw = gzip.decompress(path.read_bytes())
    offset = 0
    types: set[str] = set()
    members = 0
    while offset + 512 <= len(raw):
        header = raw[offset : offset + 512]
        if header == b"\0" * 512:
            break
        name = header[:100].split(b"\0", 1)[0].decode("utf-8", "replace")
        typeflag = chr(header[156]) if header[156] else "0"
        if typeflag not in {"0", "5"}:
            raise ValueError(f"{path}: unsupported tar type {typeflag!r} at {name!r}")
        if name.rsplit("/", 1)[-1].startswith("._"):
            raise ValueError(f"{path}: AppleDouble metadata member {name!r}")
        size = tar_size(header[124:136])
        offset += 512 + ((size + 511) // 512) * 512
        types.add(typeflag)
        members += 1
    if not members:
        raise ValueError(f"{path}: no tar members found")
    print(f"{path.name}: members={members} typeflags={','.join(sorted(types))}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args()
    for archive in args.archives:
        scan(archive)


if __name__ == "__main__":
    main()
