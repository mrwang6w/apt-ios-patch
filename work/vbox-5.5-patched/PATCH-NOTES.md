# VBox 5.5 Rootless Patch Record

## Provenance

- Original package: `/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/VBox_5.5「无根」_5.5_com.amg456.VBox1.deb`
- Original package id/version: `com.amg456.VBox1` / `5.5-1`
- Published patch version: `5.5-4`
- Original SHA-256: `2ab876fc64885dbebbb2fc079a9009c7243144c1457ada0c85ecf5c936a3f290`
- License target: `var/jb/Library/MobileSubstrate/DynamicLibraries/VBoc.dylib`
- Home-page target: `var/jb/Applications/VBox.app/VBox`
- Original `VBoc.dylib` SHA-256: `e2aa03f6c409e2b564f5698d06e555f6724f6e903e7ecfccd6dabbe5f478f2d6`
- Patched and signed `VBoc.dylib` SHA-256: `dea4135c387356931e1afa390483833569882073df390725be858f3acb4f79de`
- Original `VBox` SHA-256: `ad38cd8e805e9781a2528a239cfbab7aba58f80857fed576cc3c9d03a01e6f31`
- Patched and signed `VBox` SHA-256: `cd6205753187fb6cbecd11117cfd2945eecff00f5ecc6e150fa3b3aa7f399886`

## Evidence

`VBoc.dylib` is filtered to `com.google.vbox` / `VBox`. It contains the
activation endpoints `rauti.php?sn=...&km=` and `rauth.php?sn=`, the local
state path `/var/jb/var/mobile/Library/Preferences/AMG/sa.conf`, and the
Swift symbols `ActiveHUD.showActivationAlert` and `ActiveHUD.heartbeat_action`.

The previous `5.5-3` patch returned early only from `heartbeat_action`. It left
two independently reachable scheduling layers intact. `startAutoHeartbeat`
could still create its `NSTimer`, while `SBURLProtocol.startLoading` could call
`ActiveHUD.aaaaavvvvv()`. The latter schedules a main-queue closure after the
double constant `60.0`; that closure reads the authorization state again and
calls `_exit(0)` when the state is still absent. The confirmed delayed-exit
calls are at arm64 `0xB790` and arm64e `0xC244`.

The home-page authorization time does not come from `VBoc.dylib`'s
`getAuthEndTime:`. `MainViewController tableView:viewForHeaderInSection:` in
the main `VBox` executable reads the global `strExpiryTime` ivar, formats it as
a date, prefixes the result with the authorization-time label, and calls
`UILabel setText:`. Opaque control flow contains two equivalent formatting
branches at `0x1005F6ED4` and `0x1005F7FB4`; both must be patched.

## Binary Changes

| Architecture | Target | VA / file offset | Old bytes | New bytes |
| --- | --- | --- | --- | --- |
| arm64 | `ActiveHUD.aaaaavvvvv` scheduler | `0xB02C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | 60-second delayed-exit closure | `0xB700` | `ff0301d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.startAutoHeartbeat` | `0xB99C` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64 | heartbeat timer closure | `0xBED0` | `ffc300d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.heartbeat_action` | `0xBF6C` | `ff8300d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.showActivationAlert` | `0xBFAC` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64e | `ActiveHUD.aaaaavvvvv` scheduler | `0xB8A8` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | 60-second delayed-exit closure | `0xC1A0` | `7f2303d5ff0301d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `ActiveHUD.startAutoHeartbeat` | `0xC480` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | heartbeat timer closure | `0xCA44` | `7f2303d5ffc300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `ActiveHUD.heartbeat_action` | `0xCAEC` | `7f2303d5ff8300d1` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64e | `ActiveHUD.showActivationAlert` | `0xCB40` | `7f2303d5f44fbea9` | `7f2303d5ff0f5fd6` (`pacibsp; retab`) |
| arm64 | Home expiry branch 1 | `0x1005F6ED4` / `0x5F6ED4` | `006969f8481900d001fd41f91f810a94604e40f9481900d0017d41f91b810a94` | `604e40f908409852e882b7720001631e481900d0018141f91f2003d51b810a94` |
| arm64 | Home expiry branch 2 | `0x1005F7FB4` / `0x5F7FB4` | `006969f8481900b001fd41f9e77c0a94601e40f9481900b0017d41f9e37c0a94` | `601e40f908409852e882b7720001631e481900b0018141f91f2003d5e37c0a94` |

The two home-page branches now call
`+[NSDate dateWithTimeIntervalSinceNow:3155673600]`. The interval is 36524
days, which maps the current validation date `2026-07-10` to the same date and
time in `2126`. The existing formatter remains responsible for the displayed
minutes and seconds, so the value is recalculated from device time whenever
the header is built.

`scripts/patch_vbox_vboc.py` parses the original fat Mach-O architecture table,
checks the original file and thin-slice SHA256 values, verifies every old-byte
window, and applies all six patches to both architectures. The patched dylib
was ad-hoc re-signed with macOS `codesign` using identifier `vb1.dylib`; strict
verification reports `Signature=adhoc`. The full `VBox.app` bundle was
re-signed with identifier
`com.google.vbox` while preserving all 23 original entitlements and refreshing
the sealed-resource manifest; macOS `codesign -v --strict` accepts the result.

## Output

- Patched package: `VBox_5.5_rootless_5.5-4_com.amg456.VBox1_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb`
- Published package: `patched/VBox_5.5「无根」_5.5-4_com.amg456.VBox1_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb`
- Package SHA-256: `9a9cabe9045455331176f0ee2242ed14e74cb86577829d0b3b7ce1b0e7e2ca38`
- Package size: `6343758` bytes
- Archive members: `debian-binary`, `control.tar.gz`, `data.tar.gz`
- Both tar members use deterministic GNU USTAR headers with numeric owner/group `0/0`; PAX and AppleDouble metadata are absent.

## Verification

The final package was unpacked with `ar -x`; its binaries matched the hashes
above. `otool -tvV` disassembled both home-page windows as a load of
`3155673600`, `ucvtf d0, w8`, and
`+[NSDate dateWithTimeIntervalSinceNow:]`. All twelve `VBoc.dylib` patch
locations disassemble as `ret` or `pacibsp; retab`, including the scheduler and
closure that previously reached the 60-second `_exit(0)`. The repository's
`validate_deb_archive` check accepted both final tar members.

`pages-repo/Packages` publishes only VBox `5.5-4` at
`./debs/com.amg456.VBox1_5.5-4_nolicense_noheartbeat_nodelayedexit_dynamic100y_ustar.deb`; its Size and
SHA256 fields match the published file. `Packages.gz` also passes `gzip -t`.

Runtime validation still requires installing `5.5-4` on a compatible rootless
iOS device, respringing, and reopening the home page. The expected value on
`2026-07-10 HH:mm` is `2126-07-10 HH:mm`.

## Rebuild

```bash
bash scripts/build_vbox_dynamic100y.sh
python3 scripts/build_pages_repo.py
gzip -t pages-repo/Packages.gz
```

The VBox build script starts from the immutable audited main executable and
`VBoc.dylib`, checks the original SHA256 values and all old-byte windows,
preserves the original entitlements during app-bundle ad-hoc signing, creates
deterministic gzip/USTAR members, and validates the finished deb before copying
it to `patched/`.
