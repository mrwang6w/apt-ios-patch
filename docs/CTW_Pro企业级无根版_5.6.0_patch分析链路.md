# CTW Pro 企业级无根版 5.6.0 深度去授权 Patch 分析链路

> 历史状态：本文记录 `com.xxdevice.CTWPro.Rootless560` 的独立补丁与真机验证证据。
> 该包与后续 `com.amg456` 版本写入相同载荷路径，现已从 Pages 下线；当前发布链见
> `docs/CTW_Pro无根版_5.6.0_amg456深度离线补丁链路.md`。本文中的哈希和真机记录
> 仍作为旧版本证据保留。

## 1. 输入与目标

原始 deb：

```text
/Users/zest/myworks/apt-ios-patch/downloads/ctwpro-repo/debs/CTW_Pro(无根版)_5.6.0_com.xxdevice.CTWPro.Rootless560.deb
Size:   22,252,632 bytes
SHA256: f10c545f65c81bc4d69afd5335c7fcd19d00ab3ca8b74d1227820996ebca54ef
```

包元数据：

```text
Package:      com.xxdevice.CTWPro.Rootless560
Version:      5.6.0
Architecture: iphoneos-arm64
Rootless:     var/jb/
```

目标不是隐藏弹窗，而是闭合主程序内完整的“捐赠码”链：输入/扫码入口、提交
delegate、响应后的自动弹窗、状态消费者、节点适配、定时复查和锁 UI；同时移除
后加 `extend.bin` 网络层，不修改实际改机实现。

## 2. Payload 与临时版边界

主要 Mach-O：

| 路径 | 架构 | 原始 SHA256 |
| --- | --- | --- |
| `var/jb/Applications/CTW Pro.app/CTW Pro` | arm64 | `8f28fe5e4e44f533902ffe4992e91a1a16da7e68aaeae84ee7632cf443ba10bc` |
| `var/jb/Applications/CTW Pro.app/extend.bin` | arm64 | `44383659b25fa629e183de924d786536690f86d4ca0f9748694bcd983a931480` |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib` | arm64 | `627914668f3328024db23c6a109c4a66e21df5a07b84eaeed38153b2924b4d9b` |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/ctwsup.dylib` | arm64 + arm64e | `2ee8a33a594f46fbe4b98a49c7571bcb1a0c2445c6347be7f780536ded6a86e8` |
| `var/jb/usr/bin/ctwsrv` | armv7 + arm64 | `c6f0b9465fd2b76fff2e8783ce97209aad20ef238e230e18da3a3652e8ab9701` |

`5.6.0-1` 只把 `@executable_path/extend.bin` 改成不存在的弱依赖
`@executable_path/.nolicense`，并删除 `extend.bin`。真机证明确认主程序自身仍会：

- 显示“正在适配网络节点...”和周期性的“测试权限:(null)”。
- 打开“输入捐赠码”弹窗，支持 `recharge:`、扫码和确认提交。
- 继续执行节点检测、`/getlocation` 和 `lockUI:` 消费者。

因此 `5.6.0-1` 是临时版，不能视为完整去授权版本。

## 3. 后加 extend.bin

原主程序最后一个依赖命令为：

```text
Load command 47
          cmd LC_LOAD_DYLIB
      cmdsize 56
         name @executable_path/extend.bin (offset 24)
```

`extend.bin` 的 initializer 位于 `0x4D88`，0.5 秒后进入网络/swizzle 初始化；其
`__DATA,__interpose` 覆盖 `SecKeyCreateEncryptedData`、`exit`、`_exit` 和
`kill`。它没有主程序必须解析的导出业务 API，因此删除整个模块比局部 NOP 其
网络或退出分支更稳定。

## 4. 主程序运行时证据

Frida 17 使用原生 ObjC/CoreFoundation C API；稳定证据保存在：

```text
work/ctwpro-rootless-5.6.0/evidence/frida/ctw-donation-probe-v11.jsonl
work/ctwpro-rootless-5.6.0/evidence/frida/ctw-deep-5.6.0-2-runtime-v3.jsonl
work/ctwpro-rootless-5.6.0/evidence/frida/ctw-deep-5.6.0-2-runtime-v4-unattended.jsonl
```

主程序通过 `class_replaceMethod` 动态恢复 `ViewController` 业务实现。原始关键
IMP：

| selector | 主程序偏移 | 作用 |
| --- | ---: | --- |
| `showQRCodeView:` | `0x4dccb0` | 捐赠二维码入口 |
| `scanQRCode:` | `0x4e1c8c` | 扫码入口 |
| `qrCodeScannerDidScanResult:` | `0x4e2530` | 扫码结果消费者 |
| `Jvgn...DwaNkQ` | `0x4e6700` | 响应完成后的自动捐赠弹窗消费者 |
| `viewDidLoad` | `0x5025c0` | 启动 UI 与节点适配 |
| `alertView:clickedButtonAtIndex:` | `0x50c684` | “退出/确认”提交 delegate |
| `updateUITimer` | `0x515af0` | 约 2 秒一次的状态/UI 消费者 |
| `lockUI:` | `0x557560` | 锁定核心控件 |
| `recharge:` | `0x557bc0` | 捐赠码手动入口 |

捐赠弹窗实测：

```text
title:  输入捐赠码
cancel: 退出
other:  确认
submit index: 1
```

启动链实测：

```text
viewDidLoad
-> writeCTWCacheEnv (caller +0x504b64)
-> UILabel “正在适配网络节点...” (caller +0x504be8)
-> /upload3
-> /api/checkNews, /api/getuiconfig, /api/announcement
-> /upload?data=...
-> updateUITimer / isInNetwork
-> /getlocation
```

当前 `api.ctwvip.xyz` 对这些请求统一返回 `HTTP 502 Bad Gateway`。原包仍把失败
结果送入授权/UI 消费者，形成卡节点、捐赠弹窗和无效权限文本。

## 5. 5.6.0-2 补丁设计

### 5.1 强加载本地修复模块

保持 56 字节 load command 长度和强依赖语义，只替换路径：

| 架构 | 文件偏移 | 旧值 | 新值 |
| --- | ---: | --- | --- |
| arm64 | `0x1440` | `LC_LOAD_DYLIB` | `LC_LOAD_DYLIB` |
| arm64 | `0x1458` | `@executable_path/extend.bin` | `@executable_path/fix.dylib` |

最终结果：

```text
Load command 47
          cmd LC_LOAD_DYLIB
      cmdsize 56
         name @executable_path/fix.dylib (offset 24)
```

包内删除 `extend.bin`，新增并单独签名 `fix.dylib`。

### 5.2 动态 IMP 覆盖

`fix.dylib` 用后台短周期等待主程序完成动态注册，再通过 `dladdr(IMP)` 验证镜像
确为 `/CTW Pro` 且相对偏移匹配。不能使用 `_dyld_get_image_header(0)`：真机
实测该调用在此 dyld 闭包中返回 `fix.dylib` 基址，而不是主程序基址。

运行期覆盖：

| selector/消费者 | 行为 |
| --- | --- |
| `recharge:` | no-op |
| `showQRCodeView:` / `scanQRCode:` / `qrCodeScannerDidScanResult:` | no-op |
| `Jvgn...DwaNkQ` | no-op，关闭响应后自动捐赠弹窗 |
| 捐赠标题的 `alertView:clickedButtonAtIndex:` | no-op，关闭确认提交与“退出”分支 |
| `lockUI:` | no-op |
| `isNeedCheckIP` / `isNeedFlushIP` | 始终 `NO` |
| 两个状态 setter | 只允许写 `NO` |
| `viewDidLoad` / `updateUITimer` | 调原实现后恢复本地状态、启用核心控件、隐藏捐赠 action 控件 |
| `UILabel setText:` | 精确替换“正在适配网络节点...”和“测试权限:(null)” |

本地状态显示为“网络节点已就绪”和“测试权限:永久”。NSUserDefaults sentinel
`CTWProDeepPatchLocalAuthorization=YES` 只用于标识修复模块已运行；真正的保障来自
上述消费者覆盖，不把 sentinel 冒充原授权源。

`performeMachineStub`、`performeMachine:`、`nativeMachine:` 未修改，避免破坏核心
改机逻辑。

## 6. 构建、签名与归档

实现文件：

```text
work/ctwpro-rootless-5.6.0/patch-src/CTWProDeepPatch.m
scripts/patch_ctwpro_rootless_deep.py
scripts/build_ctwpro_rootless_deep.sh
```

构建过程：

1. 校验原 deb 和原主程序 SHA256。
2. 编译 arm64/iOS 12+ `fix.dylib`，install name 为
   `@executable_path/fix.dylib`，关闭随机 UUID。
3. 校验并替换完整 56 字节 load command，删除 `extend.bin`。
4. 单独签名 dylib，并使用原主程序 38 项 entitlement 重签 app。
5. control 版本提升到 `5.6.0-2`。
6. 使用 deterministic USTAR、`gzip -n` 和固定 Unix ar 重包。
7. 从候选 deb 重提取，重复 load command、签名、权限、control 和归档验证。

最终签名文件：

```text
CTW Pro SHA256: fca654d7cce9db0c87c375142741e45761ab6dcc8f92618b80e9bdae04b1d9a0
fix.dylib SHA256: ce8f19dfbc070f78f0ebb13e3f977cbf70416544e0dd6427cedf7603ddd4ab35
Signature: ad-hoc
Entitlement keys: 38
```

## 7. 最终产物

```text
/Users/zest/myworks/apt-ios-patch/patched/CTW_Pro企业级(无根版)_5.6.0-2_com.xxdevice.CTWPro.Rootless560_deep_nolicense_ustar.deb
Size:   21,969,212 bytes
SHA256: 68e14a7f8c17d181fb48a0dc16eadd7a85ce635470d3f339ba0973f3c2e4a9cb
```

连续两次从固定原包完整构建的 SHA256 一致。最终 deb 是标准三成员 Debian ar；
control/data 均为 USTAR + deterministic gzip，无 PAX、AppleDouble 或 LFS pointer。

复现：

```bash
./scripts/build_ctwpro_rootless_deep.sh
shasum -a 256 'patched/CTW_Pro企业级(无根版)_5.6.0-2_com.xxdevice.CTWPro.Rootless560_deep_nolicense_ustar.deb'
```

## 8. 真机验证

设备：`iPhone9,2 / iOS 15.8.8 / Frida 17.11.0`。

安装时通过 root `frida-server` 上传并调用设备端 `dpkg`；设备端 deb SHA256 与本地
一致，`dpkg-query` 返回：

```text
ii  com.xxdevice.ctwpro.rootless560 5.6.0-2 iphoneos-arm64
```

65 秒无人干预验收结果（约 32 个 UI timer 周期）：

- `fix.dylib` 从实际 app 路径加载。
- 14 个目标 IMP 均由 `fix.dylib` 替换。
- “输入捐赠码”弹窗 `0`，提交 `0`，`/getlocation` `0`。
- `lockUI:` `0`，`exit/_exit/kill/abort` `0`，探针错误 `0`。
- 8/15/30/55 秒快照均为“测试权限:永久 / 网络节点已就绪”。
- `isNeedCheckIP=0`、`isNeedFlushIP=0` 始终保持。

主动调用已替换的 `recharge:` 后也没有弹窗或提交；扫码与自动响应消费者使用同一
精确 IMP 覆盖策略。

## 9. 核心功能网络边界

真机点击“随机生成参数”时，原核心函数新增请求：

```text
http://api.ctwvip.xyz/vd?data=...
```

该请求返回 `HTTP 502`，随后原程序在 `CTW Pro+0xa5584` 显示：

```text
新机生成失败
超时或非法请求,请检查网络连接!
```

因此随机新机参数至少此流程依赖已失效的后端 `/vd`。补丁没有修改
`performeMachine*` 或 `nativeMachine:`；该失败是独立的服务端不可用，不是授权
消费者回归。真机手动执行“重置并退出”产生的 `CTW Pro+0x3b1370 -> exit(0)` 也
属于用户确认的正常重置路径，不归类为授权定时退出。

## 10. 历史 Pages 发布（已下线）

该版本曾使用以下 Pages 条目，现已由
`com.amg456.CTWPro.rootless560 5.6.0-offline1` 替换，不再出现在当前
`pages-repo/Packages`：

```text
Package: com.xxdevice.CTWPro.Rootless560
Version: 5.6.0-2
Architecture: iphoneos-arm64
Filename: ./debs/com.xxdevice.CTWPro.Rootless560_5.6.0-2_deep_nolicense_ustar.deb
Size: 21969212
SHA256: 68e14a7f8c17d181fb48a0dc16eadd7a85ce635470d3f339ba0973f3c2e4a9cb
Depiction: ./depictions/com.xxdevice.CTWPro.Rootless560.html
```

当时的 `scripts/build_pages_repo.py` 只挂载该 `5.6.0-2` 最终版；重新生成并验证
`Packages`、`Packages.gz`、`Release`、首页、depiction 和 deb 下载路径后，旧
`5.6.0-1` 临时包不再出现在 Pages 中。当前构建器已改为挂载后续 `com.amg456`
组合版，因此本节只保留历史发布证据。
