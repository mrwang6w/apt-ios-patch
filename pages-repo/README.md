# iOS Patch Repo

这是一个可部署到 GitHub Pages 的静态 Cydia/Sileo 源目录，只挂载 `patched/` 中生成的补丁 deb，不镜像原始源全量资源。

## 当前包

- Package: `com.amg456.rootless`
- Name: `AMG Rootless Patch (NoPopup 2099)`
- Version: `18.1.1`
- File: `debs/com.amg456.rootless_18.1.1_nopopup_2099.deb`
- SHA256: `82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1`

> 注意：deb 内部版本仍是 `18.1.1`。如果设备已经安装同版本原包，包管理器可能不提示升级；需要强制升级时应重打 deb 并同步提升 deb control 中的 `Version`。

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
shasum -a 256 pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099.deb
```

部署后校验：

```bash
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -t
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -dc | grep -A20 '^Package: com.amg456.rootless'
curl -fsSLO https://<user>.github.io/<repo>/debs/com.amg456.rootless_18.1.1_nopopup_2099.deb
shasum -a 256 com.amg456.rootless_18.1.1_nopopup_2099.deb
```
