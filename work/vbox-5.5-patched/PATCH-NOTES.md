# VBox 5.5 Rootless Patch Record

## Provenance

- Original package: `/Users/zest/myworks/apt-ios-patch/downloads/amg456-repo/debs/VBox_5.5「无根」_5.5_com.amg456.VBox1.deb`
- Package id/version: `com.amg456.VBox1` / `5.5-1`
- Original SHA-256: `2ab876fc64885dbebbb2fc079a9009c7243144c1457ada0c85ecf5c936a3f290`
- Patch target: `var/jb/Library/MobileSubstrate/DynamicLibraries/VBoc.dylib`
- Original target SHA-256: `e2aa03f6c409e2b564f5698d06e555f6724f6e903e7ecfccd6dabbe5f478f2d6`
- Patched target SHA-256: `09114cdbf547fcf4ee2294af05ae2ee2c46916153d058bf2b099cd1a57cfe498`

## Evidence

`VBoc.dylib` is filtered to `com.google.vbox` / `VBox`. It contains the
activation endpoints `rauti.php?sn=...&km=` and `rauth.php?sn=`, the local
state path `/var/jb/var/mobile/Library/Preferences/AMG/sa.conf`, and the
Swift symbols `ActiveHUD.showActivationAlert` and `ActiveHUD.heartbeat_action`.

## Binary Changes

| Architecture | Function | Slice VA/offset | Old bytes | New bytes |
| --- | --- | --- | --- | --- |
| arm64 | `ActiveHUD.heartbeat_action` | `0xBF6C` | `ff8300d1` | `c0035fd6` (`ret`) |
| arm64 | `ActiveHUD.showActivationAlert` | `0xBFAC` | `f44fbea9` | `c0035fd6` (`ret`) |
| arm64e | `ActiveHUD.heartbeat_action` | `0xCAEC` | `7f2303d5` | `ff0f5fd6` (`retab`) |
| arm64e | `ActiveHUD.showActivationAlert` | `0xCB40` | `7f2303d5` | `ff0f5fd6` (`retab`) |

The patched dylib was ad-hoc re-signed with `ldid -S` after its two slices
were recombined.

## Output

- Patched package: `VBox_5.5_rootless_5.5-1_com.amg456.VBox1_nolicense_ustar.deb`
- Package SHA-256: `28cfcda362c30a75ab8d37f57710fa4dab85acc656cf729cb4899e4cb222c17f`
- Archive members: `debian-binary`, `control.tar.gz`, `data.tar.gz`
- Both tar members use deterministic GNU USTAR headers with numeric owner/group `0/0`; PAX and AppleDouble metadata are absent.

## Verification

The final package was unpacked with `ar -x`; its `VBoc.dylib` matched the
patched target SHA-256. `radare2` disassembled all four listed locations as
the expected `ret` / `retab` instructions. The repository's
`validate_deb_archive` check also accepted both final tar members.

Runtime validation still requires installing the package on a compatible
rootless iOS device and confirming that the app launches without the
activation prompt after a respring.
