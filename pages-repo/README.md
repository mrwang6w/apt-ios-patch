# AMG官方源™ Patch Repo

这是一个可部署到 GitHub Pages 的静态 Cydia/Sileo 源目录。前端页面和 APT 元数据挂载已完成目标的最终 patched 补丁 deb；中间态补丁包和原始源全量资源不会被 Pages 发布。

## 当前挂载包

- `com.amg456.rootless` / `纯净版18.1.1_AMG奔驰正版[无根] Patch NoExit` / `debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb` / `6206412` bytes / SHA256 `0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866`
- `app.Razer854.rootless` / `2.5.0-11_Razer雷蛇(无根) Patch AuthState USTAR` / `debs/app.Razer854.rootless_2.5.0-11_authstate_ustar.deb` / `21217862` bytes / SHA256 `53deb601ec0458da67379ddd0390b5f57e06ef7549079756bb3f7c8f351a8e21`

> 注意：APT 升级判断以 deb control 中的 `Version` 为准；需要强制覆盖已安装包时，应同步提升 control `Version` 并重新生成 Pages metadata。

## 前端分类目录

当前前端展示：`2` packages，当前 Pages 源实际挂载：`2` patched packages。

- AMG: 1 packages
- Razer雷蛇: 1 packages

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
