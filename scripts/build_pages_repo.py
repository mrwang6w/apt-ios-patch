#!/usr/bin/env python3
"""Build a static GitHub Pages Cydia/Sileo repo from patched deb artifacts."""
from __future__ import annotations

import gzip
import hashlib
import shutil
import subprocess
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCHED_DIR = ROOT / "patched"
OUT = ROOT / "pages-repo"
PACKAGE_ID = "com.amg456.rootless"
DEB_SOURCE = PATCHED_DIR / "纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb"
DEB_NAME = "com.amg456.rootless_18.1.1_nopopup_2099.deb"
REPO_NAME = "iOS Patch Repo"
REPO_DESC = "自用授权测试源：仅挂载 patched 目录中的补丁 deb。"
PUBLISH_NAME = "AMG Rootless Patch (NoPopup 2099)"
PUBLISH_MAINTAINER = "Local Patch Repo"
PUBLISH_AUTHOR = "Local Patch Repo"
PUBLISH_SECTION = "Patch"
PUBLISH_DESC = "授权测试补丁包：去除首页激活弹窗，并将试用过期时间调整为 2099。"


def run(cmd: list[str], cwd: Path | None = None) -> bytes:
    return subprocess.check_output(cmd, cwd=str(cwd) if cwd else None)


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
    fields: dict[str, str] = {}
    current: str | None = None
    for line in control_file.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        if line[0].isspace() and current:
            fields[current] += "\n" + line
            continue
        key, _, value = line.partition(":")
        if not _:
            continue
        current = key
        fields[key] = value.strip()
    return fields


def digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def looks_like_lfs_pointer(path: Path) -> bool:
    """Return True when a supposed binary artifact is a Git LFS pointer file."""
    with path.open("rb") as f:
        head = f.read(256)
    return head.startswith(b"version https://git-lfs.github.com/spec/")


def write_png(path: Path) -> None:
    """Write a tiny 64x64 RGB PNG without external dependencies."""
    w = h = 64
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            r = 35 + (x * 3) % 180
            g = 80 + (y * 2) % 130
            b = 180
            # simple center diamond highlight
            if abs(x - 32) + abs(y - 32) < 22:
                r, g, b = 245, 190, 70
            row.extend((r, g, b))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + kind + data + zlib.crc32(kind + data).to_bytes(4, "big")

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", w.to_bytes(4, "big") + h.to_bytes(4, "big") + bytes([8, 2, 0, 0, 0]))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def build() -> None:
    if not DEB_SOURCE.exists():
        raise FileNotFoundError(DEB_SOURCE)
    if looks_like_lfs_pointer(DEB_SOURCE):
        raise RuntimeError(f"{DEB_SOURCE} is a Git LFS pointer; run `git lfs pull` before rebuilding pages-repo")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "debs").mkdir(parents=True)
    (OUT / "depictions").mkdir(parents=True)

    deb_out = OUT / "debs" / DEB_NAME
    shutil.copy2(DEB_SOURCE, deb_out)
    fields = extract_control(deb_out, OUT / ".tmp-control")
    shutil.rmtree(OUT / ".tmp-control")

    filename = f"./debs/{DEB_NAME}"
    size = deb_out.stat().st_size
    package_lines = []
    for key in ["Package", "Version", "Priority", "Depends", "Architecture"]:
        if key in fields:
            package_lines.append(f"{key}: {fields[key]}")
    package_lines.extend(
        [
            f"Section: {PUBLISH_SECTION}",
            f"Maintainer: {PUBLISH_MAINTAINER}",
            f"Name: {PUBLISH_NAME}",
            f"Author: {PUBLISH_AUTHOR}",
            f"Filename: {filename}",
            f"Size: {size}",
            f"MD5sum: {digest(deb_out, 'md5')}",
            f"SHA1: {digest(deb_out, 'sha1')}",
            f"SHA256: {digest(deb_out, 'sha256')}",
            "Depiction: ./depictions/com.amg456.rootless.html",
            "Icon: ./CydiaIcon.png",
        ]
    )
    package_lines.append(f"Description: {PUBLISH_DESC}")
    packages = "\n".join(package_lines) + "\n\n"
    (OUT / "Packages").write_text(packages, encoding="utf-8")
    with gzip.GzipFile(filename=str(OUT / "Packages.gz"), mode="wb", mtime=0) as gz:
        gz.write(packages.encode("utf-8"))

    pkg_path = OUT / "Packages"
    pkg_gz_path = OUT / "Packages.gz"
    release_base = [
        f"Origin: {REPO_NAME}",
        f"Label: {REPO_NAME}",
        "Suite: stable",
        f"Version: {fields.get('Version', '1.0')}",
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

    (OUT / "index.html").write_text(
        f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no\">
  <meta name=\"robots\" content=\"noindex,nofollow\">
  <meta name=\"description\" content=\"{REPO_DESC}\">
  <title>{REPO_NAME}</title>
  <link rel=\"apple-touch-icon\" href=\"./CydiaIcon.png\">
  <link rel=\"shortcut icon\" href=\"./favicon.ico\">
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#fff7ed; color:#1f2937; }}
    main {{ max-width:720px; margin:0 auto; padding:24px 16px 40px; }}
    .card {{ background:#fff; border:1px solid #fed7aa; border-radius:18px; padding:18px; margin:14px 0; box-shadow:0 8px 28px rgba(124,45,18,.08); }}
    .hero {{ text-align:center; }}
    .icon {{ width:72px; height:72px; border-radius:16px; }}
    h1 {{ margin:12px 0 4px; font-size:28px; }}
    .muted {{ color:#6b7280; font-size:14px; }}
    .btns {{ display:grid; gap:12px; grid-template-columns:1fr; margin-top:16px; }}
    .btn {{ display:block; padding:14px 16px; border-radius:14px; text-decoration:none; color:#fff; font-weight:700; text-align:center; }}
    .cydia {{ background:#8b5cf6; }} .sileo {{ background:#0ea5e9; }} .download {{ background:#16a34a; }}
    code {{ word-break:break-all; background:#f3f4f6; padding:2px 5px; border-radius:5px; }}
    table {{ width:100%; border-collapse:collapse; }} td {{ padding:7px 0; border-bottom:1px solid #f3f4f6; vertical-align:top; }} td:first-child {{ color:#6b7280; width:92px; }}
  </style>
</head>
<body>
<main>
  <section class=\"card hero\">
    <img class=\"icon\" src=\"./CydiaIcon.png\" alt=\"repo icon\">
    <h1>{REPO_NAME}</h1>
    <p class=\"muted\">{REPO_DESC}</p>
    <div class=\"btns\">
      <a id=\"add-cydia\" class=\"btn cydia\" href=\"#\">添加到 Cydia</a>
      <a id=\"add-sileo\" class=\"btn sileo\" href=\"#\">添加到 Sileo</a>
      <a class=\"btn download\" href=\"./debs/{DEB_NAME}\">直接下载 deb</a>
    </div>
  </section>

  <section class=\"card\">
    <h2>源地址</h2>
    <p><code id=\"repo-url\">部署到 GitHub Pages 后自动显示</code></p>
    <p class=\"muted\">如果页面在子路径，例如 <code>/ios-repo/</code>，请把完整目录 URL 添加到包管理器。</p>
  </section>

  <section class=\"card\">
    <h2>当前挂载包</h2>
    <table>
      <tr><td>Package</td><td><code>{fields.get('Package', PACKAGE_ID)}</code></td></tr>
      <tr><td>Name</td><td>{PUBLISH_NAME}</td></tr>
      <tr><td>Version</td><td>{fields.get('Version', 'unknown')}</td></tr>
      <tr><td>Arch</td><td>{fields.get('Architecture', 'iphoneos-arm64')}</td></tr>
      <tr><td>Size</td><td>{size} bytes</td></tr>
      <tr><td>SHA256</td><td><code>{digest(deb_out, 'sha256')}</code></td></tr>
    </table>
  </section>

  <section class=\"card\">
    <h2>说明</h2>
    <p>本页面只展示并挂载本项目 <code>patched/</code> 中的补丁 deb，不镜像原始源全部资源。</p>
    <p class=\"muted\">请仅在自有设备或授权测试环境中使用。</p>
  </section>
</main>
<script>
(function() {{
  var repo = new URL('./', window.location.href).href;
  document.getElementById('repo-url').textContent = repo;
  document.getElementById('add-cydia').href = 'cydia://url/https://cydia.saurik.com/api/share#?source=' + repo;
  document.getElementById('add-sileo').href = 'sileo://source/' + repo;
}})();
</script>
</body>
</html>
""",
        encoding="utf-8",
    )

    (OUT / "depictions" / "com.amg456.rootless.html").write_text(
        f"""<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{PUBLISH_NAME}</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:24px;line-height:1.6;color:#1f2937}}code{{word-break:break-all}}</style></head><body><h1>{PUBLISH_NAME}</h1><p>{PUBLISH_DESC}</p><ul><li>Package: <code>{fields.get('Package', PACKAGE_ID)}</code></li><li>Version: <code>{fields.get('Version', 'unknown')}</code></li><li>SHA256: <code>{digest(deb_out, 'sha256')}</code></li></ul><p>仅供自用/授权测试环境。</p></body></html>\n""",
        encoding="utf-8",
    )

    (OUT / "README.md").write_text(
        f"""# {REPO_NAME}

这是一个可部署到 GitHub Pages 的静态 Cydia/Sileo 源目录，只挂载 `patched/` 中生成的补丁 deb，不镜像原始源全量资源。

## 当前包

- Package: `{fields.get('Package', PACKAGE_ID)}`
- Name: `{PUBLISH_NAME}`
- Version: `{fields.get('Version', 'unknown')}`
- File: `debs/{DEB_NAME}`
- SHA256: `{digest(deb_out, 'sha256')}`

> 注意：deb 内部版本仍是 `{fields.get('Version', 'unknown')}`。如果设备已经安装同版本原包，包管理器可能不提示升级；需要强制升级时应重打 deb 并同步提升 deb control 中的 `Version`。

## 推荐部署

推荐使用仓库里的 GitHub Actions：

```text
.github/workflows/deploy-pages-repo.yml
```

它会把 `pages-repo/` 作为 Pages artifact 根目录发布，避免把 `downloads/`、`work/` 等分析目录暴露成静态站点。

## Git LFS 注意事项

GitHub Pages 不能直接发布 Git LFS 文件。本目录自带 `.gitattributes`：

```gitattributes
*.deb -filter -diff -merge -text
*.gz -filter -diff -merge -text
```

确保 `Packages.gz` 和 `.deb` 以普通 Git blob 提交，而不是 LFS pointer。

## 本地校验

```bash
gzip -t pages-repo/Packages.gz
python3 scripts/build_pages_repo.py
shasum -a 256 pages-repo/debs/{DEB_NAME}
```

部署后校验：

```bash
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -t
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -dc | grep -A20 '^Package: {fields.get('Package', PACKAGE_ID)}'
curl -fsSLO https://<user>.github.io/<repo>/debs/{DEB_NAME}
shasum -a 256 {DEB_NAME}
```
""",
        encoding="utf-8",
    )

    print(f"Built {OUT}")
    print(f"deb sha256: {digest(deb_out, 'sha256')}")


if __name__ == "__main__":
    build()
