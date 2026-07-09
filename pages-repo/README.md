# AMG官方源™ Patch Repo

这是一个可部署到 GitHub Pages 的静态 Cydia/Sileo 源目录。前端页面按原 `AMG官方源™` 的越狱源分类目录做静态还原，但 APT 元数据只挂载 `patched/` 中生成的补丁 deb，不镜像原始源全量资源。

## 当前挂载包

- Package: `com.amg456.rootless`
- Name: `纯净版18.1.1_AMG奔驰正版[无根] Patch NoExit`
- Section: `AMG`
- Version: `18.1.1`
- File: `debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb`
- Size: `6206412` bytes
- SHA256: `0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866`

> 注意：deb 内部版本仍是 `18.1.1`。如果设备已经安装同版本原包，包管理器可能不提示升级；需要强制升级时应重打 deb 并同步提升 deb control 中的 `Version`。

## 前端分类目录

原源快照统计：`16` packages，当前 Pages 源实际挂载：`1` patched package。

- AWZ爱伪装: 1 packages
- AMG: 3 packages
- 工具: 1 packages
- 越狱插件: 3 packages
- ZORRO佐罗: 2 packages
- Razer雷蛇: 3 packages
- VBox虚拟盒子: 3 packages

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
shasum -a 256 pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
```

部署后校验：

```bash
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -t
curl -fsSL https://<user>.github.io/<repo>/Packages.gz | gzip -dc | grep -A20 '^Package: com.amg456.rootless'
curl -fsSLO https://<user>.github.io/<repo>/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
shasum -a 256 com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
```
