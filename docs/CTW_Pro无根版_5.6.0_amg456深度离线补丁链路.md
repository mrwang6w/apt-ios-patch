# CTW Pro 无根版 5.6.0 com.amg456 深度离线补丁链路

## 1. 输入与目标

原始 deb：

```text
downloads/fuyonghua-repo/debs/560_CTW_Pro(无根版)_5.6.0_com.amg456.CTWPro.rootless560.deb
```

- Package: `com.amg456.CTWPro.rootless560`
- Version: `5.6.0`
- Size: `27,296,062` bytes
- SHA256: `38234f4381b36587d43fc0f78dd77e9d386b7760a5412152024379233c1891b4`

目标是闭合两层授权链，同时不修改核心改机实现：

1. 后加 `CTW.dylib` 的卡密激活、启动复核、周期心跳和失败退出链。
2. 主程序原有的捐赠码、节点复核、定时权限 UI 和锁 UI 消费者。

原始 deb 保持不变，审计和中间产物位于 `work/ctwpro-5.6.0/`。

## 2. 与旧企业版分析的关系

旧分析 `docs/CTW_Pro企业级无根版_5.6.0_patch分析链路.md` 对应
`com.xxdevice.CTWPro.Rootless560`。当前包的主程序已经移除了
`@executable_path/extend.bin` load command 和 `extend.bin` 文件，但旧授权消费者
仍然存在。

当前主程序中 13 个目标 IMP 的 64 字节指纹与旧真机验证版本完全一致，因此复用
已经验证过的 `CTWProDeepPatch.m` 运行时覆盖策略；偏移和指纹在构建时再次强校验，
不按版本号盲目套用。

仅修改 `CTW.dylib` 的早期 `_offline.deb` 构建没有覆盖主程序消费者，已被本组合版
取代。

## 3. CTW.dylib 静态补丁

目标：`var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib`，arm64。

| 文件偏移 | 旧字节 | 新字节 | 作用 |
| ---: | --- | --- | --- |
| `0x11920` | `ff4301d1fd7b04a9` | `20008052c0035fd6` | 授权 getter 固定返回真 |
| `0x1315c` | `fc6fbda9` | `c0035fd6` | 禁用首次在线授权请求 |
| `0x13cf4` | `f44fbea9` | `c0035fd6` | 禁用心跳调度器 |
| `0x143a8` | `ff0301d1` | `c0035fd6` | 禁用已排队心跳回调 |
| `0x1441c` | `f44fbea9` | `c0035fd6` | 禁用激活弹窗 |
| `0x15378` | `f44fbea9` | `c0035fd6` | 禁用授权网络错误弹窗 |
| `0x16ed0` | `f44fbea9` | `c0035fd6` | 禁用激活请求/响应路径 |
| `0x17280` | `f44fbea9` | `c0035fd6` | 禁用授权提示并退出路径 |

该层覆盖 `/vd/rauti.php?sn=...&km=...`、`/vd/rauth.php?sn=...`、对应调度器、
失败 UI 和已确认的 `exit(0)` 终点。

实现：`scripts/patch_ctwpro_amg456_license.py`。

## 4. 主程序运行时覆盖

构建脚本在主程序文件偏移 `0x1440` 插入强依赖
`@executable_path/fix.dylib`，并将 `LC_CODE_SIGNATURE` 移至 `0x1478`。

`fix.dylib` 验证当前 IMP 来自主程序且相对偏移正确后，覆盖以下消费者：

| 主程序偏移 | selector/作用 |
| ---: | --- |
| `0x4dccb0` | 禁用 `showQRCodeView:` |
| `0x4e1c8c` | 禁用 `scanQRCode:` |
| `0x4e2530` | 禁用 `qrCodeScannerDidScanResult:` |
| `0x4e6700` | 禁用响应触发的捐赠弹窗消费者 |
| `0x5025c0` | 执行 `viewDidLoad` 后恢复本地启用状态 |
| `0x50c684` | 只忽略捐赠弹窗的提交/退出 action |
| `0x515af0` | 执行 `updateUITimer` 后恢复本地启用状态 |
| `0x557560` | 禁用 `lockUI:` |
| `0x557bc0` | 禁用 `recharge:` |
| `0x56cfb0` | `isNeedCheckIP` 固定为假 |
| `0x56d67c` | `setIsNeedCheckIP:` 只允许写假 |
| `0x56dd44` | `isNeedFlushIP` 固定为假 |
| `0x56e438` | `setIsNeedFlushIP:` 只允许写假 |

模块还替换两条已知授权状态文案，并隐藏 action 指向捐赠入口的控件。

`offline1` 的 `fix.dylib` 曾在 dyld constructor 中创建后台线程，以 `5ms` 间隔
轮询动态注册的 `ViewController` 并安装方法覆盖。真机出现进程存活但黑屏时，运行时
确认主队列不响应、`viewDidLoad` 尚未被替换，且模块加载停在 `0CTW.dylib` / `CTW.dylib`
动态注册阶段。该实现存在与 Objective-C 类注册并发执行 `class_getInstanceMethod` 和
`method_setImplementation` 的启动竞争。

`offline2` 删除 constructor 后台线程和永久轮询。constructor 只向主队列投递安装任务；
UIKit 与 Objective-C 方法替换均在主线程串行执行，类尚未完成注册时以 `50ms` 延迟
重试，全部覆盖成功后停止调度。

### 4.1 随机真机参数离线化

运行时与静态元数据确认以下方法均位于 `CTW.dylib`：

| IMP 偏移 | 方法 | 作用 |
| ---: | --- | --- |
| `0x9958` | `+[LKVdConfig randomConfig]` | 原随机入口，会发起 `/vd` 请求 |
| `0xb6f8` | `-[LKDeviceConfig writeCachedConfigString:]` | 写原配置缓存 |
| `0xcc0c` | `-[LKDeviceConfig makeRandomConfig]` | 原本地随机字典生成器 |
| `0xd6f4` | `-[LKDeviceConfig defaultConfig]` | 生成兼容的本机硬件/系统基线 |

`offline3` 最初直接复用 `makeRandomConfig`。真机点击“随机生成”后提示
“没有找到机型对应的系统固件版本”。定点反汇编确认根因不是缓存写入，而是原方法先
独立调用 `randomSystemVersion`，随后再独立调用 `randomMachine`，两者没有兼容性约束，
会随机产生不存在的机型/固件组合。

`offline4` 不再调用该缺陷方法。`fix.dylib` 在验证 `+[LKVdConfig randomConfig]` 当前 IMP
确实来自 `/CTW.dylib+0x9958` 后，将其替换为本地实现：

1. 使用 `defaultConfig` 保留一致的 `machine/system_version/kern_version/darwin/mode`。
2. 使用原本地 helper 随机生成 `udid`、`random`、`serial_number`、`boardSerial`、
   `mac` 和 `unknownNumber`。
3. 补齐 `active/update_time`，验证 18 个必要字段并序列化为 JSON。
4. 先调用 `writeCachedConfigString:` 成功写入，再更新内存中的 `config/device_updated`。
5. 整条路径不再调用 `/vd`，也不会随机制造机型与固件错配。

- load command/IMP 指纹实现：`scripts/patch_ctwpro_amg456_main.py`
- 运行时模块源码：`work/ctwpro-rootless-5.6.0/patch-src/CTWProDeepPatch.m`

核心 `performeMachine*`、`nativeMachine:`、`ctwsrv`、`0CTW.dylib` 和
`ctwsup.dylib` 均未修改。

## 5. 包迁移元数据

Pages 之前发布的 `com.xxdevice.CTWPro.Rootless560` 与当前包有 138 个相同载荷
路径。若不声明迁移关系，已安装旧包的设备手动安装新包时可能因文件归属冲突失败。

构建时为新包加入：

```text
Conflicts: com.xxdevice.ctwpro.rootless560
Provides: com.xxdevice.ctwpro.rootless560
Replaces: com.xxdevice.ctwpro.rootless560
```

Pages 只发布新的 `com.amg456.CTWPro.rootless560` 条目，不并列发布两个写入相同路径
的 CTW 包。

## 6. 构建与验证

复现命令：

```bash
./scripts/build_ctwpro_amg456_deep_offline.sh
```

构建脚本执行：

1. 校验原 deb、主程序和 `CTW.dylib` 输入哈希。
2. 校验 13 个主程序 IMP 指纹并插入 `fix.dylib` 强依赖。
3. 应用并验证 8 个 `CTW.dylib` 授权补丁。
4. 验证随机入口、缓存写入和本地配置方法的 Objective-C 元数据偏移。
5. 编译、签名 `fix.dylib`，并验证离线随机所需 selector 已进入最终二进制。
6. 保留并复核主程序 38 项 entitlement。
7. 使用 deterministic USTAR、`gzip -n` 和固定 Unix ar 重包。
8. 从候选 deb 重提取并复核 control、补丁、签名、权限和 load command。
9. 对比载荷只允许 2 个文件新增、2 个文件变化、0 个文件删除。
10. 全部验证完成后原子发布到 `patched/`，避免 Pages 读取旧成品。

`offline4` 已从固定原包完成全量重建，并通过上述静态验证链。

## 7. 最终产物

```text
patched/560_CTW_Pro(无根版)_5.6.0-offline4_com.amg456.CTWPro.rootless560_deep_offline_ustar.deb
```

- Package: `com.amg456.CTWPro.rootless560`
- Version: `5.6.0-offline4`
- Size: `27,000,380` bytes
- SHA256: `00e4eab5b2f61478e8ad41056e27562410e0f90008b381588b743cc263a55ebc`

最终 Mach-O：

- `CTW Pro`: `a13272b2897b0ca3d8f3099d6cc8e6432317a27f325666f4def60318a25824be`
- `fix.dylib`: `7c9c8c52c94be30caa84a53aa802d0bd41e126ac2f33870bfa080d9c7980a45d`
- `CTW.dylib`: `8d278269c4b2ce8b7cf7dff6e5a4e88bc2a1fe0cf6501c408265a813135a9df2`

载荷差异：

- 修改：`CTW Pro`、`CTW.dylib`
- 新增：`fix.dylib`、`_CodeSignature/CodeResources`
- 删除：无

## 8. 运行边界

`offline1` 黑屏样本已完成模块加载、主队列和 IMP 归属检查。`offline3` 的真机反馈确认
随机入口覆盖能够到达本地生成链，同时暴露了原 `makeRandomConfig` 的机型/固件错配。
`offline4` 已移除该缺陷调用并完成静态构建、二次提取验证和 Pages 挂载；当前设备上的
Frida 服务只能枚举进程、无法 attach，因此无 `/vd` 请求与缓存变化仍需在安装
`offline4` 后做最后一轮真机观察。

## 9. Pages 发布

`scripts/build_pages_repo.py` 从 `patched/` 读取上述最终成品。更新 deb 后必须重新生成
并验证 Pages，不能只替换 `patched/` 文件：

```bash
python3 scripts/build_pages_repo.py
python3 scripts/verify_pages_repo.py
gzip -t pages-repo/Packages.gz
```

当前 Pages 条目：

```text
Package: com.amg456.CTWPro.rootless560
Version: 5.6.0-offline4
Filename: ./debs/com.amg456.CTWPro.rootless560_5.6.0-offline4_deep_offline_ustar.deb
Size: 27000380
SHA256: 00e4eab5b2f61478e8ad41056e27562410e0f90008b381588b743cc263a55ebc
Depiction: ./depictions/com.amg456.CTWPro.rootless560.html
```

`pages-repo/.gitattributes` 关闭该目录内 deb/gzip 的 Git LFS filter，确保 GitHub Pages
发布的是实际二进制，而不是 LFS pointer。
