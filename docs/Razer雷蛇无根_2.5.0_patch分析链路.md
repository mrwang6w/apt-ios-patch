# Razer 雷蛇无根 2.5.0 patch 分析链路

## 1. 样本与最终产物

- 原始 deb：`/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/2.5.0_Razer雷蛇(无根)_2.5.0_app.Razer854.rootless.deb`
- 原始 SHA256：`e1da2c3995ab653609671d0dd75adf9f65669378c089a0386070635bd4c16d1d`
- 原始 size：`21521984` bytes
- Package：`app.Razer854.rootless`
- 原始 Version：`2.5.0`
- 最终 Patch Version：`2.5.0-11`
- Architecture：`iphoneos-arm64`
- 最终 deb：`/Users/zest/myworks/apt-ios-patch/patched/2.5.0_Razer雷蛇(无根)_2.5.0-11_app.Razer854.rootless_authstate_ustar.deb`
- 最终 SHA256：`53deb601ec0458da67379ddd0390b5f57e06ef7549079756bb3f7c8f351a8e21`
- 最终 size：`21217862` bytes

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

v8 真机反馈仍为“请输入授权码 / error 未授权 / 1970.01.01 08:00”。Frida native-only 证据显示 v8 的 `NSDictionary` 基类方法没有捕获授权读取，而具体 `__NSDictionaryM` 已捕获 `LicenseAccepted` 读取；因此 v11 将状态覆盖下沉到具体类簇，并仅在包含 `License`、`Authorization`、`ExpiredText` 或 `LicenseAccepted` 的响应字典中覆盖 `retcode`、`retCode`、`code`，同时保留 `LicenseAccepted` 与 `ExpiredText` 覆盖。

## 4. 真机反馈后的修复策略

用户真机反馈 `2.5.0-2` 仍出现：

- `error未授权`
- 点击 `Authorization/授權` 弹 `請輸入授權碼`
- 点击 `[全面清理]` 也要求授权码
- 授权过期时间显示 `1970.01.01 08:00`
- 点击刷新按钮弹 `error未授权`

根因复盘：`2.5.0-2`/中间态曾把主控 `viewDidAppear:`、授权页 `viewDidAppear:`、daemon `requestDeviceInfo:` 直接 `ret`，副作用是刷新和授权状态回填链路不再执行，时间字段回退到 0。

`2.5.0-4`/`2.5.0-5`/`2.5.0-6` 策略：

1. 恢复 `viewDidAppear:` 与 `requestDeviceInfo:`，保留刷新/一键新机业务入口。
2. 保留明确的弹窗/退出入口静态 `ret`：`requestlicense`、两组 `showAlert:`、`buttonAuthTapped`、`checkUpdate`、退出路径。
3. 新增 `RazerAuth2099.dylib` 运行期 hook，只在主进程 `Razer` 启用：
   - `NSUserDefaults`：`LicenseAccepted => YES`，`ExpiredText => 2099.01.01 00:00`。
   - `2.5.0-4`/`2.5.0-5` 曾尝试全局 `NSDictionary`/子类兜底；Frida 证明会影响 CoreFoundation / ColorSync，`2.5.0-6` 已移除。
   - `UILabel setText:`：把 `1970.01.01`、`未授权/未授權/Unauthorized/license expired` 文案替换为 `2099.01.01 00:00`。
   - `UIViewController presentViewController:`：兜底拦截授权码/未授权相关 `UIAlertController`。

这样修复用户提出的几条现象：授权判断读到 valid，过期时间读到 2099；刷新按钮不会再因被 `ret` 掐断而回 1970；一键新机入口不再被直接 `ret`，而是在进入前授权 predicate 被 hook 为有效。


## 4.1 真机启动闪退复盘与 `2.5.0-6` 修复

用户安装 `2.5.0-4` 后打开即闪退。通过 USB 拉取真机 crash report：

- 设备：`iPhone9,2` / iOS `15.8.8 (19H422)` / `arm64`
- crash：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/evidence/device-crashreports/Razer-2026-07-10-012825.ips`
- 摘要：`EXC_CRASH (SIGABRT)`，`abort() called`
- 关键栈：`RazerAuth2099Init+260 -> _objc_msgSend_uncached -> +[UIView initialize] -> CGColorSpaceExtendedSRGB -> create_sRGBProfile -> std::terminate`
- 证据摘要留存：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/evidence/startup-crash-2.5.0-4/crash-summary.txt`

根因：`2.5.0-4` 的 `RazerAuth2099Init` 构造函数在 dyld 执行 tweak constructors 阶段直接访问 `UILabel` / `UIViewController` 并 swizzle UIKit 方法，触发 `+[UIView initialize]`，在 iOS 15.8.8 / Dopamine / ElleKit 注入链路中稳定 abort。

`2.5.0-5`/`2.5.0-6` 最小修复：

1. constructor 只做最小 `NSUserDefaults` 授权/过期字段 hook。
2. `UILabel setText:` 与 `UIViewController presentViewController:` 的 swizzle 改为收到 `UIApplicationDidFinishLaunchingNotification` 后安装，不再用 constructor 或提前 main-queue fallback 触碰 UIKit。
3. `2.5.0-6` 根据 Frida 证据移除全局 `NSDictionary` swizzle，避免影响 CoreFoundation / ColorSync 内部字典实现。
4. hook dylib 重新 ad-hoc codesign，最终反解包校验 `codesign -vv` 通过。



Frida 复核：

- 探针脚本：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/evidence/frida/razer_launch_probe.py`
- 原始日志：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/evidence/frida/razer-launch-probe-20260710-015021.log`
- 摘要：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/evidence/frida/razer-launch-probe-summary.txt`

Frida 捕获到旧安装包启动时：

```text
dlopen path=/var/jb/usr/lib/TweakInject/RazerAuth2099.dylib
+[UIView initialize] -> ColorSync.framework/ColorSync
objc_exception_throw inside CoreFoundation -[NSDictionary objectForKey:]
ENTER abort -> pthread_kill -> process-terminated
```

因此 `2.5.0-6` 不再做全局字典类替换，只保留 `NSUserDefaults` 授权状态和启动后 UI 兜底；复查时已进一步删除源码/dylib 中残留的 `NSDictionary` hook 死代码，最终二进制不再包含 `objectForKeyedSubscript`/`rz2099_objectForKeyedSubscript` 等字典 hook 字符串。

最终 v6 hook 字符串验证包含：

```text
[RazerAuth2099Hook] enabled: LicenseAccepted=YES ExpiredText=%@; post-launch hooks deferred
[RazerAuth2099Hook] post-launch hooks installed
```

## 5. Patch 点表

### 5.1 v7 主面板 action 修复

真机反馈 v6 虽隐藏了所有授权码弹窗，但 `[全面清理]`、`[历史记录]` 等主面板 action 无法完成。原因不是 `cleanDataClicked:` 仍被 patch，而是补丁错误地在 UI 层同时做了两件事：

1. 直接把 `requestlicense`、两组 `showAlert:` 和 `buttonAuthTapped` 函数首指令改为 `ret`。
2. 全局 hook `UIViewController presentViewController:animated:completion:`，命中未授权文本即直接返回。

这两个位置只能隐藏失败结果，不能让 VM dispatcher 中的授权 predicate 通过；并且吞掉原始 `presentViewController:` 会破坏业务 action 依赖的完成时序。

v7 恢复上述四处 VM trampoline prologue `ff 03 10 d1`，移除 `UILabel setText:` 和 `UIViewController presentViewController:` swizzle。v11 的 `RazerAuth2099.dylib` 不链接 UIKit，在 `UIApplicationDidFinishLaunchingNotification` 后仅对具体 `NSDictionary` 类簇及 `NSUserDefaults` 的授权响应读取返回有效值；业务 selector、alert 和 completion 保持原始实现。

| Binary | Arch | Function / symbol | VA | file offset | old bytes | new bytes | reason |
|---|---|---:|---:|---:|---|---|---|
| `var/jb/Applications/razer.app/Razer` | arm64 | `requestlicense` | `0x1003d2018` | `0x003d2018` | `c0 03 5f d6` (v6) | `ff 03 10 d1` | 恢复原始授权 UI/业务调用，不在函数入口吞调用。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `showAlert:`（主控组） | `0x1003d2fe0` | `0x003d2fe0` | `c0 03 5f d6` (v6) | `ff 03 10 d1` | 恢复主控 action 的原始失败处理与 completion 时序。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `buttonAuthTapped` | `0x100d97694` | `0x00d97694` | `c0 03 5f d6` (v6) | `ff 03 10 d1` | 恢复授权按钮原始调用链。 |
| `var/jb/Applications/razer.app/Razer` | arm64 | `showAlert:`（授权页组） | `0x100d9b8c0` | `0x00d9b8c0` | `c0 03 5f d6` (v6) | `ff 03 10 d1` | 不再以 alert 层作为授权绕过点。 |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib` | arm64 | post-launch auth state hook | N/A | N/A | v6 UIKit UI swizzle | v7 `NSDictionary`/`NSUserDefaults` scoped read override | 强制授权 state，而不拦截 UI 或业务回调。 |

v7 的业务修复在安装阶段暴露了归档兼容性缺陷，v8 曾修复 USTAR 归档并验证通过；v11 在此基础上重新重包。v11 反解包验证：`Package=app.Razer854.rootless`、`Version=2.5.0-11`、三段 deb member 正常；上述四个 offset 均为 `ff0310d1`。`codesign --verify --deep --strict razer.app` 与 `codesign --verify --strict RazerAuth2099.dylib` 均通过。hook 的 `otool -L` 只有 Foundation/CoreFoundation/libobjc/libSystem，不含 UIKit；字符串检查不含 `presentViewController:`、`UILabel`、`UIViewController` 或 `setText:`。

### 5.4 v11 具体字典类簇状态修复

v11 源码：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/patch-src/RazerAuth2099Hook.m`。

- `NSDictionary` 是 class cluster；仅交换抽象基类不能覆盖 `__NSDictionaryI` / `__NSDictionaryM` 等实际响应对象。
- v11 在应用完成启动后保存每个具体类的原始 IMP，并用 `method_setImplementation` 安装 wrapper；wrapper 沿 superclass 查找 entry，避免具体字典子类因找不到 entry 而错误返回 `nil`。
- 状态覆盖为 `LicenseAccepted=YES`、`ExpiredText=2099.01.01 00:00`；只有授权响应字典同时包含授权相关字段时，才覆盖 `retcode`、`retCode`、`code` 为 `0`，没有吞掉 alert 或 action。
- native-only Frida 探针、无脚本 spawn 基线和具体类命中日志均留存在 `evidence/frida/`；启动期全局 `objc_msgSend` 版本导致进程终止的失败日志也保留，未用于最终包。
- 具体类命中日志来自 v11 安装前的当前真机版本，仅证明授权读取位于 `__NSDictionaryM` 路径；v11 包本身已完成静态、签名和归档验证，安装后的授权成功 UI 回归仍需单独验证。

### 5.2 v7 安装失败与 v8 USTAR 重包修复

Sileo 安装 v7 的明确错误为：`corrupted filesystem tarfile in package archive: unsupported PAX tar header type 'x'`。

根因是 v7 使用 macOS BSD `tar -czf` 生成 `control.tar.gz` 和 `data.tar.gz`。该实现写入 PAX `typeflag=x` 以及 `._*` AppleDouble 元数据；设备端 dpkg 不支持 PAX header，因此在解包前拒绝整个 deb。v8 使用 GNU tar：`--format=ustar --mtime=@0 --owner=0 --group=0 --numeric-owner --no-xattrs --sort=name`，并在打包前和最终 deb 反解包后扫描每个 512-byte tar header，只接受普通文件 `0` 和目录 `5`，同时拒绝 `._*`。

v8 验证结果：`control.tar.gz: members=6 typeflags=0,5`，`data.tar.gz: members=232 typeflags=0,5`。因此没有 `x`、`g`、`e` 等扩展 header，兼容 Sileo/dpkg 的 tar parser。`scripts/build_pages_repo.py` 与 Pages GitHub Actions 也会在发布前拒绝 PAX/AppleDouble 成员；同时保留对 AMG 既有 GNU long-name `L/K` header 的兼容。

### 5.3 v6 历史静态 patch 表

以下表格只记录已废弃的 v6 静态 patch，不能用于 v11。所有 VA 均基于 Mach-O image base `0x100000000`，file offset = `VA - 0x100000000`；当时新增的静态指令为 ARM64 `ret`：`c0 03 5f d6`。v11 当前 `requestlicense`、两组 `showAlert:` 和 `buttonAuthTapped` 均已恢复为 `ff 03 10 d1`，以保留主面板 action 调用链。

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
| `var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib` | arm64 | constructor / ObjC swizzle | N/A | N/A | 文件不存在 | 新增 dylib，SHA256 `1d007ad80b156a916c34c81fcdc72ea6742148932ecbdab7ec42cbc948a6f1fe` | hook `LicenseAccepted`、`ExpiredText`、残留授权 alert，强制 2099 授权态；`2.5.0-6` 移除全局 `NSDictionary` swizzle，并将 UIKit swizzle 延后到 app launch 后，避免启动期初始化 `UIView` / ColorSync 字典异常闪退。 |

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

当前最终验证目录：`/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/verify-final-2.5.0-11/`。

最终 `deb_audit`：

```text
/Users/zest/myworks/apt-ios-patch/work/app.Razer854.rootless-2.5.0/final-audit-2.5.0-11/
lfs_pointer=false
Package=app.Razer854.rootless
Version=2.5.0-11
```

最终 deb 反解包 byte 验证：

```text
Razer        checkUpdate                      off=0x003cee84 got=c0035fd6 OK
Razer        requestlicense restored          off=0x003d2018 got=ff0310d1 OK
Razer        main showAlert restored          off=0x003d2fe0 got=ff0310d1 OK
Razer        buttonAuthTapped restored        off=0x00d97694 got=ff0310d1 OK
Razer        license showAlert restored       off=0x00d9b8c0 got=ff0310d1 OK
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

pages-repo/debs/app.Razer854.rootless_2.5.0-11_authstate_ustar.deb
SIZE=21217862
SHA256=53deb601ec0458da67379ddd0390b5f57e06ef7549079756bb3f7c8f351a8e21
```

`pages-repo/Packages` 包含两条记录：

```text
Package: com.amg456.rootless
Version: 18.1.1
Filename: ./debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb

Package: app.Razer854.rootless
Version: 2.5.0-11
Filename: ./debs/app.Razer854.rootless_2.5.0-11_authstate_ustar.deb
```

没有在仓库根目录复制 `index.html`、`Packages`、`debs/` 等重复 Pages 产物；所有展示前端和 APT 静态源只位于 `pages-repo/`。
