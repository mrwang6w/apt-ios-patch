# AMG rootless deb 去除卡密弹窗与 2099 过期时间 Patch 分析链路

> 文档路径：`/Users/zest/myworks/apt-ios-patch/docs/去除卡密弹窗与2099过期时间_patch分析链路.md`  
> 项目根目录：`/Users/zest/myworks/apt-ios-patch`  
> 目标包：`/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless.deb`  
> 最新最终产物：`/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat_noexit.deb`

## 1. 任务目标

本次任务针对 iOS 越狱 deb 包 `com.amg456.rootless` 的 rootless 版本进行授权层分析和二进制 patch，目标为：

1. 去除首页卡密/激活码弹窗：
   - 弹窗提示：`试用已到期，请输入激活码.`
   - 输入框 placeholder：`请输入激活码`
   - 按钮：`退出` / `注册`
2. 将授权过期时间逻辑改为长期有效：
   - 将有效期返回值固定为 `2099-12-31 23:59:59 UTC`
   - Unix timestamp：`4102444799` / `0xF48656FF`
3. 针对后续真机反馈“隔段时间定时检测心跳后闪退”，继续定位并禁用周期心跳入口。
4. 确认 `[一键新机]` 按钮路径中是否额外加入了卡密/过期校验。
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
├── buildroot-nopopup-2099/          # 第一阶段重打包构建根目录（去弹窗 + 2099）
├── pkgparts-nopopup-2099/           # 第一阶段 deb 的 debian-binary/control/data parts
├── verify-nopopup-2099-final/       # 第一阶段 deb 重新解包验证目录
├── buildroot-nopopup-2099-noheartbeat/   # 第二阶段构建根目录（禁用心跳 timer）
├── pkgparts-nopopup-2099-noheartbeat/    # 第二阶段 debian-binary/control/data parts
├── verify-nopopup-2099-noheartbeat-final/ # 第二阶段重新解包验证目录
├── buildroot-nopopup-2099-noheartbeat-noexit/   # 最新最终包构建根目录（移除延迟退出）
├── pkgparts-nopopup-2099-noheartbeat-noexit/    # 最新最终包 debian-binary/control/data parts
└── verify-nopopup-2099-noheartbeat-noexit-final/ # 最新最终包重新解包验证目录
```

### 2.3 阶段性与最新最终 deb

第一阶段产物（去弹窗 + 2099，有心跳）：

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb
SHA256: 82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1
TG@wx_zyyy.dylib SHA256: a4bce2ba92f2a9555ff171a825bac282c6c9e337af0b1bc943a9400724a19a78
```

第二阶段产物（去弹窗 + 2099 + 禁用心跳 timer）：

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat.deb
SHA256: b39511e5a2ca7e0d506d999bf09f101e209e8fb5054df4d89b4dd4629bf8f697
TG@wx_zyyy.dylib SHA256: 39cca71d7825ff4b3c48392ce2ead907caafc90159ff39800ab1d2d7439c0460
```

最新最终产物（去弹窗 + 2099 + 禁用心跳 timer + 移除延迟退出）：

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat_noexit.deb
SHA256: 0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866
TG@wx_zyyy.dylib SHA256: fb3a9f2861db58a5cc884980f9962f1c33b22a4a69360a5fd22e67771dbe2e54
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

第一阶段打包逻辑（后续 noheartbeat 包沿用同一 deb 三件套格式）：

```bash
# 构造 deb 标准三件套
debian-binary
control.tar.gz
data.tar.gz

# macOS ar 必须使用 -S，避免生成 __.SYMDEF
ar -crS final.deb debian-binary control.tar.gz data.tar.gz
```

第一阶段 deb 路径（去弹窗 + 2099，尚未禁用心跳）：

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

## 13. 第一阶段 deb 重新解包验证

验证目录：

```text
/Users/zest/myworks/apt-ios-patch/work/doc-verify-nopopup-2099
```

> 注：本节记录第一阶段 `nopopup_2099` 包的验证结果。第二阶段 `noheartbeat` 复验见第 19 节；最新最终 `noheartbeat_noexit` 复验见第 20 节。

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

第一阶段验证输出：

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

## 14. 第一阶段结论

第一阶段 patch 已实现：

1. 首页卡密/激活码弹窗移除：
   - `ActiveHUD.gg()` Swift/ObjC 两层入口均直接返回。
2. 授权过期时间改为 2099：
   - `ActiveHUD.dd()` Swift/ObjC 两层入口均固定返回 `4102444799`。
3. arm64 与 arm64e 双架构均已 patch。
4. 使用 IDA MCP 反编译确认：
   - `dd()` patch 后反编译为 `return 4102444799LL;`
   - `gg()` patch 后为空函数直接返回。
5. `[一键新机]` 路径未发现独立卡密校验证据；当前判断授权判断集中在 `TG@wx_zyyy.dylib` 全局授权层。
6. 第一阶段 deb 重新解包后 byte-level 验证、hash 验证、codesign 验证均通过。

第一阶段尚未禁用周期心跳；后续真机反馈的延迟闪退问题在第 17～22 节继续处理。

## 15. 关键产物索引

### 15.1 第一阶段安装包

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099.deb
```

SHA256：

```text
82f39a133c9c156509a7cab0f88bca7a9a1d2d1c83da90f2cf4e76216e8e32b1
```

### 15.2 第一阶段 patched dylib

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

## 16. 第一阶段复现检查清单

若后续需要重新验证第一阶段 deb，可执行：

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


---

## 17. 后续问题：周期心跳检测导致闪退

### 17.1 现象

第一阶段 `nopopup_2099` 包安装后，首页激活弹窗已经移除，过期时间也已经固定为 2099。但真机运行反馈：

```text
隔段时间定时检测心跳，会导致过一段时间后闪退
```

这说明除 `dd()`/`gg()` 外，`TG@wx_zyyy.dylib` 里仍存在周期性授权/心跳逻辑。由于 `dd()` 只覆盖本地过期时间读取，定时心跳仍可能触发网络校验、状态刷新、异常退出或服务端返回后的防护分支。

### 17.2 心跳符号定位

在当前 patched dylib 上按架构枚举符号：

```bash
TG="/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app/TG@wx_zyyy.dylib"
nm -arch arm64  -m "$TG" | rg -i 'heartbeat|Timer|startAuto|ActiveHUDC2ff|ActiveHUDC2gg|ActiveHUDC2dd'
nm -arch arm64e -m "$TG" | rg -i 'heartbeat|Timer|startAuto|ActiveHUDC2ff|ActiveHUDC2gg|ActiveHUDC2dd'
```

核心命中：

```text
arm64:
0xb7e4  _$s2lk9ActiveHUDC18startAutoHeartbeat33_...yyF
0xbdb8  _$s2lk9ActiveHUDC18startAutoHeartbeat33_...yyFySo7NSTimerCYbcfU_
0xbe64  _$s2lk9ActiveHUDC16heartbeat_action33_...yyF

arm64e:
0xc2d4  _$s2lk9ActiveHUDC18startAutoHeartbeat33_...yyF
0xc930  _$s2lk9ActiveHUDC18startAutoHeartbeat33_...yyFySo7NSTimerCYbcfU_
0xc9e8  _$s2lk9ActiveHUDC16heartbeat_action33_...yyF
```

相关辅助符号：

```text
arm64:
0x9ffc  heartbeatTimer getter
0xa068  heartbeatTimer setter
0xa0fc  heartbeatTimer modify
0xad84  ActiveHUD.ff()
0xb798  ActiveHUD.ff() ObjC wrapper

arm64e:
0xa734  heartbeatTimer getter
0xa7a4  heartbeatTimer setter
0xa83c  heartbeatTimer modify
0xb644  ActiveHUD.ff()
0xc284  ActiveHUD.ff() ObjC wrapper
```

反汇编证据显示：

- `startAutoHeartbeat` 会计算时间差，并在条件满足时创建 `NSTimer`。
- 定时器由 `scheduledTimerWithTimeInterval:repeats:block:` 创建，随后通过 `addTimer:forMode:` 加入 runloop。
- timer block 会触发心跳逻辑。
- `heartbeat_action` 是周期心跳动作函数。

因此最小稳定 patch 点选择三层同时覆盖：

1. `startAutoHeartbeat`：阻止创建新 timer。
2. timer block：即使已存在/被外部调用，也不执行动作。
3. `heartbeat_action`：兜底禁用周期动作本体。

## 18. 心跳补丁方案

### 18.1 备份

patch 前备份：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/backup/TG@wx_zyyy.dylib.before_heartbeat_patch
```

心跳分析与验证产物目录：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/heartbeat-patch
```

### 18.2 arm64 patch 点

| 功能 | 函数 | offset | patch bytes |
|---|---|---:|---|
| 禁止启动自动心跳 timer | `_$s2lk9ActiveHUDC18startAutoHeartbeat...yyF` | `0xb7e4` | `c0035fd6` |
| 禁止 timer block 执行 | `_$s2lk9ActiveHUDC18startAutoHeartbeat...yyFySo7NSTimerCYbcfU_` | `0xbdb8` | `c0035fd6` |
| 禁止心跳动作本体 | `_$s2lk9ActiveHUDC16heartbeat_action...yyF` | `0xbe64` | `c0035fd6` |

`c0035fd6` 对应：

```asm
ret
```

### 18.3 arm64e patch 点

| 功能 | 函数 | offset | patch bytes |
|---|---|---:|---|
| 禁止启动自动心跳 timer | `_$s2lk9ActiveHUDC18startAutoHeartbeat...yyF` | `0xc2d4` | `7f2303d5ff0f5fd6` |
| 禁止 timer block 执行 | `_$s2lk9ActiveHUDC18startAutoHeartbeat...yyFySo7NSTimerCYbcfU_` | `0xc930` | `7f2303d5ff0f5fd6` |
| 禁止心跳动作本体 | `_$s2lk9ActiveHUDC16heartbeat_action...yyF` | `0xc9e8` | `7f2303d5ff0f5fd6` |

`7f2303d5ff0f5fd6` 对应：

```asm
pacibsp
retab
```

### 18.4 重签名

心跳 patch 后重新合并 fat Mach-O，并对 dylib 与 app 做 ad-hoc 重签：

```bash
codesign -f -s - "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app/TG@wx_zyyy.dylib"
codesign -f -s - --deep "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app"
```

验证结果：

```text
codesign dylib OK
codesign app OK
```

心跳 patch 后当前工作区 dylib SHA256：

```text
39cca71d7825ff4b3c48392ce2ead907caafc90159ff39800ab1d2d7439c0460
```

### 18.5 去除心跳处理链路方案（可复现）

本节把“去除心跳导致的延迟闪退”的实际处理链路整理成可复现方案，便于后续遇到同类定时检测/后台心跳问题时复用。

#### 18.5.1 判断问题边界

已完成第一阶段 patch 后，`ActiveHUD.dd()` 固定返回 2099，`ActiveHUD.gg()` 直接返回，但仍出现“隔段时间闪退”。这类现象优先怀疑：

1. 启动后延迟创建的 `NSTimer` / `DispatchSourceTimer` / RunLoop timer。
2. 周期性授权心跳接口返回异常后触发退出。
3. 心跳结果写回本地授权状态，覆盖第一阶段本地时间 patch 的效果。
4. timer block 内部调用其它授权动作函数，导致间接闪退。

本次目标限定为 `TG@wx_zyyy.dylib` 内已经可证实的 `ActiveHUD` 心跳链路，不扩大到主程序其它后台线程或完整性检测。

#### 18.5.2 定位入口

从当前工作区 dylib 枚举心跳/定时器相关符号：

```bash
TG="/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app/TG@wx_zyyy.dylib"

nm -arch arm64  -m "$TG" | rg -i 'heartbeat|Timer|startAuto|ActiveHUDC2ff|ActiveHUDC2gg|ActiveHUDC2dd'
nm -arch arm64e -m "$TG" | rg -i 'heartbeat|Timer|startAuto|ActiveHUDC2ff|ActiveHUDC2gg|ActiveHUDC2dd'
```

关键判断：

- `startAutoHeartbeat` 是 timer 创建入口。
- `startAutoHeartbeat(...NSTimer...)` 是 `NSTimer` block 回调。
- `heartbeat_action` 是周期动作本体。
- `heartbeatTimer getter/setter/modify` 只是 timer 属性访问，不作为主 patch 点。
- `ActiveHUD.ff()` 上游会调用 `startAutoHeartbeat`，但直接 patch `ff()` 风险更高，可能误伤其它初始化逻辑；因此不作为首选 patch 点。

#### 18.5.3 验证调用关系

用 `llvm-objdump` 对关键符号附近反汇编，确认调用链：

```bash
OUT="/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/heartbeat-patch"
mkdir -p "$OUT"

llvm-objdump -d --macho --arch=arm64 "$TG" \
  | rg -A6 -B2 '(_\$s2lk9ActiveHUDC18startAutoHeartbeat|_\$s2lk9ActiveHUDC16heartbeat_action)' \
  > "$OUT/disasm_arm64_heartbeat_patch.txt"

llvm-objdump -d --macho --arch=arm64e "$TG" \
  | rg -A6 -B2 '(_\$s2lk9ActiveHUDC18startAutoHeartbeat|_\$s2lk9ActiveHUDC16heartbeat_action)' \
  > "$OUT/disasm_arm64e_heartbeat_patch.txt"
```

已保存的证据文件：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/heartbeat-patch/disasm_arm64_heartbeat_patch.txt
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/heartbeat-patch/disasm_arm64e_heartbeat_patch.txt
```

关键证据摘要：

```text
arm64:
0xb7e4  startAutoHeartbeat: ret
0xbdb8  timer block:        ret
0xbe64  heartbeat_action:   ret

arm64e:
0xc2d4  startAutoHeartbeat: pacibsp; retab
0xc930  timer block:        pacibsp; retab
0xc9e8  heartbeat_action:   pacibsp; retab
```

#### 18.5.4 Patch 原则

本次不只 patch `heartbeat_action`，而是三层同时处理：

| 层级 | 目的 | 原因 |
|---|---|---|
| `startAutoHeartbeat` | 阻止新建周期 timer | 从源头避免后续重复触发 |
| timer block | 阻止已注册/间接调用的 block 执行 | 防止已有 block 或 trampoline 继续触发 |
| `heartbeat_action` | 兜底禁止心跳动作本体 | 即使其它路径直接调用也不执行 |

arm64 使用裸 `ret`：

```text
c0035fd6
```

arm64e 保留 PAC 返回语义：

```text
7f2303d5ff0f5fd6
```

即：

```asm
pacibsp
retab
```

#### 18.5.5 实施步骤

1. 备份 patch 前 dylib：

```bash
cp -p "$TG" \
  "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/backup/TG@wx_zyyy.dylib.before_heartbeat_patch"
```

2. 用 `lipo` 拆出双架构切片：

```bash
OUT="/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/heartbeat-patch"
lipo "$TG" -thin arm64  -output "$OUT/TG_arm64.before_hb.dylib"
lipo "$TG" -thin arm64e -output "$OUT/TG_arm64e.before_hb.dylib"
```

3. 按 offset 写入 patch bytes：

```text
arm64:
0xb7e4 c0035fd6
0xbdb8 c0035fd6
0xbe64 c0035fd6

arm64e:
0xc2d4 7f2303d5ff0f5fd6
0xc930 7f2303d5ff0f5fd6
0xc9e8 7f2303d5ff0f5fd6
```

4. 合并 fat dylib 并写回 app：

```bash
lipo -create \
  "$OUT/TG_arm64.after_hb.dylib" \
  "$OUT/TG_arm64e.after_hb.dylib" \
  -output "$OUT/TG_heartbeat_patched.fat.dylib"

cp -f "$OUT/TG_heartbeat_patched.fat.dylib" "$TG"
```

5. 重签名：

```bash
codesign -f -s - "$TG"
codesign -f -s - --deep "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app"
```

#### 18.5.6 验证步骤

验证必须同时覆盖旧 patch 和新心跳 patch。

1. 验证 patch bytes：

```bash
python3 - <<'PY'
from pathlib import Path
import subprocess, sys
fat = Path('/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app/TG@wx_zyyy.dylib')
out = Path('/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/heartbeat-patch')
checks = {
  'arm64': {
    0xa14c:'e0df8ad2c090bef2c0035fd6',
    0xad2c:'e0df8ad2c090bef2c0035fd6',
    0xbea4:'c0035fd6',
    0xca4c:'c0035fd6',
    0xb7e4:'c0035fd6',
    0xbdb8:'c0035fd6',
    0xbe64:'c0035fd6',
  },
  'arm64e': {
    0xa8a8:'7f2303d5e0df8ad2c090bef2ff0f5fd6',
    0xb5e8:'7f2303d5e0df8ad2c090bef2ff0f5fd6',
    0xca3c:'7f2303d5ff0f5fd6',
    0xd6dc:'7f2303d5ff0f5fd6',
    0xc2d4:'7f2303d5ff0f5fd6',
    0xc930:'7f2303d5ff0f5fd6',
    0xc9e8:'7f2303d5ff0f5fd6',
  }
}
ok_all = True
for arch in ('arm64', 'arm64e'):
    thin = out / f'verify-{arch}.dylib'
    subprocess.run(['lipo', str(fat), '-thin', arch, '-output', str(thin)], check=True)
    data = thin.read_bytes()
    print(f'## {arch}')
    for off, exp in checks[arch].items():
        got = data[off:off + len(bytes.fromhex(exp))].hex()
        ok = got == exp
        ok_all &= ok
        print(f'{off:#x} expected={exp} got={got} {"OK" if ok else "FAIL"}')
if not ok_all:
    sys.exit(1)
PY
```

2. 验签：

```bash
codesign -v "$TG"
codesign -v "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app"
```

3. 从最终 deb 重新解包复验：

```bash
FINAL="/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat.deb"
VERIFY="/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/verify-nopopup-2099-noheartbeat-final"

rm -rf "$VERIFY"
mkdir -p "$VERIFY/parts" "$VERIFY/rootfs" "$VERIFY/control" "$VERIFY/slices"
(cd "$VERIFY/parts" && ar -x "$FINAL")
gtar -xzf "$VERIFY/parts/control.tar.gz" -C "$VERIFY/control"
gtar -xzf "$VERIFY/parts/data.tar.gz" -C "$VERIFY/rootfs"
```

最终验证产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/verify-nopopup-2099-noheartbeat-final/verify_patch_bytes_from_final_deb.txt
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/verify-nopopup-2099-noheartbeat-final/final_hashes.txt
```

#### 18.5.7 成功判定

本次方案的成功判定不是只看“能打包”，而是同时满足：

1. `dd()` 仍固定返回 2099。
2. `gg()` 仍为空返回，不再展示首页激活弹窗。
3. `startAutoHeartbeat` 直接返回，不再创建新心跳 timer。
4. timer block 直接返回，不再触发 `heartbeat_action`。
5. `heartbeat_action` 直接返回，作为兜底。
6. arm64 / arm64e 双架构 patch bytes 都从最终 deb 解包后复验通过。
7. `TG@wx_zyyy.dylib` 与 `AMG.app` codesign 验证通过。
8. 最终 deb hash 与 Pages 源挂载 hash 一致。

#### 18.5.8 回滚与后续排查边界

如需回滚心跳 patch，可从备份恢复：

```bash
cp -f \
  "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/backup/TG@wx_zyyy.dylib.before_heartbeat_patch" \
  "$TG"
codesign -f -s - "$TG"
codesign -f -s - --deep "/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/extract/rootfs/var/jb/Applications/AMG.app"
```

如果真机仍然出现延迟闪退，下一步不应继续盲目扩大 patch，而应按运行时证据继续定位：

- 是否还有其它 `NSTimer` / `dispatch_after` / `DispatchSourceTimer`。
- 是否有完整性校验、签名校验或反调试延迟触发。
- 是否主程序 `AMG` 内存在与按钮操作绑定的后台校验。
- 是否网络请求失败/返回异常后触发退出分支。
- 是否安装脚本或旧偏好文件残留导致状态不一致。

当前 noheartbeat 包只声明已覆盖 `TG@wx_zyyy.dylib` 中有静态符号证据的 `ActiveHUD` 心跳链路。

## 19. 第二阶段 noheartbeat deb 打包与复验

### 19.1 第二阶段 noheartbeat deb

路径：

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat.deb
```

SHA256：

```text
b39511e5a2ca7e0d506d999bf09f101e209e8fb5054df4d89b4dd4629bf8f697
```

大小：

```text
6206424 bytes
```

内部 `TG@wx_zyyy.dylib` SHA256：

```text
39cca71d7825ff4b3c48392ce2ead907caafc90159ff39800ab1d2d7439c0460
```

构建目录：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/buildroot-nopopup-2099-noheartbeat
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/pkgparts-nopopup-2099-noheartbeat
```

从第二阶段 deb 重新解包验证目录：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/verify-nopopup-2099-noheartbeat-final
```

### 19.2 从第二阶段 deb 复验 patch bytes

第二阶段 deb 解包后的验证文件：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/verify-nopopup-2099-noheartbeat-final/verify_patch_bytes_from_final_deb.txt
```

验证结果：

```text
arm64:
0xa14c e0df8ad2c090bef2c0035fd6 OK
0xad2c e0df8ad2c090bef2c0035fd6 OK
0xbea4 c0035fd6 OK
0xca4c c0035fd6 OK
0xb7e4 c0035fd6 OK
0xbdb8 c0035fd6 OK
0xbe64 c0035fd6 OK

arm64e:
0xa8a8 7f2303d5e0df8ad2c090bef2ff0f5fd6 OK
0xb5e8 7f2303d5e0df8ad2c090bef2ff0f5fd6 OK
0xca3c 7f2303d5ff0f5fd6 OK
0xd6dc 7f2303d5ff0f5fd6 OK
0xc2d4 7f2303d5ff0f5fd6 OK
0xc930 7f2303d5ff0f5fd6 OK
0xc9e8 7f2303d5ff0f5fd6 OK
```

验签与 hash：

```text
CODESIGN_TG OK
CODESIGN_APP OK
FINAL_DEB_SHA256 b39511e5a2ca7e0d506d999bf09f101e209e8fb5054df4d89b4dd4629bf8f697
TG_DYLIB_SHA256 39cca71d7825ff4b3c48392ce2ead907caafc90159ff39800ab1d2d7439c0460
```

### 19.3 安装脚本复验

第二阶段包仍保留第一阶段的安装脚本修复，并额外把 `postinst` 中的 `AMG_run` 清理路径加上引号。

关键复验结果：

```text
preinst:
if [ -e "/var/jb/Applications/AMG.app" ];then
    rm -rf "/var/jb/Applications/AMG.app" > /dev/null
fi

postinst:
if [[ ${iOSVerCount} -gt 1 ]]; then
    ...
else
    rm -f "/var/jb/Applications/AMG.app/AMG_run"
fi
```


## 20. 第二轮修复：延迟退出 noexit 补丁

### 20.1 现象与重新定位

第二阶段 `nopopup_2099_noheartbeat` 已经禁用了 `startAutoHeartbeat`、timer block、`heartbeat_action`，但真机仍反馈：

```text
隔一两分钟自动闪退
```

这说明“心跳闪退”的实际表现不只来自 `NSTimer` 心跳动作，也可能来自 `ActiveHUD.ff()` 中通过 `DispatchQueue.asyncAfter` 安排的延迟退出 closure。

重新枚举 `TG@wx_zyyy.dylib` 后发现：

```text
ActiveHUD.ff() 存在多个 Swift closure：
0xb47c  _$s2lk9ActiveHUDC2ffyyFyycfU_
0xb6ac  _$s2lk9ActiveHUDC2ffyyFyycfU0_
0xb6e0  _$s2lk9ActiveHUDC2ffyyFyyScMYccfU1_
0xb748  _$s2lk9ActiveHUDC2ffyyFyyScMYccfU2_
```

其中 `_$s2lk9ActiveHUDC2ffyyFyycfU_` 内存在明确的退出调用：

```text
arm64:
0xb59c  mov w0, #0x0
0xb5a0  bl _exit

arm64e:
0xc05c  mov w0, #0x0
0xc060  bl _exit
```

另外，`TG@wx_zyyy.dylib` 内还有 3 处 `_exit(0)` 路径，分别位于 `gg` / `gg(String?)` / `zz(String?)` 相关 closure。虽然首页 `gg()` 已经直接返回，但为避免异步/间接路径继续触发退出，本轮统一移除 TG 内所有显式 `_exit` call。

### 20.2 noexit patch 原则

本轮没有直接砍掉整个 `ActiveHUD.ff()`，原因是 `ff()` 还包含初始化、异步调度、状态处理等逻辑。更稳的做法是：

- 保留原函数和 closure 的控制流。
- 只把 `bl _exit` 替换成 `nop`。
- 让命中退出条件后继续执行函数 epilogue 正常返回。

`nop` 机器码：

```text
1f2003d5
```

### 20.3 noexit patch 点

#### arm64

| 功能 | 位置/函数 | offset | 原始 bytes | patch bytes |
|---|---|---:|---|---|
| `ActiveHUD.ff()` 延迟退出 closure | `_$s2lk9ActiveHUDC2ffyyFyycfU_` | `0xb5a0` | `aa510094` | `1f2003d5` |
| `gg()` 退出按钮 closure | `_$s2lk9ActiveHUDC2gg...UIAlertAction...` | `0xc9d0` | `9e4c0094` | `1f2003d5` |
| `gg(String?)` 退出路径 | `_$s2lk9ActiveHUDC2ggyySSSgF...` | `0xeb60` | `3a440094` | `1f2003d5` |
| `zz(String?)` 延迟退出 closure | `_$s2lk9ActiveHUDC2zzyySSSgF...` | `0xf128` | `c8420094` | `1f2003d5` |

#### arm64e

| 功能 | 位置/函数 | offset | 原始 bytes | patch bytes |
|---|---|---:|---|---|
| `ActiveHUD.ff()` 延迟退出 closure | `_$s2lk9ActiveHUDC2ffyyFyycfU_` | `0xc060` | `60590094` | `1f2003d5` |
| `gg()` 退出按钮 closure | `_$s2lk9ActiveHUDC2gg...UIAlertAction...` | `0xd65c` | `e1530094` | `1f2003d5` |
| `gg(String?)` 退出路径 | `_$s2lk9ActiveHUDC2ggyySSSgF...` | `0xfc08` | `764a0094` | `1f2003d5` |
| `zz(String?)` 延迟退出 closure | `_$s2lk9ActiveHUDC2zzyySSSgF...` | `0x102d4` | `c3480094` | `1f2003d5` |

### 20.4 noexit patch 验证

工作区验证产物：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/second-heartbeat/noexit_patch_report.txt
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/analysis/second-heartbeat/verify_all_patch_bytes_after_noexit.txt
```

关键验证结果：

```text
arm64:
0xb5a0 1f2003d5 OK
0xc9d0 1f2003d5 OK
0xeb60 1f2003d5 OK
0xf128 1f2003d5 OK

arm64e:
0xc060 1f2003d5 OK
0xd65c 1f2003d5 OK
0xfc08 1f2003d5 OK
0x102d4 1f2003d5 OK
```

反汇编验证：

```text
No _exit call remains in TG disasm
```

noexit 后工作区 dylib SHA256：

```text
fb3a9f2861db58a5cc884980f9962f1c33b22a4a69360a5fd22e67771dbe2e54
```

### 20.5 noexit 最终 deb

路径：

```text
/Users/zest/myworks/apt-ios-patch/patched/纯净版18.1.1_AMG奔驰正版[无根]_18.1.1_com.amg456.rootless_nopopup_2099_noheartbeat_noexit.deb
```

大小：

```text
6206412 bytes
```

SHA256：

```text
0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866
```

最终 deb 重新解包验证目录：

```text
/Users/zest/myworks/apt-ios-patch/work/com.amg456.rootless-18.1.1/verify-nopopup-2099-noheartbeat-noexit-final
```

复验结果：

```text
所有 2099 / 去弹窗 / noheartbeat / noexit patch bytes 均 OK
No _exit call remains in final deb TG disasm
codesign extracted dylib OK
codesign extracted app OK
```

## 21. GitHub Pages 静态源同步

因为当前推荐的前端源只挂载 `patched/` 中的最新补丁 deb，心跳补丁完成后同步更新了静态源构建脚本与产物。

目录约束：所有展示前端与 APT 静态源文件只维护在 `pages-repo/` 目录内，仓库根目录不再复制 `index.html`、`Packages`、`debs/` 等重复产物，避免出现两份 HTML/元数据需要维护。

部署链路：仓库保留单一自定义 workflow：

```text
/Users/zest/myworks/apt-ios-patch/.github/workflows/deploy-pages-repo.yml
```

该 workflow 使用 `actions/upload-pages-artifact` 将 `pages-repo/` 作为 Pages artifact 根目录发布。因此源码目录是 `pages-repo/`，但公开 URL 不带 `/pages-repo/` 路径段，最终访问路径是：

```text
https://myzest.github.io/apt-ios-patch/
https://myzest.github.io/apt-ios-patch/Packages
https://myzest.github.io/apt-ios-patch/Packages.gz
https://myzest.github.io/apt-ios-patch/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
```

> 如果 GitHub Actions 仍同时出现 GitHub 自动的 `pages build and deployment`，说明仓库 Settings → Pages 还配置在 `Deploy from a branch`。需要切到 `GitHub Actions`，否则 GitHub 会继续用分支根目录触发第二条部署线。

同步更新的关键产物：

```text
/Users/zest/myworks/apt-ios-patch/scripts/build_pages_repo.py
/Users/zest/myworks/apt-ios-patch/.github/workflows/deploy-pages-repo.yml
/Users/zest/myworks/apt-ios-patch/pages-repo/index.html
/Users/zest/myworks/apt-ios-patch/pages-repo/Packages
/Users/zest/myworks/apt-ios-patch/pages-repo/Packages.gz
/Users/zest/myworks/apt-ios-patch/pages-repo/Release
/Users/zest/myworks/apt-ios-patch/pages-repo/CydiaIcon.png
/Users/zest/myworks/apt-ios-patch/pages-repo/favicon.ico
/Users/zest/myworks/apt-ios-patch/pages-repo/depictions/com.amg456.rootless.html
/Users/zest/myworks/apt-ios-patch/pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
```

Pages 当前挂载文件：

```text
pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
Size: 6206412
SHA256: 0695c1eb4a3bc7e928c76bf22256d5298be784bf0aa854b2addaef924a8a2866
```

本地校验：

```bash
python3 /Users/zest/myworks/apt-ios-patch/scripts/build_pages_repo.py
gzip -t /Users/zest/myworks/apt-ios-patch/pages-repo/Packages.gz
shasum -a 256 /Users/zest/myworks/apt-ios-patch/pages-repo/debs/com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb
```

`pages-repo/.gitattributes` 已覆盖 `*.deb` 与 `*.gz` 为普通 Git blob，避免 GitHub Pages 发布 Git LFS pointer。

后续前端页面进一步按原 `AMG官方源™` 越狱源结构做了分类目录还原：

```text
AWZ爱伪装: 1 packages
AMG: 3 packages
工具: 1 packages
越狱插件: 3 packages
ZORRO佐罗: 2 packages
Razer雷蛇: 3 packages
VBox虚拟盒子: 3 packages
```

实现边界：`pages-repo/index.html` 展示原源快照中的分类/条目结构，非补丁条目标记为“目录镜像”；APT `pages-repo/Packages` 与 `pages-repo/debs/` 仍只发布 `com.amg456.rootless_18.1.1_nopopup_2099_noheartbeat_noexit.deb` 一个补丁包。

## 22. 当前最新结论

最新 `nopopup_2099_noheartbeat_noexit` 包在前两阶段基础上新增了延迟退出移除：

1. `ActiveHUD.gg()` Swift/ObjC 入口直接返回，首页激活码弹窗不再展示。
2. `ActiveHUD.dd()` Swift/ObjC 入口固定返回 `4102444799`，过期时间等效为 `2099-12-31 23:59:59 UTC`。
3. `startAutoHeartbeat`、timer block、`heartbeat_action` 三处同时直接返回，阻断周期心跳 timer 创建与执行。
4. `TG@wx_zyyy.dylib` 内 4 处显式 `_exit(0)` 调用均替换为 `nop`，覆盖 `ActiveHUD.ff()` 的 1～2 分钟延迟退出 closure。
5. arm64 / arm64e 双架构 patch bytes 均已从最终 deb 反解包复验通过。
6. dylib 与 app 已重签；最终 deb 与 `pages-repo/` 静态源均已同步到 noheartbeat_noexit 版本。

后续如果真机仍出现延迟闪退，应继续按运行时证据定位其它定时器、后台线程或完整性检测分支；但当前已覆盖本次静态证据中最明确的 `ActiveHUD` 心跳链路。
