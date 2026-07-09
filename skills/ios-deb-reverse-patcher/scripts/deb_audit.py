#!/usr/bin/env python3
"""Quick triage for iOS jailbreak .deb packages.

Outputs hashes, control metadata, payload tree, Mach-O candidates, and strings hints.
Only extracts into the requested --out directory; never modifies the input deb.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HINT_RE = re.compile(
    r"激活|注册|试用|到期|卡密|授权|过期|心跳|"
    r"heartbeat|heart|timer|expire|expiry|trial|license|activate|register|"
    r"exit|abort|kill|crash|url|session|http|https|api|token|udid|device",
    re.IGNORECASE,
)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(256).startswith(b"version https://git-lfs.github.com/spec/")


def parse_control(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        if not line:
            continue
        if line[0].isspace() and current:
            fields[current] += "\n" + line
            continue
        key, sep, value = line.partition(":")
        if sep:
            current = key
            fields[key] = value.strip()
    return fields


def safe_extract_tar(tar_path: Path, dest: Path) -> None:
    """Extract tar into dest while rejecting traversal and unsafe links."""
    base = dest.resolve()
    with tarfile.open(tar_path) as tf:
        for member in tf.getmembers():
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise RuntimeError(f"unsafe tar member path: {member.name}")
            target = (dest / member.name).resolve()
            try:
                target.relative_to(base)
            except ValueError as exc:
                raise RuntimeError(f"unsafe tar member path: {member.name}") from exc
            if member.islnk() or member.issym():
                link_target = Path(member.linkname)
                if link_target.is_absolute() or ".." in link_target.parts:
                    raise RuntimeError(f"unsafe tar link target: {member.name} -> {member.linkname}")
        try:
            tf.extractall(dest, filter="data")
        except TypeError:
            tf.extractall(dest)


def extract_deb(deb: Path, out: Path) -> tuple[Path, Path, list[str]]:
    raw = out / "raw"
    root = out / "rootfs"
    control = out / "control"
    for p in [raw, root, control]:
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True)

    run(["ar", "x", str(deb.resolve())], cwd=raw)
    members = sorted(p.name for p in raw.iterdir())
    data_tar = next((raw / m for m in members if m.startswith("data.tar")), None)
    control_tar = next((raw / m for m in members if m.startswith("control.tar")), None)
    if not data_tar or not control_tar:
        raise RuntimeError(f"missing data/control tar in {deb}")
    safe_extract_tar(data_tar, root)
    safe_extract_tar(control_tar, control)
    return root, control, members


def file_type(path: Path) -> str:
    try:
        return run(["file", "-b", str(path)], check=False).stdout.strip()
    except Exception as e:
        return f"file-error: {e}"


def collect_tree(root: Path) -> list[str]:
    rows: list[str] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            rows.append(f"L {rel} -> {os.readlink(p)}")
        elif p.is_dir():
            rows.append(f"D {rel}/")
        else:
            rows.append(f"F {rel} {p.stat().st_size}")
    return rows


def collect_macho(root: Path) -> list[dict[str, str | int]]:
    rows = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        ft = file_type(p)
        if any(x in ft for x in ["Mach-O", "universal binary", "dynamically linked shared library"]):
            rel = p.relative_to(root).as_posix()
            rows.append({"path": rel, "size": p.stat().st_size, "file": ft, "sha256": sha256(p)})
    return rows


def collect_strings_hints(root: Path, limit_per_file: int = 80) -> str:
    chunks: list[str] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.stat().st_size > 80 * 1024 * 1024:
            continue
        ft = file_type(p)
        if "Mach-O" not in ft and "text" not in ft and p.suffix.lower() not in {".plist", ".strings", ".json", ".js"}:
            continue
        proc = run(["strings", "-a", str(p)], check=False)
        hits: list[str] = []
        for line in proc.stdout.splitlines():
            if HINT_RE.search(line):
                hits.append(line)
                if len(hits) >= limit_per_file:
                    break
        if hits:
            chunks.append(f"### {p.relative_to(root).as_posix()}\n" + "\n".join(hits) + "\n")
    return "\n".join(chunks)


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit an iOS jailbreak deb package")
    ap.add_argument("deb", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    deb = args.deb.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not deb.exists():
        print(f"missing deb: {deb}", file=sys.stderr)
        return 2

    meta = {"path": str(deb), "size": deb.stat().st_size, "sha256": sha256(deb), "lfs_pointer": is_lfs_pointer(deb)}
    (out / "deb.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    if meta["lfs_pointer"]:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print("input is a Git LFS pointer; cannot extract", file=sys.stderr)
        return 3

    root, control_dir, ar_members = extract_deb(deb, out)
    control_file = control_dir / "control"
    control = parse_control(control_file.read_text(errors="replace")) if control_file.exists() else {}
    (out / "control.json").write_text(json.dumps(control, ensure_ascii=False, indent=2) + "\n")
    (out / "ar-members.txt").write_text("\n".join(ar_members) + "\n")
    (out / "tree.txt").write_text("\n".join(collect_tree(root)) + "\n")
    (out / "macho.json").write_text(json.dumps(collect_macho(root), ensure_ascii=False, indent=2) + "\n")
    (out / "strings-hints.txt").write_text(collect_strings_hints(root) + "\n")

    summary = {
        "deb": meta,
        "control": {k: control.get(k) for k in ["Package", "Name", "Version", "Architecture", "Section"] if k in control},
        "outputs": ["deb.json", "control.json", "ar-members.txt", "tree.txt", "macho.json", "strings-hints.txt", "rootfs/", "control/"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
