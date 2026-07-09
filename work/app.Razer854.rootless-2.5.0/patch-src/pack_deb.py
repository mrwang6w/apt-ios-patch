#!/usr/bin/env python3
"""Write the three-member Unix ar archive used by a Debian .deb package."""
from __future__ import annotations

import argparse
from pathlib import Path


def member_header(name: str, size: int) -> bytes:
    fields = [
        name.encode("ascii").ljust(16, b" "),
        b"0".ljust(12, b" "),
        b"0".ljust(6, b" "),
        b"0".ljust(6, b" "),
        b"100644".ljust(8, b" "),
        str(size).encode("ascii").ljust(10, b" "),
        b"`\n",
    ]
    header = b"".join(fields)
    if len(header) != 60:
        raise ValueError(f"invalid ar header length for {name}: {len(header)}")
    return header


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("debian_binary", type=Path)
    parser.add_argument("control_tar", type=Path)
    parser.add_argument("data_tar", type=Path)
    args = parser.parse_args()

    members = [
        ("debian-binary", args.debian_binary),
        ("control.tar.gz", args.control_tar),
        ("data.tar.gz", args.data_tar),
    ]
    with args.output.open("xb") as out:
        out.write(b"!<arch>\n")
        for name, path in members:
            data = path.read_bytes()
            out.write(member_header(name, len(data)))
            out.write(data)
            if len(data) & 1:
                out.write(b"\n")


if __name__ == "__main__":
    main()
