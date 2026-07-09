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
        "source": PATCHED_DIR / "2.5.0_Razer雷蛇(无根)_2.5.0-6_app.Razer854.rootless_nopopup_2099_noheartbeat_noexit_authhook_nodict_deferui.deb",
        "deb_name": "app.Razer854.rootless_2.5.0-6_nopopup_2099_noheartbeat_noexit_authhook_nodict_deferui.deb",
        "publish_name": "2.5.0-6_Razer雷蛇(无根) Patch Auth2099 NoDict DeferUI NoExit",
        "publish_section": "Razer雷蛇",
        "publish_desc": "授权测试补丁包：恢复刷新/一键新机业务入口，保留授权弹窗/退出路径静态补丁；运行期授权 hook 强制 LicenseAccepted=YES、ExpiredText=2099.01.01 00:00，移除全局 NSDictionary swizzle，并延后安装 UIKit hook 修复真机启动闪退。",
        "depiction_name": "app.Razer854.rootless.html",
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
    return parse_deb_control_text(control_file.read_text(encoding="utf-8"))[0]


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
    package_id = str(config["package_id"])
    package_lines = []
    for key in ["Package", "Version", "Priority", "Depends", "Architecture"]:
        if key in fields:
            package_lines.append(f"{key}: {fields[key]}")
    if "Package" not in fields:
        package_lines.insert(0, f"Package: {package_id}")
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
        if package_id in by_package:
            selected.append(dict(by_package[package_id]))
            continue
        fields = info["fields"]
        assert isinstance(fields, dict)
        selected.append(
            {
                "Section": str(info["publish_section"]),
                "Package": package_id,
                "Name": str(info["publish_name"]),
                "Version": str(fields.get("Version", "unknown")),
                "Architecture": str(fields.get("Architecture", "iphoneos-arm64")),
            }
        )
    return selected



def build() -> None:
    for config in PATCHED_PACKAGES:
        source = Path(config["source"])
        if not source.exists():
            raise FileNotFoundError(source)
        if looks_like_lfs_pointer(source):
            raise RuntimeError(f"{source} is a Git LFS pointer; run `git lfs pull` before rebuilding pages-repo")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "debs").mkdir(parents=True)
    (OUT / "depictions").mkdir(parents=True)

    mounted: dict[str, dict[str, object]] = {}
    package_records: list[str] = []
    for config in PATCHED_PACKAGES:
        source = Path(config["source"])
        deb_out = OUT / "debs" / str(config["deb_name"])
        shutil.copy2(source, deb_out)
        fields = extract_control(deb_out, OUT / ".tmp-control")
        shutil.rmtree(OUT / ".tmp-control")
        package_id = fields.get("Package", str(config["package_id"]))
        deb_sha256 = digest(deb_out, "sha256")
        info = {**config, "fields": fields, "size": deb_out.stat().st_size, "sha256": deb_sha256}
        mounted[package_id] = info
        package_records.append(build_package_record(config, deb_out, fields, deb_sha256))

    source_packages = select_mounted_source_entries(load_source_packages(), mounted)
    grouped = group_by_section(source_packages)
    total_display_packages = sum(len(items) for items in grouped.values())
    mounted_count = len(mounted)

    packages = "\n\n".join(package_records) + "\n\n"
    (OUT / "Packages").write_text(packages, encoding="utf-8")
    with gzip.GzipFile(filename=str(OUT / "Packages.gz"), mode="wb", mtime=0) as gz:
        gz.write(packages.encode("utf-8"))

    pkg_path = OUT / "Packages"
    pkg_gz_path = OUT / "Packages.gz"
    release_version = (
        str(next(iter(mounted.values()))["fields"].get("Version", "unknown"))
        if len(mounted) == 1
        else "multi"
    )
    release_base = [
        f"Origin: {REPO_NAME}",
        f"Label: {ORIGINAL_REPO_NAME}",
        "Suite: stable",
        f"Version: {release_version}",
        "Codename: ios-patch",
        "Architectures: iphoneos-arm64",
        "Components: main",
        f"Description: {REPO_DESC}",
        f"Date: {datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S %z')}",
    ]
    release_hashes: list[str] = []
    for title, algo in [("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256")]:
        release_hashes.append(f"{title}:")
        for rel, path in [("Packages", pkg_path), ("Packages.gz", pkg_gz_path)]:
            release_hashes.append(f" {digest(path, algo)} {path.stat().st_size} {rel}")
    release = "\n".join(release_base + release_hashes) + "\n"
    (OUT / "Release").write_text(release, encoding="utf-8")

    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / ".gitattributes").write_text(
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


    write_png(OUT / "CydiaIcon.png")
    (OUT / "favicon.ico").write_bytes((OUT / "CydiaIcon.png").read_bytes())

    section_nav = render_section_nav(grouped)
    package_rows = render_package_rows(grouped, mounted=mounted)
    mounted_deb_names = ", ".join(str(info["deb_name"]) for info in mounted.values())

    (OUT / "index.html").write_text(
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
      <div class="hero-title"><div class="name">{h(ORIGINAL_REPO_NAME)}</div><div class="root">rootless patch</div></div>
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
        (OUT / "depictions" / str(info["depiction_name"])).write_text(
            render_depiction(info, fields, str(info["sha256"])),
            encoding="utf-8",
        )

    category_lines = "\n".join(f"- {section}: {len(items)} packages" for section, items in grouped.items())
    (OUT / "README.md").write_text(
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

    print(f"Built {OUT}")
    for package_id, info in mounted.items():
        print(f"{package_id} sha256: {info['sha256']}")
    print(f"source categories: {len(grouped)}")


if __name__ == "__main__":
    build()
