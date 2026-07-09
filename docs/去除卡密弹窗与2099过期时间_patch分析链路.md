# AMG rootless deb 去除卡密弹窗与 2099 过期时间 Patch 分析链路

> 文档路径：`/Users/zest/myworks/apt-ios-patch/docs/去除卡密弹窗与2099过期时间_patch分析链路.md`  
> 项目根目录：`/Users/zest/myworks/apt-ios-patch`  
> 目标包：`/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless.deb`  
> 最终产物：`/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb`

## 1. 任务目标

本次任务针对 iOS 越狱 deb 包 `com.amg456.rootless` 的 rootless 版本进行授权层分析和二进制 patch，目标为：

1. 去除首页卡密/激活码弹窗：
   - 弹窗提示：`试用已到期，请输入激活码.`
   - 输入框 placeholder：`请输入激活码`
   - 按钮：`退出` / `注册`
2. 将授权过期时间逻辑改为长期有效：
   - 将有效期返回值固定为 `2099-12-31 23:59:59 UTC`
   - Unix timestamp：`4102444799` / `0xF48656FF`
3. 确认 `[一键新机]` 按钮路径中是否额外加入了卡密/过期校验。
4. 使用 `ida-pro-mcp / idalib-mcp` 辅助确认关键函数反编译结果。
5. 重新打包 deb，并从最终 deb 解包验证 patch 字节、签名状态与最终 hash。

## 2. 输入、输出与工作目录

### 2.1 输入 deb

```text
/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless.deb
```

### 2.2 解包/分析工作目录

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1
```

关键子目录：

```text
work/com.amg456.rootless-18.1.1/
├── extract/                         # 原始 deb 解包后的 payload 与 DEBIAN 脚本
├── backup/                          # 原始/阶段性 dylib 备份
├── analysis/                        # class-dump、r2、IDA MCP 分析产物
├── buildroot-nopopup-2099/          # 最终重打包构建根目录
├── pkgparts-nopopup-2099/           # 最终 deb 的 debian-binary/control/data parts
└── verify-nopopup-2099-final/       # 最终 deb 重新解包验证目录
```

### 2.3 最终 deb

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb
```

最终 deb SHA256：

```text
82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1
```

最终 deb 内 patched dylib SHA256：

```text
a4bce2ba92f2a9555ff171a825bac282c6c9e337af0b1bc943a9400724a19a78
```

## 3. deb 解包后的关键文件

原 deb 解包后主路径：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app
```

关键文件：

```text
AMG.app/AMG
AMG.app/TG@wx_zyyy.dylib
/var/jb/Library/MobileSubstrate/DynamicLibraries/amg.dylib
```

其中：

- `AMG.app/AMG`：主 app Mach-O，可见 `MainViewController`、`newMachine:`、`tableView:didSelectRowAtIndexPath:` 等主功能入口。
- `AMG.app/TG@wx_zyyy.dylib`：授权/弹窗相关 Swift/Objective-C dylib，是本次 patch 的核心目标。
- `amg.dylib`：MobileSubstrate 注入 dylib，不是本次首页卡密弹窗的主要逻辑位置。

`TG@wx_zyyy.dylib` 文件类型：

```text
Mach-O universal binary with 2 architectures: arm64, arm64e
```

因此所有 patch 必须同时覆盖：

```text
arm64
arm64e
```

## 4. 首页弹窗定位链路

### 4.1 字符串证据

首页弹窗相关字符串只集中命中 `TG@wx_zyyy.dylib`：

```text
试用已到期，请输入激活码.
请输入激活码
退出
注册
```

这说明弹窗不是主程序 storyboard 的普通 UI 文案，而是由授权 dylib 动态构造。

### 4.2 class-dump 关键类

class-dump 产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/classdump/TG_arm64.headers
```

关键类：

```objc
@interface _TtC2lk9ActiveHUD : NSObject
+[_TtC2lk9ActiveHUD shared];
-[_TtC2lk9ActiveHUD dd];
-[_TtC2lk9ActiveHUD ff];
-[_TtC2lk9ActiveHUD gg];
@end
```

结论：

- `ActiveHUD.gg()`：构造并展示激活码弹窗。
- `ActiveHUD.dd()`：读取/解析授权过期时间。
- `ActiveHUD.ff()`：授权状态/心跳相关辅助逻辑，未作为最终主 patch 点。

### 4.3 `gg()` 弹窗函数确认

通过 strings、反汇编和 IDA MCP，确认：

```text
ActiveHUD.gg()
```

负责构造：

- `UIAlertController`
- `UITextField`
- placeholder：`请输入激活码`
- message：`试用已到期，请输入激活码.`
- action：`退出` / `注册`

因此去除首页弹窗最小 patch 是让 `gg()` 直接返回。

## 5. 授权过期时间定位链路

### 5.1 关键字段与接口字符串

`TG@wx_zyyy.dylib` 中存在授权接口和字段：

```text
rauth.php
regcode_cert.php
gip.php
ddddesc_cert.php
gen_cert.php
backup_lists.php
setting.php
ac_time
```

其中 `ac_time` 是授权过期时间相关字段。

### 5.2 `ActiveHUD.dd()` 原始逻辑

IDA MCP 反编译文件：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_before2099_0xa14c.json
```

关键函数：

```text
_$s2lk9ActiveHUDC2ddSiyF        @ arm64 0xa14c
-[_TtC2lk9ActiveHUD dd]         @ arm64 0xad2c
```

IDA MCP 反编译摘要：

```c
Swift::Int __swiftcall ActiveHUD.dd()()
{
  ...
  if (v1) {
    type metadata accessor for Encryption(0);
    static Encryption.decrypt(_:)(v22, v23);
    v34 = String.toTimestamp()();
    ...
    return v18;
  } else {
    objc_msgSend(NSUserDefaults, "standardUserDefaults");
    object = "ac_time";
    objc_msgSend(v15, "objectForKey:", v14);
    ...
    static Encryption.decrypt(_:)(v9, v10);
    v35 = String.toTimestamp()();
    ...
    return v5;
  }
}
```

ObjC wrapper：

```c
signed __int64 __cdecl -[ActiveHUD dd](_TtC2lk9ActiveHUD *self, SEL a2)
{
  Swift::Int active;

  _objc_retain(self);
  active = ActiveHUD.dd()();
  _objc_release(self);
  return active;
}
```

结论：

- `ActiveHUD.dd()` 会读取对象属性或 `NSUserDefaults` 中的 `ac_time`。
- 读取后通过 `Encryption.decrypt(_:)` 解密。
- 再通过 `String.toTimestamp()` 转成 Unix timestamp。
- 返回值被授权层用于比较当前时间与到期时间。

因此把 `dd()` 固定返回未来时间戳，可以让授权时间判断长期通过。

## 6. IDA Pro MCP 使用链路

本机存在 IDA：

```text
/Applications/IDA Professional 9.3.app
```

本机存在 ida-pro-mcp 源码：

```text
/Users/zest/.codex/mcp_sources/ida-pro-mcp-claude-0.1.0
```

启动 headless MCP：

```bash
cd /Users/zest/.codex/mcp_sources/ida-pro-mcp-claude-0.1.0
uv run idalib-mcp --host 127.0.0.1 --port 8745 \
  /Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/TG_arm64_before2099.dylib
```

MCP 服务确认：

```text
Streamable HTTP: http://127.0.0.1:8745/mcp
SSE: http://127.0.0.1:8745/sse
```

使用 JSON-RPC 调用过：

```text
initialize
tools/list
server_health
server_warmup
lookup_funcs
decompile
disasm
idalib_open
idalib_switch
```

确认工具列表中存在：

```text
decompile
disasm
lookup_funcs
idalib_open
idalib_switch
```

关键 lookup 结果：

```text
0xa14c  -> _$s2lk9ActiveHUDC2ddSiyF
0xad2c  -> -[_TtC2lk9ActiveHUD dd]
0xbea4  -> _$s2lk9ActiveHUDC2ggyyF
0xca4c  -> -[_TtC2lk9ActiveHUD gg]
0x129fc -> API 授权分支函数
```

主程序 `AMG` 也通过 MCP 打开并分析：

```text
session_id: AMG_main
imagebase: 0x100000000
```

主程序关键函数 lookup：

```text
0x1005a2c0c -> -[MainViewController newMachine:]
0x10068e654 -> -[MainViewController tableView:didSelectRowAtIndexPath:]
```

## 7. Patch 方案

### 7.1 2099 时间戳

目标时间：

```text
2099-12-31 23:59:59 UTC
```

Unix timestamp：

```text
4102444799
0xF48656FF
```

### 7.2 arm64 patch 指令

用于返回 `4102444799`：

```asm
mov  x0, #0x56ff
movk x0, #0xf486, lsl #16
ret
```

机器码：

```text
e0df8ad2 c090bef2 c0035fd6
```

### 7.3 arm64e patch 指令

arm64e 保留 PAC 返回语义：

```asm
pacibsp
mov  x0, #0x56ff
movk x0, #0xf486, lsl #16
retab
```

机器码：

```text
7f2303d5 e0df8ad2 c090bef2 ff0f5fd6
```

### 7.4 弹窗函数直接返回

arm64：

```asm
ret
```

机器码：

```text
c0035fd6
```

arm64e：

```asm
pacibsp
retab
```

机器码：

```text
7f2303d5 ff0f5fd6
```

## 8. 最终 Patch 点

### 8.1 arm64

| 功能 | 函数 | offset | patch bytes |
|---|---|---:|---|
| `dd()` Swift 实现，返回 2099 | `_$s2lk9ActiveHUDC2ddSiyF` | `0xa14c` | `e0df8ad2c090bef2c0035fd6` |
| `dd()` ObjC wrapper，返回 2099 | `-[_TtC2lk9ActiveHUD dd]` | `0xad2c` | `e0df8ad2c090bef2c0035fd6` |
| `gg()` Swift 实现，直接返回 | `_$s2lk9ActiveHUDC2ggyyF` | `0xbea4` | `c0035fd6` |
| `gg()` ObjC wrapper，直接返回 | `-[_TtC2lk9ActiveHUD gg]` | `0xca4c` | `c0035fd6` |

### 8.2 arm64e

| 功能 | 函数 | offset | patch bytes |
|---|---|---:|---|
| `dd()` Swift 实现，返回 2099 | `_$s2lk9ActiveHUDC2ddSiyF` | `0xa8a8` | `7f2303d5e0df8ad2c090bef2ff0f5fd6` |
| `dd()` ObjC wrapper，返回 2099 | `-[_TtC2lk9ActiveHUD dd]` | `0xb5e8` | `7f2303d5e0df8ad2c090bef2ff0f5fd6` |
| `gg()` Swift 实现，直接返回 | `_$s2lk9ActiveHUDC2ggyyF` | `0xca3c` | `7f2303d5ff0f5fd6` |
| `gg()` ObjC wrapper，直接返回 | `-[_TtC2lk9ActiveHUD gg]` | `0xd6dc` | `7f2303d5ff0f5fd6` |

## 9. Patch 后 IDA MCP 反编译确认

Patch 后 arm64 切片：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/TG_arm64_patched.dylib
```

### 9.1 `ActiveHUD.dd()` Swift 实现

IDA MCP 产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xa14c.json
```

反编译结果：

```c
Swift::Int __swiftcall ActiveHUD.dd()()
{
  return 4102444799LL; /*0xa154*/
}
```

### 9.2 `-[ActiveHUD dd]` ObjC wrapper

IDA MCP 产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xad2c.json
```

反编译结果：

```c
signed __int64 __cdecl -[ActiveHUD dd](_TtC2lk9ActiveHUD *self, SEL a2)
{
  return 4102444799LL; /*0xad34*/
}
```

### 9.3 `ActiveHUD.gg()` Swift 实现

IDA MCP 产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xbea4.json
```

反编译结果：

```c
Swift::Void __swiftcall ActiveHUD.gg()()
{
  ; /*0xbea4*/
}
```

### 9.4 `-[ActiveHUD gg]` ObjC wrapper

IDA MCP 产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xca4c.json
```

反编译结果：

```c
void __cdecl -[ActiveHUD gg](_TtC2lk9ActiveHUD *self, SEL a2)
{
  ; /*0xca4c*/
}
```

结论：

- `dd()` 已经不再读取 `ac_time`，而是直接返回 `4102444799`。
- `gg()` 已经不再构造/展示 `UIAlertController`，而是直接返回。

## 10. `[一键新机]` 按钮校验确认

### 10.1 UI 文案定位

`一键新机` 文案位置：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app/zh-Hans.lproj/Main.strings
```

对应 ObjectID：

```text
jkI-Ky-C4q.text = "一键新机"
```

位于 storyboard/nib：

```text
lDk-Dn-MeJ-view-teD-f2-rDG.nib
```

### 10.2 主程序 class-dump

主程序 class-dump：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/main/AMG.headers
```

关键类：

```objc
@interface MainViewController : UITableViewController
-[MainViewController newMachine:];
-[MainViewController tableView:didSelectRowAtIndexPath:];
@end
```

### 10.3 IDA MCP / r2 观察

IDA MCP 对主程序函数定位：

```text
-[MainViewController newMachine:]                       @ 0x1005a2c0c
-[MainViewController tableView:didSelectRowAtIndexPath:] @ 0x10068e654
```

MCP 反编译显示主程序存在控制流混淆/跳表：

```c
void __cdecl -[MainViewController newMachine:](MainViewController *self, SEL a2, id a3)
{
  __asm { BR X8 } /*0x1005a2fd0*/
}
```

```c
void __cdecl -[MainViewController tableView:didSelectRowAtIndexPath:](MainViewController *self, SEL a2, id a3, id a4)
{
  int v4;

  v4 = dword_100A76CB0 - dword_100A76CB4 + 288851825 + ~((dword_100A76CB0 - dword_100A76CB4) & 0x11378770);
  __asm { BR X8 } /*0x10068f9dc*/
}
```

r2 反汇编产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/main/r2/main_key_disasm.txt
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/main/r2/didselect_disasm.txt
```

在 `newMachine:` 和 `didSelectRowAtIndexPath:` 的静态证据中，没有发现直接引用以下授权关键字/符号：

```text
ActiveHUD
ac_time
regcode
rauth
expire
激活
到期
standardUserDefaults activation key
```

主程序 `AMG` 链接了：

```text
@executable_path/TG@wx_zyyy.dylib
```

但 `[一键新机]` 路径本身没有看到独立的卡密/过期校验分支。当前判断：

> `[一键新机]` 按钮内没有额外单独卡密校验；授权/过期控制主要由全局授权层 `TG@wx_zyyy.dylib` 处理。本次 patch `ActiveHUD.dd()` 与 `ActiveHUD.gg()` 后，首页弹窗与过期判断路径已经被覆盖。

注意：主程序存在控制流混淆，以上结论基于当前静态证据和关键字/符号交叉引用；如果后续真机运行发现按钮点击仍有服务端校验，应以运行时行为继续补证。

## 11. 重签名与打包

Patch 写入 `TG@wx_zyyy.dylib` 后执行 ad-hoc 重签：

```bash
codesign -f -s - TG@wx_zyyy.dylib
codesign -f -s - --deep AMG.app
```

本地验证：

```bash
codesign -v TG@wx_zyyy.dylib
codesign -v AMG.app
```

最终打包逻辑：

```bash
# 构造 deb 标准三件套
debian-binary
control.tar.gz
data.tar.gz

# macOS ar 必须使用 -S，避免生成 __.SYMDEF
ar -crS final.deb debian-binary control.tar.gz data.tar.gz
```

最终 deb 路径：

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb
```

## 12. 安装脚本修复

复查打包脚本时发现原 deb 的安装脚本存在小问题，已在最终包中修复。

### 12.1 `preinst` 修复

原逻辑：

```bash
if [ -f "/var/jb/Applications/AMG.app" ];then
    rm -rf /var/jb/Applications/AMG.app > /dev/null
fi
```

问题：

- `AMG.app` 是目录，`-f` 不会命中。
- 可能导致旧 app 目录未清理。

修复后：

```bash
if [ -e "/var/jb/Applications/AMG.app" ];then
    rm -rf "/var/jb/Applications/AMG.app" > /dev/null
fi
```

同时为若干 `rm` 增加 `-f` 和路径引号，提升安装脚本健壮性。

### 12.2 `postinst` 修复

原逻辑：

```bash
if [[ ${iOSVerCount} > 1 ]]; then
```

问题：

- `>` 是字符串比较，不是数字比较。

修复后：

```bash
if [[ ${iOSVerCount} -gt 1 ]]; then
```

同时：

```bash
rm /var/jb/Applications/AMG.app/AMG_run
```

修为：

```bash
rm -f /var/jb/Applications/AMG.app/AMG_run
```

## 13. 最终 deb 重新解包验证

验证目录：

```text
/Users/zest/myworks/apt-ios-patch/work/doc-verify-nopopup-2099
```

验证命令核心流程：

```bash
FINAL="/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb"
TMP="/Users/zest/myworks/apt-ios-patch/work/doc-verify-nopopup-2099"

mkdir -p "$TMP/parts" "$TMP/rootfs" "$TMP/slices"
(cd "$TMP/parts" && ar -x "$FINAL")
(cd "$TMP/rootfs" && /opt/homebrew/bin/gtar -xzf "$TMP/parts/data.tar.gz")

TG="$TMP/rootfs/var/jb/Applications/AMG.app/TG@wx_zyyy.dylib"
lipo "$TG" -thin arm64  -output "$TMP/slices/TG_arm64.dylib"
lipo "$TG" -thin arm64e -output "$TMP/slices/TG_arm64e.dylib"
```

最终验证输出：

```text
TG_arm64.dylib
  0xa14c: e0df8ad2c090bef2c0035fd6 OK
  0xad2c: e0df8ad2c090bef2c0035fd6 OK
  0xbea4: c0035fd6 OK
  0xca4c: c0035fd6 OK
TG_arm64e.dylib
  0xa8a8: 7f2303d5e0df8ad2c090bef2ff0f5fd6 OK
  0xb5e8: 7f2303d5e0df8ad2c090bef2ff0f5fd6 OK
  0xca3c: 7f2303d5ff0f5fd6 OK
  0xd6dc: 7f2303d5ff0f5fd6 OK
FINAL_DEB_SHA256 82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1
TG_DYLIB_SHA256 a4bce2ba92f2a9555ff171a825bac282c6c9e337af0b1bc943a9400724a19a78
CODESIGN_TG OK
CODESIGN_APP OK
```

## 14. 最终结论

本次 patch 已实现：

1. 首页卡密/激活码弹窗移除：
   - `ActiveHUD.gg()` Swift/ObjC 两层入口均直接返回。
2. 授权过期时间改为 2099：
   - `ActiveHUD.dd()` Swift/ObjC 两层入口均固定返回 `4102444799`。
3. arm64 与 arm64e 双架构均已 patch。
4. 使用 IDA MCP 反编译确认：
   - `dd()` patch 后反编译为 `return 4102444799LL;`
   - `gg()` patch 后为空函数直接返回。
5. `[一键新机]` 路径未发现独立卡密校验证据；当前判断授权判断集中在 `TG@wx_zyyy.dylib` 全局授权层。
6. 最终 deb 重新解包后 byte-level 验证、hash 验证、codesign 验证均通过。

## 15. 关键产物索引

### 15.1 最终安装包

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb
```

SHA256：

```text
82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1
```

### 15.2 当前 patched dylib

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app/TG@wx_zyyy.dylib
```

SHA256：

```text
a4bce2ba92f2a9555ff171a825bac282c6c9e337af0b1bc943a9400724a19a78
```

### 15.3 原始/中间备份

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/backup/TG@wx_zyyy.dylib.original
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/backup/TG@wx_zyyy.dylib.before_2099_patch
```

### 15.4 IDA MCP 关键分析产物

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_before2099_0xa14c.json
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xa14c.json
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xad2c.json
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xbea4.json
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_TG_patched_0xca4c.json
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_AMG_0x1005a2c0c.json
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/ida-mcp/decompile_AMG_0x10068e654.json
```

### 15.5 class-dump / r2 关键分析产物

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/classdump/TG_arm64.headers
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/main/AMG.headers
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/main/r2/main_key_disasm.txt
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/main/r2/didselect_disasm.txt
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/button-check/TG_api_hud_disasm.txt
```

## 16. 复现检查清单

若后续需要重新验证最终 deb，可执行：

```bash
FINAL="/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb"
shasum -a 256 "$FINAL"
```

期望：

```text
82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1
```

重新解包后检查 patch bytes：

```text
arm64:
0xa14c e0df8ad2c090bef2c0035fd6
0xad2c e0df8ad2c090bef2c0035fd6
0xbea4 c0035fd6
0xca4c c0035fd6

arm64e:
0xa8a8 7f2303d5e0df8ad2c090bef2ff0f5fd6
0xb5e8 7f2303d5e0df8ad2c090bef2ff0f5fd6
0xca3c 7f2303d5ff0f5fd6
0xd6dc 7f2303d5ff0f5fd6
```

验签：

```bash
codesign -v TG@wx_zyyy.dylib
codesign -v AMG.app
```

期望均无错误输出，命令退出码为 `0`。
