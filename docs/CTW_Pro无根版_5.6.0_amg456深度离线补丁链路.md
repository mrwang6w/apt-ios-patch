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

目标是闭合两层授权链，并让随机新机配置脱离失效的 `/vd` 服务，同时不修改核心
改机实现：

1. 后加 `CTW.dylib` 的卡密激活、启动复核、周期心跳和失败退出链。
2. 主程序原有的捐赠码、节点复核、定时权限 UI 和锁 UI 消费者。
3. `MachinePreferences -randomPreferences:` 发起的随机新机网络流程。

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
| `0x84488` | 以本地随机配置替换 `MachinePreferences -randomPreferences:` |

模块还替换两条已知授权状态文案，并隐藏 action 指向捐赠入口的控件。

`offline1` 的 `fix.dylib` 曾在 dyld constructor 中创建后台线程，以 `5ms` 间隔
轮询动态注册的 `ViewController` 并安装方法覆盖。真机出现进程存活但黑屏时，运行时
确认主队列不响应、`viewDidLoad` 尚未被替换，且模块加载停在 `0CTW.dylib` / `CTW.dylib`
动态注册阶段。该实现存在与 Objective-C 类注册并发执行 `class_getInstanceMethod` 和
`method_setImplementation` 的启动竞争。

`offline2` 删除 constructor 后台线程和永久轮询。constructor 只向主队列投递安装任务；
UIKit 与 Objective-C 方法替换均在主线程串行执行，类尚未完成注册时以 `50ms` 延迟
重试，14 项覆盖全部成功后停止调度。

### 4.1 随机按钮真实入口

NIBArchive 解析确认主界面“一键新机”按钮绑定 `ViewController -performeMachine:`；
随后出现的 `MachinePreferences` 选择页有两个独立 action：

```text
nativePreferences:
randomPreferences:
```

主程序 `MachinePreferences +initialize` 在 `+0xd544c` 调用
`class_replaceMethod`，把 `randomPreferences:` 注册到 `+0x84488`，类型为
`v24@0:8@16`。历史真机流量中 `/vd` 正是在 `MachinePreferences -viewDidLoad`
之后选择随机项时发出；同一时段没有进入 `ViewController -performeMachineStub`。
因此 `/vd` 不能归因于通用网络点或 stub。

`offline3` 曾直接调用包内 `makeRandomConfig`，但该方法分别随机系统版本与机型，会
产生不兼容组合并提示“没有找到机型对应的系统固件版本”。`offline4` 改为兼容基线，
但错误覆盖 `+[LKVdConfig randomConfig]`，没有截断 `MachinePreferences` 自身的异步
网络流程，仍会进入“超时或非法请求”分支。`offline4` 已通过 Git revert 撤回，不再
发布。

`offline5` 只覆盖已确认的 `randomPreferences:` action：

1. 从 `LKDeviceConfig -defaultConfig` 复制兼容的机型、固件、内核和模式基线。
2. 只随机化 `random`、`udid`、`serial_number`、`boardSerial`、`mac` 和
   `unknownNumber`，并刷新 `active/update_time`。
3. 通过原 `writeCachedConfigString:` 写缓存，并更新 `config/device_updated`。
4. 返回主控制器后，验证原 `performeMachineStub` 仍为主程序 `+0x53de04`，再调用它
   应用配置。

真机安装 `offline5` 后，点击“随机生成”进入补丁的主动拒绝提示“本地配置或应用入口
校验失败，未执行改机”，证明原 `/vd` 链已被截断，但该版本把控制器、apply IMP 和
配置生成错误合并成一个提示，无法继续定位。

`offline6` 在同一窄覆盖面上增加：

1. 优先从选择页所属 navigation stack、parent/presenting 链和当前 window 查找主控制器，
   最后才遍历 application windows。
2. 配置基线按 `LKDeviceConfig.config`、解析 `readCachedConfigString`、`defaultConfig`
   顺序回退；基线必须包含机型、固件、内核、模式等 9 个兼容字段。
3. 失败提示显示 `controller`、`apply-contract`、`config-instance`、`baseline`、
   `random-helper`、`final-config`、`serialize` 或 `cache-write` 精确阶段码，且任何失败
   都不调用原 stub。

真机安装 `offline6` 后精确返回 `config-instance`。静态元数据进一步确认
`+[LKDeviceConfig sharedInstance]` 是标准 `dispatch_once` 单例，因此正常情况下不会
返回空；该结果说明类所在的 `CTW.dylib` 没有出现在 App 的 Objective-C runtime。

`offline7` 在查询类之前增加显式加载回退：先查询当前 runtime，缺失时依次从
`/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib` 和 rootful 兼容路径
`dlopen(..., RTLD_NOW | RTLD_GLOBAL)`。加载的是同包内已经完成 8 点静态补丁并重签的
`CTW.dylib`。失败阶段进一步拆为 `config-dlopen`、`config-class`、
`config-shared-selector` 和 `config-shared-instance`。

补丁不调用原 `randomPreferences:`，因此不会创建 `/vd` 请求；通用
`NSURLSession` 创建点 `+0x990f58` 和 completion `+0x992740` 均保持不变，避免破坏
`/upload3`、`/upload`、`/getlocation` 等其它业务。

- load command/IMP 指纹实现：`scripts/patch_ctwpro_amg456_main.py`
- 运行时模块源码：`patches/ctwpro/CTWProDeepPatch.m`

核心 `performeMachineStub`、`performeMachine:`、`nativeMachine:`、`ctwsrv`、
`0CTW.dylib` 和 `ctwsup.dylib` 均未修改；`offline7` 只在运行时调用经过偏移校验的
原 stub。

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
2. 校验原授权消费者，以及 `randomPreferences:` selector、`+initialize` 注册指令、
   `+0x84488` action 和 `+0x53de04` apply IMP 指纹，并插入 `fix.dylib` 强依赖。
3. 应用并验证 8 个 `CTW.dylib` 补丁。
4. 编译、签名 `fix.dylib`，保留并复核主程序 38 项 entitlement。
5. 使用 deterministic USTAR、`gzip -n` 和固定 Unix ar 重包。
6. 从候选 deb 重提取并复核 control、补丁、签名、权限和 load command。
7. 对比载荷只允许 2 个文件新增、2 个文件变化、0 个文件删除。
8. 全部验证完成后原子发布到 `patched/`，避免 Pages 读取旧成品。

`offline7` 已从固定原包连续完成两次全量重建；deb、`fix.dylib`、主程序和
`CTW.dylib` 的 SHA256 均逐项一致。

## 7. 最终产物

```text
patched/560_CTW_Pro(无根版)_5.6.0-offline7_com.amg456.CTWPro.rootless560_deep_offline_ustar.deb
```

- Package: `com.amg456.CTWPro.rootless560`
- Version: `5.6.0-offline7`
- Size: `27,004,438` bytes
- SHA256: `9a946b631375a8d90f2aad1480f32a827ff711f084a3b3f5658f7f818330f95a`

最终 Mach-O：

- `CTW Pro`: `d08c8fa74cd3cb1759e1758e28c1e2cd529939f39f2d16840c1e9edb8c0d055b`
- `fix.dylib`: `9e8e9f1fcd9c67ef1f75965fd8c4c0056fbf4201e40f97d4a19f6e3ebb77b3fd`
- `CTW.dylib`: `8d278269c4b2ce8b7cf7dff6e5a4e88bc2a1fe0cf6501c408265a813135a9df2`

载荷差异：

- 修改：`CTW Pro`、`CTW.dylib`
- 新增：`fix.dylib`、`_CodeSignature/CodeResources`
- 删除：无

## 8. 运行边界

历史真机证据已确认原始点击链会发出 `http://api.ctwvip.xyz/vd?data=...`，并在服务
返回 502 后显示“超时或非法请求”。`offline5` 真机已进入本地补丁拒绝分支且未执行
改机；`offline7` 的 NIB action、运行时注册点、原 apply 入口、本地 helper、显式
`CTW.dylib` 加载回退、三层配置
基线、缓存写入 selector 和载荷均已完成静态闭环。

当前设备可以通过 USB 枚举并正常桌面启动 App，但 Frida `17.15.3` 和与历史服务端
匹配的 `17.11.0` 客户端附加均返回 `unexpected early end-of-stream`；SSH/端口转发也
没有可用 root shell。因此尚未取得 `offline7` 点击后“零 `/vd`、缓存身份字段变化、
原 stub 执行且不闪退”的最终真机证据。静态构建通过不替代这项回归；安装后若仍被
拒绝，应记录提示中的精确阶段码。

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
Version: 5.6.0-offline7
Filename: ./debs/com.amg456.CTWPro.rootless560_5.6.0-offline7_deep_offline_ustar.deb
Size: 27004438
SHA256: 9a946b631375a8d90f2aad1480f32a827ff711f084a3b3f5658f7f818330f95a
Depiction: ./depictions/com.amg456.CTWPro.rootless560.html
```

`pages-repo/.gitattributes` 关闭该目录内 deb/gzip 的 Git LFS filter，确保 GitHub Pages
发布的是实际二进制，而不是 LFS pointer。
