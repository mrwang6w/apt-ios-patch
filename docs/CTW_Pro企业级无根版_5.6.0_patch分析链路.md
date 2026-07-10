# CTW Pro 企业级无根版 5.6.0 去卡密 Patch 分析链路

## 1. 输入与目标

原始 deb：

```text
/Users/zest/myworks/apt-ios-patch/downloads/ctwpro-repo/debs/CTW_Pro企业级(无根版)_5.6.0_com.xxdevice.CTWPro.Rootless560.deb
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

目标是移除后加卡密网络验证层，不扩大修改到 CTW Pro 原业务、daemon、
MobileSubstrate tweak 或其他静态可疑退出路径。

## 2. Payload 映射

审计识别出五个 Mach-O：

| 路径 | 架构 | 原始 SHA256 |
| --- | --- | --- |
| `var/jb/Applications/CTW Pro.app/CTW Pro` | arm64 | `8f28fe5e4e44f533902ffe4992e91a1a16da7e68aaeae84ee7632cf443ba10bc` |
| `var/jb/Applications/CTW Pro.app/extend.bin` | arm64 | `44383659b25fa629e183de924d786536690f86d4ca0f9748694bcd983a931480` |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib` | arm64 | `627914668f3328024db23c6a109c4a66e21df5a07b84eaeed38153b2924b4d9b` |
| `var/jb/Library/MobileSubstrate/DynamicLibraries/ctwsup.dylib` | arm64 + arm64e | `2ee8a33a594f46fbe4b98a49c7571bcb1a0c2445c6347be7f780536ded6a86e8` |
| `var/jb/usr/bin/ctwsrv` | armv7 + arm64 | `c6f0b9465fd2b76fff2e8783ce97209aad20ef238e230e18da3a3652e8ab9701` |

## 3. 后加授权层证据

### 3.1 装载边界

主程序使用 iOS 15.0 SDK / clang 711 构建，`extend.bin` 使用 iOS 16.4 SDK /
clang 1267 构建。主程序最后新增的 dylib load command 是：

```text
Load command 47
          cmd LC_LOAD_DYLIB
      cmdsize 56
         name @executable_path/extend.bin (offset 24)
```

`extend.bin` 没有导出符号，也没有自有 ObjC 类；主程序没有需要从它解析的
业务符号。它的作用边界是加载时 initializer、method swizzling 和 dyld
interpose，而不是正常链接库 API。

### 3.2 加载时触发链

`extend.bin` 的 `__TEXT,__init_offsets` 首项为 `0x4D88`。该 initializer：

```text
dyld load extend.bin
-> initializer 0x4D88
-> [NSBundle mainBundle].bundleIdentifier
-> 命中目标包标识分支
-> 0x4F14（RSA / 请求材料初始化）
-> dispatch_time(..., 500000000 ns)
-> dispatch_after(...)
-> block 0x20330（invoke 0x5470）
-> 0x5494（NSURLSession / method swizzling）
-> 安装后续异常与终止处理
```

关键静态证据：

- `0x4E28` 调用 `0x4F14`。
- `0x4E30..0x4E38` 构造 `500,000,000` 纳秒，即 0.5 秒。
- `0x4E68` 调用 `dispatch_after`。
- block fixup `0x20340` 指向 invoke `0x5470`，其 `0x5484` 调用 `0x5494`。
- `dataTaskWithRequest:completionHandler:` selector 引用位于 `0x24040`，代码引用
  位于 `0x5D3C/0x5D40/0x6348/0x634C`。
- `dataTaskWithURL:completionHandler:` selector 引用位于 `0x24048`，代码引用
  位于 `0x5E38/0x5E3C/0x63A4/0x63A8`。

### 3.3 终止与全局拦截能力

`extend.bin` 导入 `dispatch_after`、`sleep`、`kill`、`exit`、`_exit`、`abort`、
`method_setImplementation`、RSA Security API 和 `NSURLSession`。

它的 `__DATA,__interpose` 将四个替换入口对应到：

```text
0x4000 -> SecKeyCreateEncryptedData
0x405C -> exit
0x4120 -> _exit
0x416C -> kill
```

因此单独 NOP 一个网络失败分支或一个终止 call site 不能覆盖该层的 constructor、
swizzle、延时任务和 interpose。解除整个后加模块的装载是更窄的稳定边界。

## 4. 补丁设计

保留 Mach-O load-command 表大小不变，把必需依赖改成不存在的弱依赖，并从
app payload 删除 `extend.bin`：

| 架构 | 位置 | 旧值 | 新值 | 作用 |
| --- | --- | --- | --- | --- |
| arm64 | file `0x1440` | `0c000000` (`LC_LOAD_DYLIB`) | `18000080` (`LC_LOAD_WEAK_DYLIB`) | 缺失模块不再阻止主程序启动 |
| arm64 | file `0x1458` | `@executable_path/extend.bin` | `@executable_path/.nolicense` | 解除对实际授权模块的引用 |

两个路径均为 27 字节，整个 56 字节 command 保持等长。最终 `otool` 结果：

```text
Load command 47
          cmd LC_LOAD_WEAK_DYLIB
      cmdsize 56
         name @executable_path/.nolicense (offset 24)
```

没有修改 `0CTW.dylib`、`ctwsup.dylib`、`ctwsrv` 或原业务函数。

## 5. 重签与重包

构建脚本：

```text
scripts/patch_ctwpro_rootless_nolicense.py
scripts/build_ctwpro_rootless_nolicense.sh
```

构建过程：

1. 校验原 deb 和主程序 SHA256。
2. 重新审计并从已验证的原始 `data.tar.gz` 提取 payload。
3. 校验完整旧 load command 后写入两个等长补丁。
4. 删除 `CTW Pro.app/extend.bin`。
5. 提取并保留原主程序 38 项 entitlement，对 app 做 ad-hoc 重签。
6. 将 control 版本提升为 `5.6.0-1`，规范 control/maintainer-script 权限。
7. 使用 GNU tar `--format=ustar --sort=name --mtime=@0 --owner=0 --group=0
   --no-xattrs`、`gzip -n` 和确定性 Unix ar 容器重包。
8. 从候选 deb 重新提取并重复补丁、签名、权限、control 和归档验证，全部通过后
   原子替换 `patched/` 中的正式文件。

签名后的主程序：

```text
Size:       24,106,048 bytes
SHA256:     3317db92aefd2912d0adb95a39b6ce11614cf1a7eb516976c2784512da810e96
Signature:  ad-hoc
Entitlement keys: 38（与原始值语义一致）
```

## 6. 最终产物与验证

最终 deb：

```text
/Users/zest/myworks/apt-ios-patch/patched/CTW_Pro企业级(无根版)_5.6.0-1_com.xxdevice.CTWPro.Rootless560_nolicense_ustar.deb
Size:   21,959,938 bytes
SHA256: 3bff4426fde21b807d491d39c6b09eaa99ae5c770dbce113b65516862a9e8225
```

验证结果：

- `Package=com.xxdevice.CTWPro.Rootless560`、`Version=5.6.0-1`、
  `Architecture=iphoneos-arm64`。
- 最终 deb 是标准 2.0 三成员 ar：`debian-binary`、`control.tar.gz`、
  `data.tar.gz`。
- control/data 均为 USTAR + deterministic gzip，无 PAX/AppleDouble 扩展头。
- 从最终 deb 重提取后，补丁脚本再次验证 `0x1440/0x1458`。
- `CTW Pro.app/extend.bin` 不存在，`CodeResources` 不引用它。
- `codesign --verify --deep --strict` 通过。
- 原/最终 payload 内容差分只有主程序、删除的 `extend.bin` 和重签新增的
  `_CodeSignature`；其余业务文件相同。
- 连续两次从固定原包完整构建的最终 SHA256 完全相同。

复现命令：

```bash
./scripts/build_ctwpro_rootless_nolicense.sh
shasum -a 256 'patched/CTW_Pro企业级(无根版)_5.6.0-1_com.xxdevice.CTWPro.Rootless560_nolicense_ustar.deb'
```

## 7. Pages 发布

`pages-repo/` 已挂载最终补丁包：

```text
Package: com.xxdevice.CTWPro.Rootless560
Version: 5.6.0-1
Architecture: iphoneos-arm64
Filename: ./debs/com.xxdevice.CTWPro.Rootless560_5.6.0-1_nolicense_ustar.deb
Size: 21959938
SHA256: 3bff4426fde21b807d491d39c6b09eaa99ae5c770dbce113b65516862a9e8225
Depiction: ./depictions/com.xxdevice.CTWPro.Rootless560.html
```

`scripts/build_pages_repo.py` 的统一清单现包含 5 个最终补丁包。重新生成的
`Packages`、`Packages.gz`、`Release`、首页和 depiction 已通过
`scripts/verify_pages_repo.py`，Pages 内 CTW deb 与 `patched/` 原件哈希一致。
`pages-repo/.gitattributes` 将 `.deb`/`.gz` 强制为普通 Git blob，扫描未发现
LFS pointer。连续两次 Pages 生成哈希一致；临时本地 HTTP 验证覆盖 `/`、
`Packages`、`Packages.gz`、depiction 和 CTW deb 下载路径。

## 8. 运行验证边界

本轮完成的是当前 deb 字节、静态触发链、装载边界、签名、归档和确定性构建
验证。工作区没有用于安装和运行该 rootless 包的 iOS 15+ 越狱执行环境，因此
尚未执行真机启动、卡密弹窗观察和核心功能回归。

真机验收应从清理旧安装/授权缓存后的状态启动，确认不再出现卡密输入流程，并
覆盖主界面、核心改机操作、前后台切换及至少原验证窗口加余量。若仍出现独立的
授权症状，应从最早未闭合的运行时触发重新取证，而不是扩大修改到其他 timer 或
退出调用。
