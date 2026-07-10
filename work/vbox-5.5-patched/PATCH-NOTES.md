# VBox 5.5 Rootless Patch Record

## Provenance

- Original package: `/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/VBox_5.5「无根」_5.5_com.amg456.VBox1.deb`
- Original package id/version: `com.amg456.VBox1` / `5.5`
- Published patch version: `5.5-6`
- Original SHA-256: `2ab876fc64885dbebbb2fc079a9009c7243144c1457ada0c85ecf5c936a3f290`
- License target: `var/jb/Library/MobileSubstrate/DynamicLibraries/VBoc.dylib`
- Home-page target: `var/jb/Applications/VBox.app/VBox`
- Original `VBoc.dylib` SHA-256: `e2aa03f6c409e2b564f5698d06e555f6724f6e903e7ecfccd6dabbe5f478f2d6`
- Patched and signed `VBoc.dylib` SHA-256: `c8ac52b66362dfa27816b82faf4ec0b1ebbd978d8dac62df938fdb6097001378`
- Original `VBox` SHA-256: `ad38cd8e805e9781a2528a239cfbab7aba58f80857fed576cc3c9d03a01e6f31`
- Patched and signed `VBox` SHA-256: `0e8d7ce49694fd0f5326ec6d39418642d716cd5378bc20fc64898c3b82f444c0`

## Evidence

`VBoc.dylib` is filtered to `com.google.vbox` / `VBox`. It contains the
activation endpoints `rauti.php?sn=...&km=` and `rauth.php?sn=`, the local
state path `/var/jb/var/mobile/Library/Preferences/AMG/sa.conf`, and the
Swift symbols `ActiveHUD.showActivationAlert` and `ActiveHUD.heartbeat_action`.

The `5.5-4` patch disabled the named heartbeat functions, the
`aaaaavvvvv()` scheduler and its 60-second state-reader closure, and the
`showActivationAlert()` entry. Runtime testing nevertheless reproduced the
two-action activation prompt. The prompt's exact embedded text is
`试用已到期，请输入激活码.` with `注册` and `退出` actions. Its main-actor UI
closure remained executable at arm64 `0xC170` / arm64e `0xCD90`.

The remaining control flow was broader than the original entry patch:

- `aaaaavvvvv()` owns three additional continuations that start the heartbeat,
  dynamically dispatch `showActivationAlert()`, or display a network-error
  alert. These must also return immediately if work was queued before an
  update or reached through a different continuation.
- The activation UI owns a registration action handler that reads the text
  field and submits to `rauti.php`, plus a shared action handler that calls
  `_exit(0)`. The same exit handler is reused by the network-error and
  `alertToExit` alerts.
- `ddddvvvvffff` processes registration results and can dispatch success,
  invalid-code, or network-error UI.
- `alertToExit(message)` calls `_exit(0)` immediately when `message == nil`;
  otherwise it presents an alert and schedules a second `_exit(0)` after 5
  seconds.

The outbound authorization endpoints are also closed at their only callers.
`API.ckkkkkeeeee()` constructs `rauth.php` and is called only from inside
`aaaaavvvvv()` (arm64 `0xB31C`, arm64e `0xBCB8`). `API.apsdsaeee(code:)`
constructs `rauti.php` and is called only from inside `ddddvvvvffff` (arm64
`0xE6BC`, arm64e `0xF6F8`). Both containing entries now return before those
calls, while the registration action handler is independently disabled.

All four application-owned `_exit` calls are now guarded by early returns in
their containing functions: arm64 `0xB790`, `0xCAD8`, `0xEA00`, `0xEF50` and
arm64e `0xC244`, `0xD770`, `0xFAFC`, `0x10150`. Swift runtime compatibility
`abort` sites are outside this authorization chain and remain unchanged.

The later `软件已过期，请输入激活码，注册后会自动退出请重新进入`
prompt is a separate main-executable path, not a remaining `VBoc.dylib` call.
Frida captured `VBox+0x50239C -> VBox+0x5897E0` for alert construction and
`VBox+0x5023F8` / `VBox+0x5024A0` for its `退出` / `注册并退出` actions. The
caller is `-[MainViewController pGflauxabac]`, invoked from `viewDidLoad`.

Runtime data-flow tracing closed the decisive branch:

- The helper return retained at `VBox+0x502244` is an empty mutable array;
  `count == 0` immediately reaches the alert block.
- The helper creates the array at `VBox+0x13FFD4`, reads
  `UIDevice.currentDevice.systemVersion` at `0x13FFF0` / `0x140008`, converts
  `15.8.8` with `floatValue` at `0x140020`, and compares it with `15.0` at
  `0x140050..0x140058`.
- No `NSDate`, `time`, `gettimeofday`, preferences, Keychain, file, SQLite, or
  network access occurs in this path. The trial-time hypothesis is therefore
  disproved; the code mislabels an iOS 15 compatibility gate as software
  expiry.
- Replacing the empty array with one element suppresses the prompt but reaches
  another explicit exit branch, so fabricating helper data is unsafe.
- Redirecting only the `viewDidLoad -> pGflauxabac` message to a benign method
  suppresses the prompt while VBox remains alive for more than 30 seconds.

`5.5-6` therefore returns immediately from `pGflauxabac`; it does not globally
forge time, arrays, alerts, or Objective-C return values.

The home-page authorization time does not come from `VBoc.dylib`'s
`getAuthEndTime:`. `MainViewController tableView:viewForHeaderInSection:` in
the main `VBox` executable reads the global `strExpiryTime` ivar, formats it as
a date, prefixes the result with the authorization-time label, and calls
`UILabel setText:`. Opaque control flow contains two equivalent formatting
branches at `0x1005F6ED4` and `0x1005F7FB4`; both must be patched.

## Binary Changes

| Architecture | Target | VA / file offset | Old bytes | New bytes |
| --- | --- | --- | --- | --- |
| arm64 | `-[MainViewController pGflauxabac]` compatibility/expiry protection | `0x100500E5C` / `0x500E5C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.aaaaavvvvv` scheduler | `0xB02C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | 60-second delayed-exit closure | `0xB700` | `ff0301d1` | `c0035fd6` (`ret`) |
| arm64 | delayed-chain heartbeat closure | `0xB894` | `ffc300d1` | `c0035fd6` (`ret`) |
| arm64 | delayed-chain activation-alert closure | `0xB8C8` | `ffc300d1` | `c0035fd6` (`ret`) |
| arm64 | delayed-chain network-error closure | `0xB920` | `ffc300d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.startAutoHeartbeat` | `0xB99C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | heartbeat timer closure | `0xBED0` | `ffc300d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.heartbeat_action` | `0xBF6C` | `ff8300d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.showActivationAlert` | `0xBFAC` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | activation-alert UI closure | `0xC170` | `ffc305d1` | `c0035fd6` (`ret`) |
| arm64 | registration action handler | `0xC600` | `ff4306d1` | `c0035fd6` (`ret`) |
| arm64 | shared alert exit action handler | `0xCAC0` | `ff8300d1` | `c0035fd6` (`ret`) |
| arm64 | `showNetErrorAlert` | `0xCB8C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | network-error alert UI closure | `0xCD50` | `ffc302d1` | `c0035fd6` (`ret`) |
| arm64 | registration-result handler `ddddvvvvffff` | `0xE5A4` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | registration-result UI closure | `0xE7F0` | `ff8301d1` | `c0035fd6` (`ret`) |
| arm64 | `alertToExit` | `0xE90C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | `alertToExit` UI closure | `0xEB80` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | `alertToExit` 5-second exit closure | `0xEF44` | `fd7bbfa9` | `c0035fd6` (`ret`) |
| arm64e | `ActiveHUD.aaaaavvvvv` scheduler | `0xB8A8` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | 60-second delayed-exit closure | `0xC1A0` | `7f2303d5ff0301d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | delayed-chain heartbeat closure | `0xC358` | `7f2303d5ffc300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | delayed-chain activation-alert closure | `0xC390` | `7f2303d5ffc300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | delayed-chain network-error closure | `0xC3FC` | `7f2303d5ffc300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `ActiveHUD.startAutoHeartbeat` | `0xC480` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | heartbeat timer closure | `0xCA44` | `7f2303d5ffc300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `ActiveHUD.heartbeat_action` | `0xCAEC` | `7f2303d5ff8300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `ActiveHUD.showActivationAlert` | `0xCB40` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | activation-alert UI closure | `0xCD90` | `7f2303d5ffc305d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | registration action handler | `0xD264` | `7f2303d5ff4306d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | shared alert exit action handler | `0xD754` | `7f2303d5ff8300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `showNetErrorAlert` | `0xD82C` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | network-error alert UI closure | `0xDA7C` | `7f2303d5ffc302d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | registration-result handler `ddddvvvvffff` | `0xF594` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | registration-result UI closure | `0xF888` | `7f2303d5ff8301d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `alertToExit` | `0xF9C8` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `alertToExit` UI closure | `0xFCD0` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `alertToExit` 5-second exit closure | `0x10140` | `7f2303d5fd7bbfa9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64 | Home expiry branch 1 | `0x1005F6ED4` / `0x5F6ED4` | `006969f8481900d001fd41f91f810a94604e40f9481900d0017d41f91b810a94` | `604e40f908409852e882b7720001631e481900d0018141f91f2003d51b810a94` |
| arm64 | Home expiry branch 2 | `0x1005F7FB4` / `0x5F7FB4` | `006969f8481900b001fd41f9e77c0a94601e40f9481900b0017d41f9e37c0a94` | `601e40f908409852e882b7720001631e481900b0018141f91f2003d5e37c0a94` |

The two home-page branches now call
`+[NSDate dateWithTimeIntervalSinceNow:3155673600]`. The interval is 36524
days, which maps the current validation date `2026-07-10` to the same date and
time in `2126`. The existing formatter remains responsible for the displayed
minutes and seconds, so the value is recalculated from device time whenever
the header is built.

The package `preinst` now terminates stale `VBox` / `VBox_` processes before
files are replaced, removes rootful `VBox.*` and `VBoc.*` injection leftovers,
and correctly treats `/Applications/VBox.app` as a directory. The package also
conflicts with the rootful and RootHide VBox variants, and `VBox_run` now uses
its computed rootless app path instead of hard-coding `/Applications`.

`scripts/patch_vbox_vboc.py` parses the original fat Mach-O architecture table,
checks the original file and thin-slice SHA256 values, verifies every old-byte
window, rejects duplicate, unordered, or overlapping patch definitions, and
applies all 19 patches to both architectures. The patched dylib
was ad-hoc re-signed with macOS `codesign` using identifier `vb1.dylib`; strict
verification reports `Signature=adhoc`. The full `VBox.app` bundle was
re-signed with identifier
`com.google.vbox` while preserving all 23 original entitlements and refreshing
the sealed-resource manifest; macOS `codesign -v --strict` accepts the result.

## Output

- Patched package: `VBox_5.5_rootless_5.5-6_com.amg456.VBox1_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb`
- Published package: `patched/VBox_5.5「无根」_5.5-6_com.amg456.VBox1_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb`
- Package SHA-256: `5881deae09d8709f0b1be5bc6813edbaf8ed20487c1ca80442f7ea00514264ff`
- Package size: `6343796` bytes
- Archive members: `debian-binary`, `control.tar.gz`, `data.tar.gz`
- Both tar members use deterministic GNU USTAR headers with numeric owner/group `0/0`; PAX and AppleDouble metadata are absent.

## Verification

The final package was unpacked with `ar -x`; its binaries matched the hashes
above. `otool -tvV` disassembled both home-page windows as a load of
`3155673600`, `ucvtf d0, w8`, and
`+[NSDate dateWithTimeIntervalSinceNow:]`; `0x100500E5C` disassembles as
`ret`. All 38 `VBoc.dylib` patch locations
disassemble as `ret` or `pacibsp; retab`, including every function containing
the four application-owned `_exit(0)` calls. The repository's
`validate_deb_archive` check accepted both final tar members.

`pages-repo/Packages` publishes only VBox `5.5-6` at
`./debs/com.amg456.VBox1_5.5-6_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb`; its Size and
SHA256 fields match the published file. `Packages.gz` also passes `gzip -t`.

Frida runtime validation on iOS `15.8.8` proved the equivalent
`viewDidLoad -> pGflauxabac` call suppression: the exact expiry alert was not
constructed and VBox remained alive beyond 30 seconds. Final-package device
validation still requires installing `5.5-6`; the expected home-page value on
`2026-07-10 HH:mm` is `2126-07-10 HH:mm`.

## Rebuild

```bash
bash scripts/build_vbox_dynamic100y.sh
python3 scripts/build_pages_repo.py
python3 scripts/verify_pages_repo.py
gzip -t pages-repo/Packages.gz
```

The VBox build script starts from the immutable audited main executable and
`VBoc.dylib`, checks the original SHA256 values and all old-byte windows,
preserves the original entitlements during app-bundle ad-hoc signing, creates
deterministic gzip/USTAR members, and validates both patched binaries after
extracting the finished deb before copying it to `patched/`.
