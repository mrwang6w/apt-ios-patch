#!/usr/bin/env python3
"""Build a static GitHub Pages Cydia/Sileo repo from patched deb artifacts.

The published APT metadata intentionally mounts one final patched deb per
completed target from ``patched/``. Intermediate patch artifacts are kept out of
the Pages repo.

All display frontend and APT static files are generated under ``pages-repo/``.
GitHub Pages should publish ``pages-repo/`` as the artifact root, so the public
URL is mounted at ``https://<user>.github.io/<repo>/`` without a ``/pages-repo/``
path segment.
"""
from __future__ import annotations

import gzip
import hashlib
import html
import json
import os
import shutil
import subprocess
import zlib
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PATCHED_DIR = ROOT / "patched"
DOWNLOADS_DIR = ROOT / "downloads" / "amg456-repo"
SOURCE_MANIFEST = DOWNLOADS_DIR / "manifest.json"
SOURCE_PACKAGES = DOWNLOADS_DIR / "Packages"
OUT = ROOT / "pages-repo"

ORIGINAL_REPO_NAME = "AMG官方源™"
ORIGINAL_REPO_DESC = "AMG唯一正版官方源"
REPO_NAME = "AMG官方源™ Patch Repo"
REPO_DESC = "自用授权测试源：Pages 挂载已完成目标的最终 patched 补丁 deb，不发布中间态补丁包或原始源全量资源。"
PUBLISH_MAINTAINER = "Local Patch Repo"
PUBLISH_AUTHOR = "Local Patch Repo"
SOURCE_LAST_UPDATED = "2026-07-08 19:44:22"
DEFAULT_SOURCE_DATE_EPOCH = 1783511062

CONTROL_PASSTHROUGH_FIELDS = (
    "Package",
    "Version",
    "Essential",
    "Installed-Size",
    "Priority",
    "Pre-Depends",
    "Depends",
    "Recommends",
    "Suggests",
    "Breaks",
    "Conflicts",
    "Provides",
    "Replaces",
    "Enhances",
    "Architecture",
    "Multi-Arch",
)

PATCHED_PACKAGES = [
    {
        "package_id": "com.amg456.rootless",
        "source": PATCHED_DIR / "纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat_noexit.deb",
        "deb_name": "com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb",
        "publish_name": "纯净版18.1.1_AMG奔驰正版[无根] Patch NoExit",
        "publish_section": "AMG",
        "publish_desc": "授权测试补丁包：去除首页激活弹窗，将试用过期时间调整为 2099，禁用周期心跳检测，并移除延迟退出路径。",
        "depiction_name": "com.amg456.rootless.html",
    },
    {
        "package_id": "app.Razer854.rootless",
        "source": PATCHED_DIR / "2.5.0_Razer雷蛇(无根)_2.5.0-11_app.Razer854.rootless_authstate_ustar.deb",
        "deb_name": "app.Razer854.rootless_2.5.0-11_authstate_ustar.deb",
        "publish_name": "2.5.0-11_Razer雷蛇(无根) Patch AuthState USTAR",
        "publish_section": "Razer雷蛇",
        "publish_desc": "授权测试补丁包：恢复原始主面板 action 与授权 UI 调用链；运行期覆盖具体 NSDictionary 类簇的授权响应状态与 2099 过期时间，并使用无 PAX 扩展头的 USTAR deb 归档。",
        "depiction_name": "app.Razer854.rootless.html",
    },
    {
        "package_id": "com.amg456.VBox1",
        "source": PATCHED_DIR / "VBox_5.5「无根」_5.5-6_com.amg456.VBox1_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb",
        "deb_name": "com.amg456.VBox1_5.5-6_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb",
        "publish_name": "VBox_5.5「无根」 Patch NoLicense NoTrialGate NoHeartbeat Dynamic 100Y USTAR",
        "publish_section": "VBox虚拟盒子",
        "publish_desc": "授权测试补丁包：禁用主程序将 iOS 15 兼容性结果误判为软件过期的 pGflauxabac 保护链，并禁用注入层激活/网络错误弹窗、周期心跳及延迟退出；首页授权时间动态显示为设备当前时间加 100 年；使用无 PAX 扩展头的 USTAR deb 归档。",
        "depiction_name": "com.amg456.VBox1.html",
    },
    {
        "package_id": "app.awz4854.rootful",
        "source": PATCHED_DIR / "AWZ爱伪装_修复(有根)_15.0.1-1_app.awz4854.rootful_nolicense_ustar.deb",
        "deb_name": "app.awz4854.rootful_15.0.1-1_nolicense_ustar.deb",
        "publish_name": "AWZ爱伪装_修复(有根) 15.0.1-1 Patch NoLicense USTAR",
        "publish_section": "AWZ爱伪装",
        "publish_desc": "授权测试补丁包：移除后加卡密网络层与安装阶段 aloader 注入调用；双架构固定共享授权状态为有效，并使用无 PAX 扩展头的 USTAR deb 归档。",
        "depiction_name": "app.awz4854.rootful.html",
    },
    {
        "package_id": "com.xxdevice.CTWPro.Rootless560",
        "source": PATCHED_DIR / "CTW_Pro企业级(无根版)_5.6.0-1_com.xxdevice.CTWPro.Rootless560_nolicense_ustar.deb",
        "deb_name": "com.xxdevice.CTWPro.Rootless560_5.6.0-1_nolicense_ustar.deb",
        "publish_name": "CTW Pro企业级(无根版) 5.6.0-1 Patch NoLicense USTAR",
        "publish_section": "CTW Pro",
        "publish_desc": "授权测试补丁包：解除后加 extend.bin 卡密网络层的强制装载，移除其 constructor、NSURLSession、swizzle 与 exit/_exit/kill interpose；保留原业务与 entitlements，并使用无 PAX 扩展头的 USTAR deb 归档。",
        "depiction_name": "com.xxdevice.CTWPro.Rootless560.html",
    },
]


def h(value: object) -> str:
    return html.escape(str(value), quote=True)


def run(cmd: list[str], cwd: Path | None = None) -> bytes:
    return subprocess.check_output(cmd, cwd=str(cwd) if cwd else None)


def parse_deb_control_text(text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        fields: dict[str, str] = {}
        current: str | None = None
        for line in block.splitlines():
            if not line:
                continue
            if line[0].isspace() and current:
                fields[current] += "\n" + line
                continue
            key, sep, value = line.partition(":")
            if not sep:
                continue
            current = key
            fields[key] = value.strip()
        if fields:
            records.append(fields)
    return records


def extract_control(deb: Path, tmp: Path) -> dict[str, str]:
    deb = deb.resolve()
    tmp = tmp.resolve()
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    run(["ar", "-x", str(deb)], cwd=tmp)
    control_tar = next((p for p in tmp.iterdir() if p.name.startswith("control.tar")), None)
    if not control_tar:
        raise RuntimeError(f"control.tar not found in {deb}")
    control_dir = tmp / "control"
    control_dir.mkdir()
    run(["tar", "-xf", str(control_tar), "-C", str(control_dir)])
    control_file = control_dir / "control"
    records = parse_deb_control_text(control_file.read_text(encoding="utf-8"))
    if len(records) != 1:
        raise RuntimeError(f"{deb}: expected one control record, found {len(records)}")
    return records[0]


def _tar_member_size(header: bytes) -> int:
    field = header[124:136].rstrip(b"\0 ")
    if not field or field[0] & 0x80:
        raise RuntimeError("unsupported tar size encoding")
    return int(field, 8)


def _validate_tar_gzip(path: Path) -> None:
    """Reject tar extensions that the target device's dpkg cannot unpack."""
    with gzip.open(path, "rb") as fh:
        raw = fh.read()
    offset = 0
    members = 0
    while offset + 512 <= len(raw):
        header = raw[offset : offset + 512]
        if header == b"\0" * 512:
            break
        prefix = header[345:500].split(b"\0", 1)[0]
        name = header[:100].split(b"\0", 1)[0]
        full_name = b"/".join(part for part in (prefix, name) if part).decode("utf-8", "replace")
        typeflag = header[156:157] or b"0"
        if typeflag in {b"x", b"g", b"e"}:
            raise RuntimeError(f"{path}: unsupported PAX/extended tar member {full_name!r} ({typeflag!r})")
        if full_name.rsplit("/", 1)[-1].startswith("._"):
            raise RuntimeError(f"{path}: AppleDouble metadata member {full_name!r}")
        offset += 512 + ((_tar_member_size(header) + 511) // 512) * 512
        members += 1
    if not members:
        raise RuntimeError(f"{path}: no tar members")


def validate_deb_archive(deb: Path, tmp: Path) -> None:
    """Validate every published deb before metadata makes it installable."""
    deb = deb.resolve()
    tmp = tmp.resolve()
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    run(["ar", "-x", str(deb)], cwd=tmp)
    members = {path.name for path in tmp.iterdir()}
    if "debian-binary" not in members:
        raise RuntimeError(f"{deb}: debian-binary is missing")
    for kind in ("control", "data"):
        tar_path = next((path for path in tmp.iterdir() if path.name.startswith(f"{kind}.tar.gz")), None)
        if not tar_path:
            raise RuntimeError(f"{deb}: {kind}.tar.gz is missing or unsupported")
        _validate_tar_gzip(tar_path)


def load_source_packages() -> list[dict[str, str]]:
    if SOURCE_MANIFEST.exists():
        data = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        return [{str(k): str(v) for k, v in item.items()} for item in data]
    if SOURCE_PACKAGES.exists():
        return parse_deb_control_text(SOURCE_PACKAGES.read_text(encoding="utf-8"))
    return []


def group_by_section(packages: Iterable[dict[str, str]]) -> OrderedDict[str, list[dict[str, str]]]:
    grouped: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
    for pkg in packages:
        section = pkg.get("Section") or "No Section"
        grouped.setdefault(section, []).append(pkg)
    return grouped


def digest(path: Path, algo: str) -> str:
    hsh = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hsh.update(chunk)
    return hsh.hexdigest()


def looks_like_lfs_pointer(path: Path) -> bool:
    """Return True when a supposed binary artifact is a Git LFS pointer file."""
    with path.open("rb") as f:
        head = f.read(256)
    return head.startswith(b"version https://git-lfs.github.com/spec/")


def release_datetime() -> datetime:
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH", str(DEFAULT_SOURCE_DATE_EPOCH))
    try:
        epoch = int(raw_epoch)
    except ValueError as exc:
        raise RuntimeError(f"invalid SOURCE_DATE_EPOCH: {raw_epoch!r}") from exc
    if epoch < 0:
        raise RuntimeError(f"SOURCE_DATE_EPOCH must be non-negative: {epoch}")
    return datetime.fromtimestamp(epoch, timezone.utc)


def write_png(path: Path) -> None:
    """Write a tiny 64x64 RGB PNG without external dependencies."""
    w = hgt = 64
    rows = []
    for y in range(hgt):
        row = bytearray([0])
        for x in range(w):
            r = 45 + (x * 3) % 150
            g = 78 + (y * 2) % 120
            b = 185
            if abs(x - 32) + abs(y - 32) < 22:
                r, g, b = 245, 190, 70
            row.extend((r, g, b))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", w.to_bytes(4, "big") + hgt.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def render_section_nav(grouped: OrderedDict[str, list[dict[str, str]]]) -> str:
    rows = []
    mounted_ids = {str(pkg["package_id"]) for pkg in PATCHED_PACKAGES}
    for idx, (section, items) in enumerate(grouped.items()):
        mounted = sum(1 for item in items if item.get("Package") in mounted_ids)
        rows.append(
            f'''<a href="#section-{idx}">
  <span class="repo-icon folder">▸</span>
  <div class="row-main"><label><p>{h(section)}</p></label><p class="sub">{len(items)} packages · 已挂载 {mounted}</p></div>
  <span class="chevron">›</span>
</a>'''
        )
    return "\n".join(rows)


def render_package_rows(
    grouped: OrderedDict[str, list[dict[str, str]]],
    *,
    mounted: dict[str, dict[str, object]],
) -> str:
    sections = []
    for idx, (section, items) in enumerate(grouped.items()):
        rows = []
        for item in items:
            package = item.get("Package", "unknown")
            mounted_info = mounted.get(package)
            is_mounted = mounted_info is not None
            name = str(mounted_info["publish_name"]) if is_mounted else item.get("Name", package)
            if is_mounted:
                fields = mounted_info.get("fields", {})
                assert isinstance(fields, dict)
                version = str(fields.get("Version", item.get("Version", "unknown")))
                arch = str(fields.get("Architecture", item.get("Architecture", "iphoneos-arm64")))
            else:
                version = item.get("Version", "unknown")
                arch = item.get("Architecture", "iphoneos-arm64")
            desc = str(mounted_info["publish_desc"]) if is_mounted else "目录镜像：未发布原包 deb，仅保留分类结构。"
            badge = "已挂载 patch" if is_mounted else "目录镜像"
            klass = "package mounted" if is_mounted else "package disabled"
            href = f"./debs/{mounted_info['deb_name']}" if is_mounted else "#not-published"
            extra = (
                f"<p class=\"hash\">SHA256: <code>{h(mounted_info['sha256'])}</code></p>"
                f"<p class=\"sub\">Size: {mounted_info['size']} bytes</p>"
                if is_mounted
                else ""
            )
            rows.append(
                f'''<a class="{klass}" href="{h(href)}">
  <span class="repo-icon">{("✓" if is_mounted else "·")}</span>
  <div class="row-main">
    <label><p>{h(name)}</p></label>
    <p class="sub"><code>{h(package)}</code> · {h(version)} · {h(arch)}</p>
    <p class="desc">{h(desc)}</p>
    {extra}
  </div>
  <span class="badge">{h(badge)}</span>
</a>'''
            )
        sections.append(
            f'''<label class="section-title" id="section-{idx}"><p>{h(section)}</p></label>
<fieldset class="packages">
{''.join(rows)}
</fieldset>'''
        )
    return "\n".join(sections)


def build_package_record(config: dict[str, object], deb_out: Path, fields: dict[str, str], deb_sha256: str) -> str:
    package_lines = []
    for key in CONTROL_PASSTHROUGH_FIELDS:
        if key in fields:
            package_lines.append(f"{key}: {fields[key]}")
    package_lines.extend(
        [
            f"Section: {config['publish_section']}",
            f"Maintainer: {PUBLISH_MAINTAINER}",
            f"Name: {config['publish_name']}",
            f"Author: {PUBLISH_AUTHOR}",
            f"Filename: ./debs/{config['deb_name']}",
            f"Size: {deb_out.stat().st_size}",
            f"MD5sum: {digest(deb_out, 'md5')}",
            f"SHA1: {digest(deb_out, 'sha1')}",
            f"SHA256: {deb_sha256}",
            f"Depiction: ./depictions/{config['depiction_name']}",
            "Icon: ./CydiaIcon.png",
        ]
    )
    package_lines.append(f"Description: {config['publish_desc']}")
    return "\n".join(package_lines)


def render_depiction(config: dict[str, object], fields: dict[str, str], deb_sha256: str) -> str:
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(config['publish_name'])}</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:24px;line-height:1.6;color:#1f2937;background:#FFF5EE}}code{{word-break:break-all;background:#f3f4f6;padding:2px 5px;border-radius:5px}}.card{{background:#fff;border:1px solid #fed7aa;border-radius:14px;padding:16px;max-width:720px;margin:auto}}</style></head><body><div class="card"><h1>{h(config['publish_name'])}</h1><p>{h(config['publish_desc'])}</p><ul><li>Package: <code>{h(fields.get('Package', config['package_id']))}</code></li><li>Section: <code>{h(config['publish_section'])}</code></li><li>Version: <code>{h(fields.get('Version', 'unknown'))}</code></li><li>SHA256: <code>{h(deb_sha256)}</code></li></ul><p>仅供自用/授权测试环境；前端和 APT 均只挂载已完成目标的最终 patched 补丁包。</p></div></body></html>\n'''


def select_mounted_source_entries(source_packages: list[dict[str, str]], mounted: dict[str, dict[str, object]]) -> list[dict[str, str]]:
    """Return source rows for mounted packages only, preserving publish order."""
    by_package = {pkg.get("Package"): pkg for pkg in source_packages}
    selected: list[dict[str, str]] = []
    for package_id, info in mounted.items():
        fields = info["fields"]
        assert isinstance(fields, dict)
        entry = dict(by_package.get(package_id, {}))
        entry.update(
            {
                "Section": str(info["publish_section"]),
                "Package": package_id,
                "Name": str(info["publish_name"]),
                "Version": str(fields["Version"]),
                "Architecture": str(fields["Architecture"]),
            }
        )
        selected.append(entry)
    return selected


def validate_package_configs() -> None:
    required = {
        "package_id",
        "source",
        "deb_name",
        "publish_name",
        "publish_section",
        "publish_desc",
        "depiction_name",
    }
    package_ids: set[str] = set()
    deb_names: set[str] = set()
    depiction_names: set[str] = set()
    for config in PATCHED_PACKAGES:
        missing = sorted(required - config.keys())
        if missing:
            raise RuntimeError(f"patched package config is missing fields: {missing}")

        package_id = str(config["package_id"])
        if not package_id or package_id in package_ids:
            raise RuntimeError(f"invalid or duplicate package_id: {package_id!r}")
        package_ids.add(package_id)

        for key, suffix, seen in (
            ("deb_name", ".deb", deb_names),
            ("depiction_name", ".html", depiction_names),
        ):
            name = str(config[key])
            if not name.endswith(suffix) or Path(name).name != name or "/" in name or "\\" in name:
                raise RuntimeError(f"unsafe {key} for {package_id}: {name!r}")
            if name in seen:
                raise RuntimeError(f"duplicate {key}: {name!r}")
            seen.add(name)

        source = Path(config["source"])
        if not source.is_file():
            raise FileNotFoundError(source)
        if looks_like_lfs_pointer(source):
            raise RuntimeError(f"{source} is a Git LFS pointer; run `git lfs pull` before rebuilding pages-repo")


def replace_output_tree(staging: Path) -> None:
    backup = OUT.with_name(f".{OUT.name}.previous")
    if backup.exists():
        if OUT.exists():
            shutil.rmtree(backup)
        else:
            backup.rename(OUT)

    if OUT.exists():
        OUT.rename(backup)
    try:
        staging.rename(OUT)
    except BaseException:
        if backup.exists() and not OUT.exists():
            backup.rename(OUT)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _build_output(out: Path) -> tuple[dict[str, dict[str, object]], int]:
    (out / "debs").mkdir(parents=True)
    (out / "depictions").mkdir(parents=True)
    (out / ".gitattributes").write_text(
        "\n".join(
            [
                "# GitHub Pages 不能发布 Git LFS pointer；本目录内压缩包和 deb 必须作为普通 blob 提交。",
                "*.deb -filter -diff -merge -text",
                "*.gz -filter -diff -merge -text",
                "",
            ]
        ),
        encoding="utf-8",
    )


    mounted: dict[str, dict[str, object]] = {}
    package_records: list[str] = []
    for config in PATCHED_PACKAGES:
        source = Path(config["source"])
        deb_out = out / "debs" / str(config["deb_name"])
        shutil.copy2(source, deb_out)
        validate_deb_archive(deb_out, out / ".tmp-deb-validate")
        fields = extract_control(deb_out, out / ".tmp-control")
        shutil.rmtree(out / ".tmp-deb-validate")
        shutil.rmtree(out / ".tmp-control")

        missing_control = sorted({"Package", "Version", "Architecture"} - fields.keys())
        if missing_control:
            raise RuntimeError(f"{source}: control is missing required fields: {missing_control}")
        package_id = fields["Package"]
        expected_package_id = str(config["package_id"])
        if package_id != expected_package_id:
            raise RuntimeError(
                f"{source}: Package mismatch: control={package_id!r}, config={expected_package_id!r}"
            )
        if package_id in mounted:
            raise RuntimeError(f"duplicate mounted package: {package_id}")
        deb_sha256 = digest(deb_out, "sha256")
        info = {**config, "fields": fields, "size": deb_out.stat().st_size, "sha256": deb_sha256}
        mounted[package_id] = info
        package_records.append(build_package_record(config, deb_out, fields, deb_sha256))

    source_packages = select_mounted_source_entries(load_source_packages(), mounted)
    grouped = group_by_section(source_packages)
    total_display_packages = sum(len(items) for items in grouped.values())
    mounted_count = len(mounted)

    packages = "\n\n".join(package_records) + "\n\n"
    (out / "Packages").write_text(packages, encoding="utf-8")
    with gzip.GzipFile(filename=str(out / "Packages.gz"), mode="wb", mtime=0) as gz:
        gz.write(packages.encode("utf-8"))

    pkg_path = out / "Packages"
    pkg_gz_path = out / "Packages.gz"
    if len(mounted) == 1:
        only_fields = next(iter(mounted.values()))["fields"]
        assert isinstance(only_fields, dict)
        release_version = str(only_fields["Version"])
    else:
        release_version = "multi"
    release_architectures: list[str] = []
    for info in mounted.values():
        fields = info["fields"]
        assert isinstance(fields, dict)
        architecture = str(fields.get("Architecture", "iphoneos-arm64"))
        if architecture not in release_architectures:
            release_architectures.append(architecture)
    release_base = [
        f"Origin: {REPO_NAME}",
        f"Label: {ORIGINAL_REPO_NAME}",
        "Suite: stable",
        f"Version: {release_version}",
        "Codename: ios-patch",
        f"Architectures: {' '.join(release_architectures)}",
        "Components: main",
        f"Description: {REPO_DESC}",
        f"Date: {release_datetime().strftime('%a, %d %b %Y %H:%M:%S %z')}",
    ]
    release_hashes: list[str] = []
    for title, algo in [("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256")]:
        release_hashes.append(f"{title}:")
        for rel, path in [("Packages", pkg_path), ("Packages.gz", pkg_gz_path)]:
            release_hashes.append(f" {digest(path, algo)} {path.stat().st_size} {rel}")
    release = "\n".join(release_base + release_hashes) + "\n"
    (out / "Release").write_text(release, encoding="utf-8")

    (out / ".nojekyll").write_text("", encoding="utf-8")
    write_png(out / "CydiaIcon.png")
    (out / "favicon.ico").write_bytes((out / "CydiaIcon.png").read_bytes())

    section_nav = render_section_nav(grouped)
    package_rows = render_package_rows(grouped, mounted=mounted)
    mounted_deb_names = ", ".join(str(info["deb_name"]) for info in mounted.values())

    (out / "index.html").write_text(
        f'''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN">
<head>
  <title>{h(ORIGINAL_REPO_NAME)}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
  <meta name="apple-mobile-web-app-title" content="{h(ORIGINAL_REPO_NAME)}" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="viewport" content="width=device-width, minimum-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <meta name="HandheldFriendly" content="true" />
  <meta name="format-detection" content="telephone=no" />
  <meta name="robots" content="noindex,nofollow" />
  <meta name="description" content="{h(REPO_DESC)}" />
  <link rel="apple-touch-icon" href="./CydiaIcon.png" />
  <link rel="shortcut icon" href="./favicon.ico" />
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; border:0; color:inherit; font:inherit; text-decoration:none; }}
    body.pinstripe {{ background:#FFF5EE; color:#111827; font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif; font-weight:500; font-size:16px; }}
    panel {{ display:block; max-width:640px; margin:0 auto; padding:10px 10px 34px; }}
    fieldset {{ display:block; margin:12px 0; background:rgba(255,255,255,.92); border:1px solid rgba(120,53,15,.22); border-radius:13px; overflow:hidden; box-shadow:0 1px 0 rgba(255,255,255,.7) inset; }}
    fieldset > a, fieldset > div.row {{ min-height:52px; display:flex; align-items:center; gap:12px; padding:10px 12px; border-bottom:1px solid rgba(120,53,15,.12); }}
    fieldset > a:last-child, fieldset > div.row:last-child {{ border-bottom:0; }}
    fieldset > a[href] {{ -webkit-tap-highlight-color:transparent; }}
    block {{ display:block; margin:10px 0; padding:8px 15px; color:#6b7280; line-height:1.45; }}
    label.source, label.section-title {{ display:block; margin:18px 15px 6px; color:#7c2d12; font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; }}
    .source-description {{ padding:0 12px 12px 62px; color:#6b7280; font-size:14px; line-height:1.45; }}
    .repo-icon {{ flex:0 0 38px; width:38px; height:38px; border-radius:9px; display:grid; place-items:center; background:linear-gradient(135deg,#8b5cf6,#0ea5e9); color:#fff; font-weight:800; box-shadow:0 1px 3px rgba(0,0,0,.18); }}
    .repo-icon.folder {{ background:linear-gradient(135deg,#f59e0b,#ef4444); }}
    img.icon {{ flex:0 0 auto; border-radius:12px; }}
    .hero-title {{ float:right; vertical-align:middle; text-align:center; width:200px; padding-top:4px; }}
    .hero-title .name {{ font-size:24px; font-weight:700; }}
    .hero-title .root {{ font-size:16px; color:#6b7280; }}
    hr {{ height:1px; background:rgba(120,53,15,.18); margin:12px 0; clear:both; }}
    strong {{ font-weight:800; }}
    sup, small {{ font-size:11px; }}
    .add-row {{ justify-content:center; min-height:58px; }}
    .add-row .repo-icon {{ width:35px; height:35px; flex-basis:35px; }}
    .add-row p {{ font-size:22px; font-weight:700; }}
    .row-main {{ flex:1 1 auto; min-width:0; }}
    .row-main label p {{ font-weight:700; line-height:1.3; word-break:break-word; }}
    .sub {{ margin-top:2px; color:#6b7280; font-size:13px; line-height:1.35; }}
    .desc {{ margin-top:5px; color:#4b5563; font-size:13px; line-height:1.4; }}
    .hash {{ margin-top:5px; color:#4b5563; font-size:12px; line-height:1.35; }}
    code {{ background:#f3f4f6; border-radius:5px; padding:1px 4px; word-break:break-all; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
    .chevron {{ color:#9ca3af; font-size:24px; }}
    .badge {{ flex:0 0 auto; border-radius:999px; padding:4px 8px; background:#ecfdf5; color:#047857; font-size:12px; font-weight:700; }}
    .disabled {{ opacity:.72; cursor:not-allowed; }}
    .disabled .badge {{ background:#f3f4f6; color:#6b7280; }}
    .mounted {{ background:linear-gradient(90deg,rgba(236,253,245,.9),rgba(255,255,255,.95)); }}
    .notice {{ color:#92400e; background:rgba(254,243,199,.7); border:1px solid rgba(245,158,11,.25); border-radius:12px; margin:10px 0; padding:10px 14px; line-height:1.5; }}
    .footer {{ display:block; text-align:center; color:#9ca3af; margin:20px 0 0; font-size:12px; }}
    a {{ color:rgba(0,0,0,.82); transition:.2s; }}
    a:hover, a:focus {{ color:#450e61; }}
    @media (max-width:420px) {{ .hero-title {{ float:none; width:auto; text-align:left; margin-left:78px; }} .add-row p {{ font-size:19px; }} }}
  </style>
</head>
<body class="pinstripe">
<panel>
  <fieldset>
    <a id="add-cydia" class="add-row" href="#" target="_blank">
      <span class="repo-icon">C</span><p>点击添加源到Cydia</p>
    </a>
  </fieldset>
  <fieldset>
    <a id="add-sileo" class="add-row" href="#" target="_blank">
      <span class="repo-icon">S</span><p>点击添加源到Sileo</p>
    </a>
  </fieldset>

  <fieldset>
    <div class="row">
      <img class="icon" src="./CydiaIcon.png" style="width:64px;height:64px;vertical-align:top;" alt="repo icon" />
      <div class="hero-title"><div class="name">{h(ORIGINAL_REPO_NAME)}</div><div class="root">rootful / rootless patch</div></div>
    </div>
    <div class="row" style="display:block;">
      <p>Add this URL via Cydia<sup><small>™</small></sup>:</p>
      <p><strong><a id="repo-url" href="#">部署到 GitHub Pages 后自动显示</a></strong></p>
    </div>
  </fieldset>

  <block>
    <p><strong>{total_display_packages}</strong> package shown in current directory.</p>
    <p><strong>{mounted_count}</strong> patched packages mounted in this repo.</p>
    <p>Last upstream snapshot: <strong>{h(SOURCE_LAST_UPDATED)}</strong></p>
  </block>

  <div class="notice">
    当前 Pages 源展示并发布已完成目标的最终 patched 补丁包：<code>{h(mounted_deb_names)}</code>，旧 Pages 包和原始源其它 deb 均不发布。
  </div>

  <label class="source"><p>Sections</p></label>
  <fieldset class="sections">
{section_nav}
  </fieldset>

  <label class="source"><p>Source Info</p></label>
  <fieldset class="source">
    <a href="./">
      <img class="icon" src="./CydiaIcon.png" style="width:38px;height:38px;" alt="source icon" />
      <div class="row-main"><label><p id="source-name">{h(ORIGINAL_REPO_NAME)}</p></label><p class="sub">{h(ORIGINAL_REPO_DESC)}</p></div>
    </a>
    <div class="source-description"><p>{h(REPO_DESC)}</p></div>
  </fieldset>

{package_rows}

  <footer class="footer">
    <p><span>Index</span><br /><span>{h(ORIGINAL_REPO_NAME)}</span> · <span>Copyright © 2026</span></p>
  </footer>
</panel>
<script>
(function() {{
  var repo = new URL('./', window.location.href).href;
  var repoNode = document.getElementById('repo-url');
  repoNode.textContent = repo;
  repoNode.href = repo;
  document.getElementById('add-cydia').href = 'cydia://url/https://cydia.saurik.com/api/share#?source=' + repo;
  document.getElementById('add-sileo').href = 'sileo://source/' + repo;
}})();
</script>
</body>
</html>
''',
        encoding="utf-8",
    )

    for info in mounted.values():
        fields = info["fields"]
        assert isinstance(fields, dict)
        (out / "depictions" / str(info["depiction_name"])).write_text(
            render_depiction(info, fields, str(info["sha256"])),
            encoding="utf-8",
        )

    category_lines = "\n".join(f"- {section}: {len(items)} packages" for section, items in grouped.items())
    (out / "README.md").write_text(
        f'''# {REPO_NAME}

这是一个可部署到 GitHub Pages 的静态 Cydia/Sileo 源目录。前端页面和 APT 元数据挂载已完成目标的最终 patched 补丁 deb；中间态补丁包和原始源全量资源不会被 Pages 发布。

## 当前挂载包

{chr(10).join(f"- `{package_id}` / `{info['publish_name']}` / `debs/{info['deb_name']}` / `{info['size']}` bytes / SHA256 `{info['sha256']}`" for package_id, info in mounted.items())}

> 注意：APT 升级判断以 deb control 中的 `Version` 为准；需要强制覆盖已安装包时，应同步提升 control `Version` 并重新生成 Pages metadata。

## 前端分类目录

当前前端展示：`{total_display_packages}` packages，当前 Pages 源实际挂载：`{mounted_count}` patched packages。

{category_lines}

## 推荐部署

推荐使用仓库里的 GitHub Actions：

```text
.github/workflows/deploy-pages-repo.yml
```

它会把 `pages-repo/` 作为 Pages artifact 根目录发布。仓库内前端/展示文件只维护在 `pages-repo/`，但公开访问 URL 仍是：

```text
https://<user>.github.io/<repo>/
```

本仓库对应：

```text
https://myzest.github.io/apt-ios-patch/
```

## Git LFS 注意事项

GitHub Pages 不能直接发布 Git LFS 文件。本目录自带 `.gitattributes`：

```gitattributes
*.deb -filter -diff -merge -text
*.gz -filter -diff -merge -text
```

确保 `Packages.gz` 和 `.deb` 以普通 Git blob 提交，而不是 LFS pointer。

## 本地校验

```bash
python3 scripts/build_pages_repo.py
python3 scripts/verify_pages_repo.py
gzip -t pages-repo/Packages.gz
shasum -a 256 pages-repo/debs/*.deb
```

部署后校验：

```bash
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -t
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -dc
curl -fsSLO https://<user>.github.io/<repo>/debs/<deb-name>
shasum -a 256 <deb-name>
```
''',
        encoding="utf-8",
    )

    return mounted, len(grouped)


def build() -> None:
    validate_package_configs()
    staging = OUT.with_name(f".{OUT.name}.build")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        mounted, category_count = _build_output(staging)
        replace_output_tree(staging)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    print(f"Built {OUT}")
    for package_id, info in mounted.items():
        print(f"{package_id} sha256: {info['sha256']}")
    print(f"source categories: {category_count}")


if __name__ == "__main__":
    build()
