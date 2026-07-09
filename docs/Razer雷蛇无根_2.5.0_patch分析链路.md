# Razer 雷蛇无根 2.5.0 patch 分析链路

## 1. 样本与输出

- 原始 deb：`/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless.deb`
- 原始 SHA256：`e1da2c3995ab653609671d0dd75adf9f65669378c089a0386070635bd4c16d1d`
- 原始 size：`21521984` bytes
- Package：`app.Razer854.rootless`
- Version：`2.5.0`
- Architecture：`iphoneos-arm64`
- 输出 deb：`/Users/zest/myworks/apt-ios-patch/patched/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless_nopopup_noexpire_noheartbeat_noexit.deb`
- 输出 SHA256：`bffe9d57de415d70c6723e90e9aca0f2c17da123abd10e812243db3a1f8505ef`
- 输出 size：`21215306` bytes

本轮更新范围：

- `patched/`：保留各目标的最终补丁 deb，包括已恢复的 AMG 最新最终补丁包和本轮 Razer 最终补丁包；仅清理 AMG 早期中间态补丁 deb。
- `pages-repo/`：已同步为 Pages 越狱源；APT metadata 和前端同时挂载已完成的 AMG 最终补丁包与本轮 Razer 最终补丁包，未发布 AMG 早期中间态补丁包。
- `docs/`：保存本分析链路文档。
- `work/app.Razer854.rootless-2.5.0/`：仅留存审计 metadata、r2/otool/nm/strings 文本证据、patch 后反汇编和 entitlements；继续忽略 rootfs、raw tar、repack、verify-final、原始 Mach-O 备份等大体积二进制中间产物。
- `.gitignore`：只为上述 Razer work 文本证据增加定向放行规则。

没有在仓库根目录复制 `index.html`、`Packages`、`debs/` 等 Pages 产物；所有展示前端和 APT 静态源仍只位于 `pages-repo/`。

## 2. 被动审计命令

```bash
python3 skills/ios-deb-reverse-patcher/scripts/deb_audit.py \
  '/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless.deb' \
  --out /Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/audit
```

关键目录：

- 解包 work：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/`
- 原始 audit：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/audit/`
- 最终 audit：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/final-audit/`
- 反解包验证：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/verify-final/`

## 3. Payload 与 Mach-O

rootless payload 位于 `var/jb/`：

- `var/jb/Applications/razer.app/`：主 app，`CFBundleExecutable=Razer`
- `var/jb/Applications/RCleaner.app/`：清理辅助 app
- `var/jb/Library/LaunchDaemons/com.razer.startup.plist`：`KeepAlive=true`，启动 `/var/jb/usr/bin/razerdaemon`
- `var/jb/Library/MobileSubstrate/DynamicLibraries/razer.dylib`
- `var/jb/Library/MobileSubstrate/DynamicLibraries/zen.dylib`
- `var/jb/usr/bin/razerdaemon`
- `var/jb/usr/bin/razerdo`

所有 Mach-O 均为单架构 `arm64`，没有 FAT/universal，也没有 `arm64e` slice：

| Binary | 原始类型 | 原始 SHA256 |
|---|---|---|
| `var/jb/Applications/RCleaner.app/RCleaner` | Mach-O executable arm64 | `225710b91e25cbaf5d7277cef7dd1beb6d2a8a3e64b89b26f661c901bbc4a82c` |
| `var/jb/Applications/razer.app/Razer` | Mach-O executable arm64 | `f0657be08d14a62cc23424d3f04675fd98b374b121614d60cbbd270099b97916` |
| `var/jb/Applications/razer.app/razerd` | Mach-O dylib arm64 | `4805f21473682434cd688124e8c384729379ee7930cb774579e971a55bea01dd` |
| `var/jb/Applications/razer.app/z` | Mach-O dylib arm64 | `12ed80368b6445c9f45ae7e47bd08272baf32d80861fbe383e3778139afd7864` |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/razer.dylib` | Mach-O dylib arm64 | `305fa368435e1e760debd99fab93de81299ef71512328d09d7a06040ee99ad55` |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/zen.dylib` | Mach-O dylib arm64 | `5c5733167fa9b3d15703bf8bd77f9c1c333057a5597bbca7704f492dbda3c6ae` |
| `var/jb/usr/bin/razerdaemon` | Mach-O executable arm64 | `ee95c224d694677f9f0d27a655f81de9e658aecaa165b8f75b2e0db6bd27550c` |
| `var/jb/usr/bin/razerdo` | Mach-O executable arm64 | `1745e12cfc31978068a075916acf2b58180da2ee2a22bf2a0de02f199b72876e` |

## 4. 保护链路证据

### 4.1 卡密 / 授权 UI

`Razer` 主二进制中命中：

- selector：`requestlicense`
- selector：`showAlert:`
- strings：`Please Input LicenseCode`、`Code are case insensitive`、`License Code`
- strings：`LicenseAccepted`、`ExpiredText`、`Lic Expired`、`license expired`
- URL：`https://api.razerios.com/`、`http://106.75.148.59:9001/`
- storyboard/nib：`Base.lproj/Main.storyboardc/license.nib` -> `LicenseViewController`
- 多语言资源：`zh-Hans.lproj/Language.strings` 中 `Please Input LicenseCode => 请输入授权码`，`License Code => 授权码`

### 4.2 试用/版本过期

多语言资源与主二进制命中：

- `current version outtime,need to update => 当前版本已经过期，请重新安装最新版本`
- `ExpiredText => Expired (Refresh)`
- `Lic Expired => 授权至：`
- `license expired`

ObjC class 信息显示主控混淆类含 `checkUpdate`、`viewDidAppear:`、`requestlicense`，符合启动后检查版本/授权状态再弹窗或展示过期状态的链路。

### 4.3 心跳 / 定时 / 网络上报

`Razer`：

- imports：`NSTimer`、`NSURLSession`、`NSURLSessionConfiguration`、`CFNetwork`
- selectors：`scheduledTimerWithTimeInterval:target:selector:userInfo:repeats:`、`repeatingTimer`

`razerdaemon`：

- launchd：`KeepAlive=true`，程序为 `/var/jb/usr/bin/razerdaemon`
- selectors：`GCDTimer`、`keepAliveTimer`、`checkDupTimer`、`requestDeviceInfo:`
- strings：`/device/%@/1`、`/device/%@/100`、`/device/%@/#`
- URLs：`http://175.178.71.72:9005/api/rdata/getdata?enc=%s`、`http://106.75.148.59:9005/api/rdata/getdata?enc=%s`、`http://zck.razerios.com/api/rdata/getdata?enc=%s`

### 4.4 延迟退出 / kill 路径

`Razer`：

- selectors：`exit:xr:`、`exit2:xr:`、`exitClicked:`
- strings：`zexit`、`appexit`、`Kill APP`
- strings：`/var/jb/usr/bin/killall`、`/var/jb/sbin/killall`、`/usr/bin/killall`、`/bin/killall`
- strings：`/var/jb/usr/bin/killall -9 razerdaemon` 等多路径 daemon kill 命令

`razerdaemon`：

- strings：`killall -9 razerdaemon`

静态 imports 没有直接 `_exit/exit/abort/kill/system/posix_spawn/exec/fork`，且关键业务方法普遍是 88-byte trampoline：保存寄存器、设置 opcode、跳入统一分发器。因此常规 xref/decompile 不能直接展开业务分支，本轮采用入口 `RET` 的最小静态 patch。

## 5. Patch 点表

所有 VA 均基于 Mach-O image base `0x100000000`，file offset = `VA - 0x100000000`。新指令均为 ARM64 `ret`：`c0 03 5f d6`。

| Binary | Arch | Function / symbol | VA | file offset | old bytes | new bytes | reason |
|---|---|---:|---:|---:|---|---|---|
| `var/jb/Applications/razer.app/Razer` | arm64 | `checkUpdate` | `0x1003cee84` | `0x003cee84` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用启动/版本过期检查入口，覆盖 `current version outtime` 触发面。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | 混淆主控 `viewDidAppear:` | `0x1003d1938` | `0x003d1938` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用页面出现后的授权检查/弹窗/定时触发入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `requestlicense` | `0x1003d2018` | `0x003d2018` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用授权码输入弹窗与授权请求入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `exit:xr:` | `0x10032bd78` | `0x0032bd78` | `fd 7b bf a9` | `c0 03 5f d6` | 禁用 VM 外显退出/kill 方法之一，覆盖 `zexit/appexit/Kill APP` 链。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `exitClicked:` | `0x1003d3098` | `0x003d3098` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用 UI/回调触发的退出入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `exit2:xr:` | `0x1020070dc` | `0x020070dc` | `fd 7b bf a9` | `c0 03 5f d6` | 禁用第二条退出/kill 分支，防止延迟闪退残留。 |
| `var/jb/usr/bin/razerdaemon` | arm64 | `requestDeviceInfo:` | `0x10047430c` | `0x0047430c` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用 daemon 周期设备信息/授权上报入口，覆盖 `/api/rdata/getdata?enc=%s`。 |

## 6. 重签与重打包

重签：

```bash
codesign -f -s - --entitlements \
  /Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/evidence/razer-app.entitlements.plist \
  /Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/pkgroot/var/jb/Applications/razer.app

codesign -f -s - \
  /Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/pkgroot/var/jb/usr/bin/razerdaemon
```

本机没有 `dpkg-deb/fakeroot`，使用手工 deb 组装：

```bash
/opt/homebrew/bin/gtar --format=gnu --sort=name --mtime='UTC 2026-07-09' \
  --owner=0 --group=0 --numeric-owner -czf control.tar.gz .

/opt/homebrew/bin/gtar --format=gnu --sort=name --mtime='UTC 2026-07-09' \
  --owner=0 --group=0 --numeric-owner -czf data.tar.gz .

ar -crS final.deb debian-binary control.tar.gz data.tar.gz
```

关键 archive mode 验证：

- `Razer`：`0755 root/root`
- `razerdaemon`：`4755 root/root`
- `razerdo`：`4755 root/root`
- `razer.dylib` / `zen.dylib`：`0755 root/root`

## 7. 最终验证

最终 deb：

```text
/Users/zest/myworks/apt-ios-patch/patched/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless_nopopup_noexpire_noheartbeat_noexit.deb
SIZE=21215306 bytes
SHA256=bffe9d57de415d70c6723e90e9aca0f2c17da123abd10e812243db3a1f8505ef
```

最终 deb 反解包 byte-level 验证全部为 `c0035fd6`：

```text
Razer        checkUpdate              off=0x003cee84 OK
Razer        mainVC viewDidAppear:    off=0x003d1938 OK
Razer        requestlicense           off=0x003d2018 OK
Razer        exit:xr:                 off=0x0032bd78 OK
Razer        exitClicked:             off=0x003d3098 OK
Razer        exit2:xr:                off=0x020070dc OK
razerdaemon  requestDeviceInfo:       off=0x0047430c OK
```

`codesign --verify --deep --strict` 结果：

- `var/jb/Applications/razer.app`：valid on disk，satisfies its Designated Requirement
- `var/jb/usr/bin/razerdaemon`：valid on disk，satisfies its Designated Requirement

最终 `deb_audit`：

- `lfs_pointer=false`
- `Razer` SHA256：`308c9b3193f926a5267a70c59730d325e8b1d0d7db9892b196ff25c112e39207`
- `razerdaemon` SHA256：`3917fbec49271adce2f0b63e7102772b54c8eba12ce0b90034516b7a321baa37`
- 其他 Mach-O hash 与原始样本一致。

## 8. 运行时注意事项

当前验证为静态证据链 + 最终 deb 反解包 byte 验证 + codesign 验证，未在真实越狱 iOS 环境做 1～2 分钟存活测试。如果仍出现弹窗或延迟闪退，下一轮应优先检查：

1. `Razer` 中 `showAlert:` 是否仍由其他授权失败分支调用。
2. `razerdaemon` 中 `Reconnect` / `connectionClosed:` / MQTT failure branch 是否调度新的 kill/restart。
3. `razer.dylib` 是否在注入 UIKit 进程后还有独立 `abort`/timer 逻辑。
4. VM 分发器 `0x10200b624` / daemon `sym._104` 中对应 opcode 的共享 failure handler。

## 9. Pages 源同步验证

本轮 `pages-repo/` 挂载已完成目标的最终 patch 包：

```text
pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
SIZE=6206412 bytes
SHA256=0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866

pages-repo/debs/app.Razer854.rootless_2.5.0_nopopup_noexpire_noheartbeat_noexit.deb
SIZE=21215306 bytes
SHA256=bffe9d57de415d70c6723e90e9aca0f2c17da123abd10e812243db3a1f8505ef
```

`pages-repo/Packages` 包含两条记录：

```text
Package: com.amg456.rootless
Version: 18.1.1
Filename: ./debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
SHA256: 0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866

Package: app.Razer854.rootless
Version: 2.5.0
Filename: ./debs/app.Razer854.rootless_2.5.0_nopopup_noexpire_noheartbeat_noexit.deb
SHA256: bffe9d57de415d70c6723e90e9aca0f2c17da123abd10e812243db3a1f8505ef
```

同步校验命令：

```bash
python3 scripts/build_pages_repo.py
gzip -t pages-repo/Packages.gz
find pages-repo/debs -maxdepth 1 -type f -name '*.deb' | wc -l
shasum -a 256 pages-repo/debs/*.deb
git check-attr filter diff merge text -- pages-repo/Packages.gz pages-repo/debs/*.deb
```

结论：`pages-repo/debs/` 有 2 个 deb（AMG 最终包 + Razer 最终包）；`Packages.gz` 可解压；`pages-repo/.gitattributes` 对 `.deb` / `.gz` 生效为普通 Git blob；未发现 Git LFS pointer。
