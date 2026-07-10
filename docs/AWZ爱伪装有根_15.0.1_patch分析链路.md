# AWZ 爱伪装有根 15.0.1 去卡密 Patch 分析链路

## 1. 结果

- 原包：`downloads/amg456-repo/debs/AWZ爱伪装_修复(有根)_15.0.1_app.awz4854.rootful.deb`
- 原包 SHA256：`ef6fdc13cddb733b48688b76e7ac0dff2e4ccc8db70e429856d23cf11b6bad0b`
- 原包大小：`14,958,520` bytes
- Package：`app.awz4854.rootful`
- 原 Version：`15.0.1`
- 最终 Version：`15.0.1-1`
- 最终包：`patched/AWZ爱伪装_修复(有根)_15.0.1-1_app.awz4854.rootful_nolicense_ustar.deb`
- 最终包 SHA256：`3564d982efc5a79e82a818a4a487372fb9133df7c2c31cbd59366d937b379fd7`
- 最终包大小：`13,030,492` bytes

构建入口：

```bash
./scripts/build_awz_nolicense.sh
```

补丁实现：`scripts/patch_awz_nolicense.py`。

## 2. 运行入口与后加卡密层

`Info.plist` 指定 `CFBundleExecutable=AWZ`。包中同时保留 `AWZ` 和 `AWZZ`，均为 `armv7 + arm64` FAT Mach-O。

两者的业务代码完全一致：

| Arch | `AWZ` / `AWZZ` `__text` SHA256 |
|---|---|
| armv7 | `552dfe1d67b4f041004d28a015d8fe37c7aadd4422f6957557ae45f557a14f09` |
| arm64 | `cb31e144ce78e346c11e39495beac0951895239753d02899f9b6f7d7ad3fa1c6` |

`otool -l` 的差异证明 `AWZ` 是从 `AWZZ` 后处理得到的：

1. `__RESTRICT` 被改名为 `__XESTRICT`。
2. 增加 `LC_LOAD_DYLIB /Applications/AWZ.app/mapsdk.bundle`。
3. 扩大 `__LINKEDIT` 并重新签名。

`mapsdk.bundle` 的 install-name 为 `/Library/MobileSubstrate/DynamicLibraries/OOXXPlay.dylib`，签名标识为 `AWZPatch.dylib`，明文包含：

```text
http://ad.xsoftauth.com/Api/GetAuthInfo.ashx
http://ad1.xsoftauth.com/Api/GetAuthInfo.ashx
http://api.abogeek.com/Api/CardRechange.ashx
http://api1.abogeek.com/Api/CardRechange.ashx
CardRechangeSPS.ashx
GetVipAddr.ashx
```

因此 `mapsdk.bundle` 是明确的后加卡密网络层，不是 AWZ 原始业务代码。

安装脚本原本还会执行 `/usr/bin/aloader`。该程序具有网络、`dlopen/dlsym`、`posix_spawn` 和文件删除能力；`pz.dat` 又包含 `mapsdk.bundle -> OOXXPlay.dylib/AWZPatch.dylib` 映射。最终包保留 helper 文件以减少无关 payload 改动，但从 `extrainst_` 删除了 `aloader` 调用，防止安装或升级时重新注入卡密层。

## 3. 真正的授权 predicate

IDA/Hex-Rays 对 `AWZZ.arm64` 和 `AWZZ.armv7` 的分析确认，软件许可协议和付费授权不是同一状态：

- `licenseAllowed` 只控制首次启动的《软件许可使用协议》。本补丁不修改该合规提示。
- 付费授权由混淆 selector `RnUDGAmwVZvhlPKDTsEsrWzUNUCHwSJCnfNaWxus` 统一判断。

arm64 关键伪代码：

```c
bool auth_valid(manager) {
    if (!manager->authInfo)
        return false;
    if ([manager->authInfo status] != 1 || global_auth_state() != 1)
        return false;
    if ([[NSDate date] compare:[manager->authInfo expiry_date]] != NSOrderedAscending) {
        [manager->authInfo setStatus:3];
        [manager persist];
        return false;
    }
    return true;
}
```

对 selector 字符串的 xref 证明该 predicate 被大量业务入口共享调用，包括：

- `IFMagicMainVC newAppEnvClick:`：一键新机环境。
- `IFMagicMainVC originMachineClick:`：恢复原始机器。
- `cleanPastboardClick:`、`cleanKeychainClick:`、`cleanSafariClick:`。
- 备份导出、地图定位、设置页和批量操作。

例如 `originMachineClick:` 在 `0x1000CD2D8` 通过 `objc_msgSend` 调用 predicate，随后在 `0x1000CD2E0` 调用全局授权态 getter；两者均返回 `1` 才进入原始机器确认流程。`0x1000CD2C4` 是该调用序列前的 `ADRP`，不是调用点。补丁修改共享状态源，不修改这些业务 action，也不吞掉它们的 alert/completion。

UI 状态刷新函数 `-[IFMagicMainVC OezlUsKQbWyjilfezgAbCvtzAuylPnyvUcDSGGKk]` 同样读取全局授权态，原始分支会显示 `已注销`、`已锁定` 或 `未激活`。固定全局态和模型 `status` 后，该 UI 进入有效状态分支。

## 4. Patch 点

arm64 使用：

```asm
mov w0, #1
ret
```

字节：`20 00 80 52 c0 03 5f d6`。

armv7 Thumb 使用：

```asm
movs r0, #1
bx lr
```

字节：`01 20 70 47`。

| Arch | 目标 | VA | slice file offset | old bytes | new bytes |
|---|---|---:|---:|---|---|
| armv7 | shared authorization predicate | `0x40926` | `0x3C926` | `f0 b5 03 af` | `01 20 70 47` |
| armv7 | global authorization-state getter | `0xAA970` | `0xA6970` | `4f f6 34 20` | `01 20 70 47` |
| armv7 | authorization model `status` getter | `0x10DD58` | `0x109D58` | `4c f6 08 01` | `01 20 70 47` |
| arm64 | shared authorization predicate | `0x100040F2C` | `0x40F2C` | `f8 5f bc a9 f6 57 01 a9` | `20 00 80 52 c0 03 5f d6` |
| arm64 | global authorization-state getter | `0x1000B0FE8` | `0xB0FE8` | `88 1b 00 b0 00 89 40 b9` | `20 00 80 52 c0 03 5f d6` |
| arm64 | authorization model `status` getter | `0x100121314` | `0x121314` | `08 17 00 f0 08 29 8a b9` | `20 00 80 52 c0 03 5f d6` |

构建以包内原始备份 `AWZZ` 为基线，因此不携带 `mapsdk.bundle` 的新增 load command。补丁同时把四处 `__RESTRICT` 恢复为 `__XESTRICT`，保留 MobileSubstrate 注入能力和包内 `aaaa.dylib` 修复层。

## 5. 重签与重包

构建脚本执行以下步骤：

1. 校验原 deb SHA256，并在每次构建时重新提取审计树；随后校验 `AWZZ` SHA256，拒绝复用可能被修改的缓存 payload。
2. 校验六个旧字节并写入双架构 patch。
3. 删除 app 内 `mapsdk.bundle`。
4. 删除 `extrainst_` 中 `/usr/bin/aloader` 调用。
5. 使用 `codesign -d --arch armv7/arm64 --xml --entitlements -` 分别提取原 `AWZ` 两个架构的 entitlements；语义比较完全一致且均为 12 项后，只向签名命令传入一个标准 XML plist。
6. 对 `AWZ.app` 做 ad-hoc 重签并更新 `_CodeSignature/CodeResources`。
7. 将 control 版本调整为 `15.0.1-1`，规范权限：
   - `control` / `icon.png`：`0644`
   - `extrainst_` / `prerm`：`0755`
8. 使用 GNU tar `--format=ustar --sort=name --mtime=@0 --owner=0 --group=0 --no-xattrs` 和 `gzip -n` 重包。
9. 先在 `work/` 生成候选 deb，从候选 `ar` 容器重新提取并完成归档、control、patch bytes 与 deep codesign 验证；全部通过后才原子替换 `patched/` 的正式文件。

签名后的主程序：

```text
SHA256: 6b139e441772896c56a4b1776db7cd10e28cb486aed6ce8ce42bb62497fa0bbc
Size:   8,372,496 bytes
Arch:   armv7 + arm64
Identifier: AWZ
Signature: ad-hoc
```

## 6. 最终验证

从最终 deb 重新解包后的检查结果：

- `Package=app.awz4854.rootful`
- `Version=15.0.1-1`
- `Architecture=iphoneos-arm`
- FAT 架构仍为 `armv7 + arm64`
- 六个 patch 点反汇编均为固定返回 `1`
- `otool -L AWZ` 不再包含 `mapsdk.bundle` 或 `OOXXPlay`
- `AWZ.app/mapsdk.bundle` 不存在
- `_CodeSignature/CodeResources` 不再引用 `mapsdk.bundle`
- `codesign --verify --deep --strict AWZ.app` 通过
- control tar 5 个成员，data tar 524 个成员；归档验证器未发现 PAX/AppleDouble 扩展头
- 最终 payload 407 个普通文件
- 连续两次完整构建 SHA256 都为 `3564d982...379fd7`

验证目录：

```text
work/awz-rootful-15.0.1/verify-final-15.0.1-1/
work/awz-rootful-15.0.1/final-audit-15.0.1-1/
```

## 7. Pages 发布同步

`pages-repo/` 只复制最终补丁包，不发布原始 deb 或 `work/` 分析目录：

```text
Package: app.awz4854.rootful
Version: 15.0.1-1
Architecture: iphoneos-arm
Conflicts: app.awzios6.awz
Filename: ./debs/app.awz4854.rootful_15.0.1-1_nolicense_ustar.deb
Size: 13030492
SHA256: 3564d982efc5a79e82a818a4a487372fb9133df7c2c31cbd59366d937b379fd7
```

生成器从实际挂载 control 动态生成 `Release/Architectures: iphoneos-arm64 iphoneos-arm`，并透传 `Conflicts` 等 APT 求解字段。`scripts/verify_pages_repo.py` 在部署前复核 Package 唯一性、control/Packages 一致性、三种摘要、Release 摘要与架构、depiction/index 链接、USTAR/PAX 兼容性以及 LFS pointer。

## 8. 真机边界

本轮检测到连接设备 `iPhone9,2 / iOS 15.8.8`，但 Frida 应用列表中没有已安装的 `AWZ`，USB SSH 端口也没有可用认证。因此已完成静态调用链、字节、签名、归档和确定性构建验证，尚未执行安装后的 UI/功能回归。

最终包只命名为 `nolicense`，没有宣称 `noheartbeat/noexit`。原 app、daemon 和其他修复 dylib 内仍有反调试、timer 与退出逻辑；这些不属于本次已证明的卡密失败链，未做过宽修改。
