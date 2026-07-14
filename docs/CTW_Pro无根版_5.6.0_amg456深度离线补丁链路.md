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
2. 校验 13 个 IMP 指纹并插入 `fix.dylib` 强依赖。
3. 应用并验证 8 个 `CTW.dylib` 补丁。
4. 编译、签名 `fix.dylib`，保留并复核主程序 38 项 entitlement。
5. 使用 deterministic USTAR、`gzip -n` 和固定 Unix ar 重包。
6. 从候选 deb 重提取并复核 control、补丁、签名、权限和 load command。
7. 对比载荷只允许 2 个文件新增、2 个文件变化、0 个文件删除。
8. 全部验证完成后原子发布到 `patched/`，避免 Pages 读取旧成品。

连续两次从固定输入完整构建得到相同 SHA256。

## 7. 最终产物

```text
patched/560_CTW_Pro(无根版)_5.6.0-offline1_com.amg456.CTWPro.rootless560_deep_offline_ustar.deb
```

- Package: `com.amg456.CTWPro.rootless560`
- Version: `5.6.0-offline1`
- Size: `26,996,946` bytes
- SHA256: `35bfcbbd4f4e67631728cb0afecd57df8ab70edb00ec0a7cea42132a102bd871`

最终 Mach-O：

- `CTW Pro`: `d00c59a53e3d149c2cdbfb16befe62693afe260e4cdc4e31218e9716b2013951`
- `fix.dylib`: `ce8f19dfbc070f78f0ebb13e3f977cbf70416544e0dd6427cedf7603ddd4ab35`
- `CTW.dylib`: `8d278269c4b2ce8b7cf7dff6e5a4e88bc2a1fe0cf6501c408265a813135a9df2`

载荷差异：

- 修改：`CTW Pro`、`CTW.dylib`
- 新增：`fix.dylib`、`_CodeSignature/CodeResources`
- 删除：无

## 8. 运行边界

旧 `fix.dylib` 策略已在相同主程序 IMP 字节上完成真机验证，但当前
`com.amg456` 组合包尚未在 iOS 真机上安装并持续观察。

本补丁移除已确认的在线卡密和捐赠授权链，但不替换独立的随机新机请求：

```text
http://api.ctwvip.xyz/vd?data=...
```

deb 内存在加密响应样本，但消费端验签/解密链尚未还原，因此不声明随机真机参数
功能已经离线可用。

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
Version: 5.6.0-offline1
Filename: ./debs/com.amg456.CTWPro.rootless560_5.6.0-offline1_deep_offline_ustar.deb
Size: 26996946
SHA256: 35bfcbbd4f4e67631728cb0afecd57df8ab70edb00ec0a7cea42132a102bd871
Depiction: ./depictions/com.amg456.CTWPro.rootless560.html
```

`pages-repo/.gitattributes` 关闭该目录内 deb/gzip 的 Git LFS filter，确保 GitHub Pages
发布的是实际二进制，而不是 LFS pointer。
