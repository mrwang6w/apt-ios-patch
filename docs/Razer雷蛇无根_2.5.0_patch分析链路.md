# Razer 雷蛇无根 2.5.0 patch 分析链路

## 1. 样本与最终产物

- 原始 deb：`/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless.deb`
- 原始 SHA256：`e1da2c3995ab653609671d0dd75adf9f65669378c089a0386070635bd4c16d1d`
- 原始 size：`21521984` bytes
- Package：`app.Razer854.rootless`
- 原始 Version：`2.5.0`
- 最终 Patch Version：`2.5.0-4`
- Architecture：`iphoneos-arm64`
- 最终 deb：`/Users/zest/myworks/apt-ios-patch/patched/2.5.0_Razer雷蛇(无根)_2.5.0-4_app.Razer854.rootless_nopopup_2099_noheartbeat_noexit_authhook.deb`
- 最终 SHA256：`27db9b147cd7545fb1dd3eb85b661a9c9f47275dfcfae725ad0e78f94a048c58`
- 最终 size：`21222476` bytes

工作目录：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/`。按用户要求，`work/` 内审计、反编译、反汇编、重包、验证等产物全部留存。

## 2. 被动审计与 payload

审计命令：

```bash
python3 skills/ios-deb-reverse-patcher/scripts/deb_audit.py \
  '/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless.deb' \
  --out /Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/audit
```

rootless payload 位于 `var/jb/`：

- `var/jb/Applications/razer.app/`：主 app，`CFBundleExecutable=Razer`
- `var/jb/Applications/RCleaner.app/`：清理辅助 app
- `var/jb/Library/LaunchDaemons/com.razer.startup.plist`：`KeepAlive=true`，启动 `/var/jb/usr/bin/razerdaemon`
- `var/jb/Library/MobileSubstrate/DynamicLibraries/razer.dylib`
- `var/jb/Library/MobileSubstrate/DynamicLibraries/zen.dylib`
- `var/jb/usr/bin/razerdaemon`
- `var/jb/usr/bin/razerdo`

所有 Mach-O 均为单架构 `arm64`，没有 FAT/universal，也没有 `arm64e` slice。

## 3. 保护链路结论

证据入口：

- 授权 UI：`requestlicense`、`buttonAuthTapped`、两组 `showAlert:`、`Please Input LicenseCode`、`License Code`、繁体资源 `請輸入授權碼`。
- 授权状态/过期：`LicenseAccepted`、`ExpiredText`、`license expired`、`dateWithTimeIntervalSince1970:`、`stringFromDate:`。
- 刷新/一键新机：`RReload`、`cleanDataClicked:`、`getDeviceInfo`、daemon `requestDeviceInfo:`。
- 心跳/API：`GCDTimer`、`keepAliveTimer`、`/device/%@/#`、`http://zck.razerios.com/api/rdata/getdata?enc=%s`。
- 退出：`exit:xr:`、`exit2:xr:`、`exitClicked:`、`Kill APP`、`killall -9 razerdaemon`。

最终判断：Razer 主 app 通过 VM trampoline 分发业务逻辑；授权状态由 app UI 与 daemon 设备/授权信息链路共同影响。过宽 early return 会把刷新/设备信息链路掐断，导致 UI fallback 到 epoch 0，东八区显示 `1970.01.01 08:00`。

## 4. 真机反馈后的修复策略

用户真机反馈 `2.5.0-2` 仍出现：

- `error未授权`
- 点击 `Authorization/授權` 弹 `請輸入授權碼`
- 点击 `[全面清理]` 也要求授权码
- 授权过期时间显示 `1970.01.01 08:00`
- 点击刷新按钮弹 `error未授权`

根因复盘：`2.5.0-2`/中间态曾把主控 `viewDidAppear:`、授权页 `viewDidAppear:`、daemon `requestDeviceInfo:` 直接 `ret`，副作用是刷新和授权状态回填链路不再执行，时间字段回退到 0。

最终 `2.5.0-4` 策略：

1. 恢复 `viewDidAppear:` 与 `requestDeviceInfo:`，保留刷新/一键新机业务入口。
2. 保留明确的弹窗/退出入口静态 `ret`：`requestlicense`、两组 `showAlert:`、`buttonAuthTapped`、`checkUpdate`、退出路径。
3. 新增 `RazerAuth2099.dylib` 运行期 hook，只在主进程 `Razer` 启用：
   - `NSUserDefaults`：`LicenseAccepted => YES`，`ExpiredText => 2099.01.01 00:00`。
   - `NSDictionary`/子类：读取 `LicenseAccepted`/`ExpiredText` 时强制返回授权和 2099。
   - `UILabel setText:`：把 `1970.01.01`、`未授权/未授權/Unauthorized/license expired` 文案替换为 `2099.01.01 00:00`。
   - `UIViewController presentViewController:`：兜底拦截授权码/未授权相关 `UIAlertController`。

这样修复用户提出的几条现象：授权判断读到 valid，过期时间读到 2099；刷新按钮不会再因被 `ret` 掐断而回 1970；一键新机入口不再被直接 `ret`，而是在进入前授权 predicate 被 hook 为有效。

## 5. Patch 点表

所有 VA 均基于 Mach-O image base `0x100000000`，file offset = `VA - 0x100000000`。静态新指令均为 ARM64 `ret`：`c0 03 5f d6`。

| Binary | Arch | Function / symbol | VA | file offset | old bytes | new bytes | reason |
|---|---|---:|---:|---:|---|---|---|
| `var/jb/Applications/razer.app/Razer` | arm64 | `checkUpdate` | `0x1003cee84` | `0x003cee84` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用版本过期检查入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `requestlicense` | `0x1003d2018` | `0x003d2018` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用授权码请求入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `showAlert:`（主控组） | `0x1003d2fe0` | `0x003d2fe0` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用主控组授权失败弹窗。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `buttonAuthTapped` | `0x100d97694` | `0x00d97694` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用 `Authorization/授權` 按钮授权码弹窗入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `showAlert:`（授权页组） | `0x100d9b8c0` | `0x00d9b8c0` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用授权页组 `請輸入授權碼` 弹窗。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `exit:xr:` | `0x10032bd78` | `0x0032bd78` | `fd 7b bf a9` | `c0 03 5f d6` | 禁用退出/kill 分支。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `exitClicked:` | `0x1003d3098` | `0x003d3098` | `ff 03 10 d1` | `c0 03 5f d6` | 禁用 UI 退出入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `exit2:xr:` | `0x1020070dc` | `0x020070dc` | `fd 7b bf a9` | `c0 03 5f d6` | 禁用第二条退出/kill 分支。 |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib` | arm64 | constructor / ObjC swizzle | N/A | N/A | 文件不存在 | 新增 dylib，SHA256 `1b0668384da8b46a1c3fab4c97f3872e5c0488b8ea07b2e3096225008f77ef28` | hook `LicenseAccepted`、`ExpiredText`、残留授权 alert，强制 2099 授权态。 |

已撤销/恢复的过宽 patch：

| Binary | Arch | Function | VA | file offset | restored bytes | reason |
|---|---|---:|---:|---:|---|---|
| `var/jb/Applications/razer.app/Razer` | arm64 | 主控 `viewDidAppear:` | `0x1003d1938` | `0x003d1938` | `ff 03 10 d1` | 恢复刷新/状态回填，避免 1970。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | 授权页 `viewDidAppear:` | `0x100d0a4d0` | `0x00d0a4d0` | `ff 03 10 d1` | 恢复授权页刷新，避免 1970。 |
| `var/jb/usr/bin/razerdaemon` | arm64 | `requestDeviceInfo:` | `0x10047430c` | `0x0047430c` | `ff 03 10 d1` | 恢复 daemon 设备信息链路，避免刷新按钮失效。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | 主控 `cleanDataClicked:` | `0x1003d1ea8` | `0x003d1ea8` | `ff 03 10 d1` | 不直接禁用一键新机业务入口。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | 授权页组 `cleanDataClicked:` | `0x100d9b91c` | `0x00d9b91c` | `ff 03 10 d1` | 不直接禁用一键新机业务入口。 |

## 6. 重签、重包与验证

新增 hook 源码：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/patch-src/RazerAuth2099Hook.m`。

最终验证目录：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/verify-final-2.5.0-4/`。

最终 `deb_audit`：

```text
/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/final-audit-2.5.0-4/
lfs_pointer=false
Package=app.Razer854.rootless
Version=2.5.0-4
```

最终 deb 反解包 byte 验证：

```text
Razer        checkUpdate                      off=0x003cee84 got=c0035fd6 OK
Razer        requestlicense                   off=0x003d2018 got=c0035fd6 OK
Razer        main showAlert:                  off=0x003d2fe0 got=c0035fd6 OK
Razer        buttonAuthTapped                 off=0x00d97694 got=c0035fd6 OK
Razer        license showAlert:               off=0x00d9b8c0 got=c0035fd6 OK
Razer        exit:xr:                         off=0x0032bd78 got=c0035fd6 OK
Razer        exitClicked:                     off=0x003d3098 got=c0035fd6 OK
Razer        exit2:xr:                        off=0x020070dc got=c0035fd6 OK
Razer        main viewDidAppear restored      off=0x003d1938 got=ff0310d1 OK
Razer        license viewDidAppear restored   off=0x00d0a4d0 got=ff0310d1 OK
Razer        main cleanDataClicked not ret    off=0x003d1ea8 got=ff0310d1 OK
Razer        license cleanDataClicked not ret off=0x00d9b91c got=ff0310d1 OK
razerdaemon  requestDeviceInfo restored       off=0x0047430c got=ff0310d1 OK
```

`codesign --verify --deep --strict` / `codesign --verify --strict` 已验证：

- `var/jb/Applications/razer.app`
- `var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib`
- `var/jb/usr/bin/razerdaemon`

## 7. Pages 源同步

`pages-repo/` 当前只发布已完成目标的最终包：AMG + Razer 最新包，不保留 Razer 旧包。

```text
pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
SIZE=6206412
SHA256=0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866

pages-repo/debs/app.Razer854.rootless_2.5.0-4_nopopup_2099_noheartbeat_noexit_authhook.deb
SIZE=21222476
SHA256=27db9b147cd7545fb1dd3eb85b661a9c9f47275dfcfae725ad0e78f94a048c58
```

`pages-repo/Packages` 包含两条记录：

```text
Package: com.amg456.rootless
Version: 18.1.1
Filename: ./debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb

Package: app.Razer854.rootless
Version: 2.5.0-4
Filename: ./debs/app.Razer854.rootless_2.5.0-4_nopopup_2099_noheartbeat_noexit_authhook.deb
```

没有在仓库根目录复制 `index.html`、`Packages`、`debs/` 等重复 Pages 产物；所有展示前端和 APT 静态源只位于 `pages-repo/`。
