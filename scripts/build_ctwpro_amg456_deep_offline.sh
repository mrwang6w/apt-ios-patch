#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CASE="$ROOT/work/ctwpro-5.6.0"
XCODE_DEVELOPER="/Applications/Xcode.app/Contents/Developer"
XCODE_TOOLCHAIN="$XCODE_DEVELOPER/Toolchains/XcodeDefault.xctoolchain/usr/bin"
XCODE_STRINGS="$XCODE_TOOLCHAIN/strings"
XCODE_OTOOL="/Library/Developer/CommandLineTools/usr/bin/otool"
CLANG="$XCODE_TOOLCHAIN/clang"
SDK="$XCODE_DEVELOPER/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
for required_tool in "$XCODE_STRINGS" "$XCODE_OTOOL" "$CLANG"; do
  if [[ ! -x "$required_tool" ]]; then
    echo "required Xcode tool is missing: $required_tool" >&2
    exit 1
  fi
done
if [[ ! -d "$SDK" ]]; then
  echo "required iPhoneOS SDK is missing: $SDK" >&2
  exit 1
fi
SOURCE="$ROOT/downloads/fuyonghua-repo/debs/560_CTW_Pro(无根版)_5.6.0_com.amg456.CTWPro.rootless560.deb"
SOURCE_SHA256="38234f4381b36587d43fc0f78dd77e9d386b7760a5412152024379233c1891b4"
OUTPUT_NAME="560_CTW_Pro(无根版)_5.6.0-offline17_com.amg456.CTWPro.rootless560_deep_offline_ustar.deb"
OUTPUT="$ROOT/patched/$OUTPUT_NAME"
AUDIT="$CASE/deep-source-audit"
BUILD="$CASE/deep-build"
ROOTFS="$BUILD/root"
PARTS="$BUILD/parts"
CANDIDATE="$BUILD/$OUTPUT_NAME"
VERIFY="$CASE/deep-verify"
PREPUBLISH_AUDIT="$CASE/deep-prepublish-audit"
ENTITLEMENTS="$BUILD/CTWPro.entitlements.plist"
SIGNED_ENTITLEMENTS="$BUILD/CTWPro.signed.entitlements.plist"
PATCH_SOURCE="$ROOT/patches/ctwpro/CTWProDeepPatch.m"
BRIDGE_SOURCE="$ROOT/patches/ctwpro/CTWProIdentityBridge.m"
PUBLISH_TMP="$ROOT/patched/.$OUTPUT_NAME.tmp"

trap 'rm -f "$PUBLISH_TMP"' EXIT

verify_offline_random_helpers() {
  local dylib="$1"
  local metadata
  metadata="$("$XCODE_OTOOL" -ov "$dylib")"
  for expected in \
    'imp     0xb6f8 -[LKDeviceConfig writeCachedConfigString:]' \
    'imp     0xc064 -[LKDeviceConfig randomHexStringWithLength:]' \
    'imp     0xc0f8 -[LKDeviceConfig randomAlphanumericStringWithLength:]' \
    'imp     0xcae8 -[LKDeviceConfig randomMacAddress]' \
    'imp     0xcbb0 -[LKDeviceConfig randomUnknownNumber]' \
    'imp     0xd6f4 -[LKDeviceConfig defaultConfig]'; do
    if ! grep -Fq -- "$expected" <<<"$metadata"; then
      echo "offline random helper contract is missing: $expected" >&2
      return 1
    fi
  done
}

verify_random_action_contract() {
  local main="$1"
  local nib="$2"
  local expected_stub_prefix="${3:-original}"
  python3 - "$main" "$expected_stub_prefix" <<'PY'
import sys
from pathlib import Path

blob = Path(sys.argv[1]).read_bytes()
expected_stub_prefix = sys.argv[2]
stub_prefixes = {
    "original": bytes.fromhex(
        "e923b96dfc6f01a9fa6702a9f85f03a9"
        "f65704a9f44f05a9fd7b06a9fd830191"
    ),
    "disabled": bytes.fromhex(
        "c0035fd6fc6f01a9fa6702a9f85f03a9"
        "f65704a9f44f05a9fd7b06a9fd830191"
    ),
}
if expected_stub_prefix not in stub_prefixes:
    raise SystemExit(f"unknown stub contract: {expected_stub_prefix}")
checks = {
    0x154FDDE: bytes.fromhex(
        "72616e646f6d507265666572656e6365733a00"
    ),
    0xD5424: bytes.fromhex(
        "c0a300d000783791a90e5194e10300aaa282d7101f2003d5"
        "96a40090d6ce3391e00313aae30316aab80c5194"
    ),
    0x84488: bytes.fromhex(
        "fc6fbaa9fa6701a9f85f02a9f65703a9"
        "f44f04a9fd7b05a9fd430191ff0301d1"
    ),
    0x53DE04: stub_prefixes[expected_stub_prefix],
}
for offset, expected in checks.items():
    actual = blob[offset:offset + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"random action contract mismatch at {offset:#x}: "
            f"{actual.hex()} != {expected.hex()}"
        )
print(
    "random action contract verified: "
    f"selector, registration, action and {expected_stub_prefix} apply IMP"
)
PY
  for action in randomPreferences: nativePreferences:; do
    if ! "$XCODE_STRINGS" -a "$nib" | grep -Fxq -- "$action"; then
      echo "storyboard random action is missing: $action" >&2
      return 1
    fi
  done
}

verify_compatible_profile_contract() {
  python3 - "$1" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
models = re.findall(
    r'\{"(iPhone9,[1-4])", "(D(?:10|11|101|111)AP)", "(\d+)", '
    r'"(\d+)", (\d+)ULL, (\d+)ULL\}',
    source,
)
systems = re.findall(r'\{"(15\.8\.[45])", "(19H39[04])", "(15_8_[45])"\}', source)
expected_models = {
    ("iPhone9,1", "D10AP", "750", "1334", "2097807360", "127968497664"),
    ("iPhone9,2", "D11AP", "1242", "2208", "3144810496", "127968497664"),
    ("iPhone9,3", "D101AP", "750", "1334", "2097807360", "127968497664"),
    ("iPhone9,4", "D111AP", "1242", "2208", "3144810496", "127968497664"),
}
expected_systems = {
    ("15.8.4", "19H390", "15_8_4"),
    ("15.8.5", "19H394", "15_8_5"),
}
if set(models) != expected_models or set(systems) != expected_systems:
    raise SystemExit(f"compatible profile contract mismatch: models={models} systems={systems}")
print("compatible profile contract verified: 4 A10 models x 2 iOS builds")
PY
}

actual_sha256="$(shasum -a 256 "$SOURCE" | awk '{print $1}')"
if [[ "$actual_sha256" != "$SOURCE_SHA256" ]]; then
  echo "unexpected source deb SHA256: $actual_sha256" >&2
  exit 1
fi
verify_compatible_profile_contract "$PATCH_SOURCE"

rm -rf "$AUDIT" "$BUILD" "$VERIFY" "$PREPUBLISH_AUDIT"
python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$SOURCE" --out "$AUDIT"
mkdir -p "$ROOTFS/DEBIAN" "$PARTS" "$VERIFY/control" "$VERIFY/rootfs" "$ROOT/patched"
COPYFILE_DISABLE=1 gtar -xzf "$AUDIT/raw/data.tar.gz" \
  --no-same-owner --same-permissions -C "$ROOTFS"
cp -a "$AUDIT/control/." "$ROOTFS/DEBIAN/"
chmod 0644 "$ROOTFS/DEBIAN/control"

python3 - "$ROOTFS/DEBIAN/control" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
fields = [line.partition(":")[0] for line in lines if line and not line[0].isspace() and ":" in line]
if fields.count("Version") != 1:
    raise SystemExit(f"unexpected Version field count: {fields.count('Version')}")
for field in ("Conflicts", "Provides", "Replaces"):
    if field in fields:
        raise SystemExit(f"source control unexpectedly contains {field}")

result = []
inserted = False
for line in lines:
    if line == "Version: 5.6.0":
        line = "Version: 5.6.0-offline17"
    result.append(line)
    if line.startswith("Depends:"):
        result.extend(
            [
                "Conflicts: com.xxdevice.ctwpro.rootless560",
                "Provides: com.xxdevice.ctwpro.rootless560",
                "Replaces: com.xxdevice.ctwpro.rootless560",
            ]
        )
        inserted = True
if not inserted or "Version: 5.6.0-offline17" not in result:
    raise SystemExit("failed to update control metadata")
path.write_text("\n".join(result) + "\n", encoding="utf-8")
PY
chmod 0644 "$ROOTFS/DEBIAN/control"
chmod 0755 "$ROOTFS/DEBIAN/postinst" "$ROOTFS/DEBIAN/prerm"

APP="$ROOTFS/var/jb/Applications/CTW Pro.app"
MAIN="$APP/CTW Pro"
FIX="$APP/fix.dylib"
LICENSE_DYLIB="$ROOTFS/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib"
IDENTITY_BRIDGE="$ROOTFS/var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.dylib"
IDENTITY_FILTER="$ROOTFS/var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.plist"
RANDOM_ACTION_NIB="$APP/zh-Hans.lproj/Main.storyboardc/UITableViewController-Kzn-J4-oBc.nib"

ldid -e "$MAIN" > "$ENTITLEMENTS"
plutil -lint "$ENTITLEMENTS"
verify_random_action_contract "$MAIN" "$RANDOM_ACTION_NIB" original

python3 "$ROOT/scripts/patch_ctwpro_amg456_main.py" patch "$MAIN" "$MAIN"
python3 "$ROOT/scripts/patch_ctwpro_amg456_license.py" \
  patch "$LICENSE_DYLIB" "$LICENSE_DYLIB"
codesign --force --sign - --timestamp=none "$LICENSE_DYLIB"
codesign --verify --strict "$LICENSE_DYLIB"
python3 "$ROOT/scripts/patch_ctwpro_amg456_license.py" verify "$LICENSE_DYLIB"
verify_offline_random_helpers "$LICENSE_DYLIB"

"$CLANG" \
  -arch arm64 \
  -isysroot "$SDK" \
  -miphoneos-version-min=12.0 \
  -dynamiclib \
  -fobjc-arc \
  -fblocks \
  -fvisibility=hidden \
  -O2 \
  -Wall \
  -Wextra \
  -Werror \
  -Wl,-no_uuid \
  -Wl,-install_name,@executable_path/fix.dylib \
  -framework Foundation \
  -framework UIKit \
  "$PATCH_SOURCE" \
  -o "$FIX"
chmod 0755 "$FIX"
codesign --force --sign - --timestamp=none "$FIX"
codesign --verify --strict "$FIX"
for selector in \
  randomPreferences: \
  nativePreferences: \
  performeMachineStub \
  setValue:forKey: \
  save \
  reloadData \
  config \
  readCachedConfigString \
  defaultConfig \
  randomHexStringWithLength: \
  randomAlphanumericStringWithLength: \
  randomMacAddress \
  randomUnknownNumber \
  writeCachedConfigString: \
  setConfig: \
  setDevice_updated:; do
  if ! "$XCODE_STRINGS" -a "$FIX" | grep -Fxq -- "$selector"; then
    echo "fix.dylib is missing offline random selector: $selector" >&2
    exit 1
  fi
done

cat > "$IDENTITY_FILTER" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Filter</key>
  <dict>
    <key>Bundles</key>
    <array>
      <string>com.apple.UIKit</string>
    </array>
  </dict>
</dict>
</plist>
PLIST
chmod 0644 "$IDENTITY_FILTER"
plutil -lint "$IDENTITY_FILTER"

"$CLANG" \
  -arch arm64 \
  -isysroot "$SDK" \
  -miphoneos-version-min=12.0 \
  -dynamiclib \
  -fobjc-arc \
  -fblocks \
  -fvisibility=hidden \
  -O2 \
  -Wall \
  -Wextra \
  -Werror \
  -Wl,-no_uuid \
  -Wl,-install_name,/var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.dylib \
  -framework Foundation \
  -framework CoreFoundation \
  "$BRIDGE_SOURCE" \
  -o "$IDENTITY_BRIDGE"
chmod 0755 "$IDENTITY_BRIDGE"
codesign --force --sign - --timestamp=none "$IDENTITY_BRIDGE"
codesign --verify --strict "$IDENTITY_BRIDGE"
for marker in \
  MGCopyAnswer \
  MSHookFunction \
  ProductType \
  ProductVersion \
  UniqueDeviceID \
  SerialNumber \
  WiFiAddress \
  /var/jb/var/mobile/Library/Preferences/AMG/faker.plist; do
  if ! "$XCODE_STRINGS" -a "$IDENTITY_BRIDGE" | grep -Fxq -- "$marker"; then
    echo "identity bridge is missing marker: $marker" >&2
    exit 1
  fi
done
for marker in \
  /var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib \
  Applylist \
  SettingsBackup \
  ContainerRebuild \
  ClearPB \
  config-dlopen \
  config-class \
  config-shared-selector \
  config-shared-instance \
  config-setup-contract \
  _setupConfig \
  profile-data \
  model-profile \
  iPhone9,1 \
  iPhone9,2 \
  iPhone9,3 \
  iPhone9,4 \
  15.8.4 \
  15.8.5 \
  19H390 \
  19H394 \
  AMG2018 \
  /var/jb/var/mobile/Library/Preferences/AMG/faker.plist \
  amg-crypto-contract \
  amg-profile-write \
  amg-profile-verify; do
  if ! "$XCODE_STRINGS" -a "$FIX" | grep -Fxq -- "$marker"; then
    echo "fix.dylib is missing runtime load marker: $marker" >&2
    exit 1
  fi
done

codesign --force --sign - --timestamp=none \
  --identifier com.xxdevice.CTWPro \
  --entitlements "$ENTITLEMENTS" "$APP"
codesign --verify --deep --strict "$APP"
python3 "$ROOT/scripts/patch_ctwpro_amg456_main.py" verify "$MAIN"
verify_random_action_contract "$MAIN" "$RANDOM_ACTION_NIB" disabled

ldid -e "$MAIN" > "$SIGNED_ENTITLEMENTS"
python3 - "$ENTITLEMENTS" "$SIGNED_ENTITLEMENTS" <<'PY'
import plistlib
import sys
from pathlib import Path

before = plistlib.loads(Path(sys.argv[1]).read_bytes())
after = plistlib.loads(Path(sys.argv[2]).read_bytes())
if before != after:
    raise SystemExit("signed CTW Pro entitlements differ from the original")
print(f"entitlements verified: {len(before)} keys")
PY

if ! "$XCODE_OTOOL" -l "$MAIN" | grep -A6 -B4 -E '@executable_path/fix\.dylib' \
  | grep -q 'LC_LOAD_DYLIB'; then
  echo "strong fix.dylib load command is missing" >&2
  exit 1
fi
if ! "$XCODE_OTOOL" -D "$FIX" | grep -q '^@executable_path/fix\.dylib$'; then
  echo "fix.dylib install name is incorrect" >&2
  exit 1
fi
if ! "$XCODE_OTOOL" -D "$IDENTITY_BRIDGE" \
  | grep -q '^/var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge\.dylib$'; then
  echo "identity bridge install name is incorrect" >&2
  exit 1
fi

printf '2.0\n' > "$PARTS/debian-binary"
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' --no-xattrs \
  -cf "$PARTS/control.tar" -C "$ROOTFS/DEBIAN" .
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' --no-xattrs \
  -cf "$PARTS/data.tar" -C "$ROOTFS" var
gzip -n -9 -c "$PARTS/control.tar" > "$PARTS/control.tar.gz"
gzip -n -9 -c "$PARTS/data.tar" > "$PARTS/data.tar.gz"
python3 "$ROOT/scripts/build_deb_ar.py" "$CANDIDATE" \
  "$PARTS/debian-binary" "$PARTS/control.tar.gz" "$PARTS/data.tar.gz"

(cd "$VERIFY" && ar -x "$CANDIDATE")
test "$(cat "$VERIFY/debian-binary")" = "2.0"
gzip -t "$VERIFY/control.tar.gz" "$VERIFY/data.tar.gz"
gtar -xzf "$VERIFY/control.tar.gz" -C "$VERIFY/control"
gtar -xzf "$VERIFY/data.tar.gz" --same-permissions -C "$VERIFY/rootfs"

VERIFY_APP="$VERIFY/rootfs/var/jb/Applications/CTW Pro.app"
VERIFY_MAIN="$VERIFY_APP/CTW Pro"
VERIFY_FIX="$VERIFY_APP/fix.dylib"
VERIFY_LICENSE="$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib"
VERIFY_IDENTITY_BRIDGE="$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.dylib"
VERIFY_IDENTITY_FILTER="$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.plist"
VERIFY_RANDOM_ACTION_NIB="$VERIFY_APP/zh-Hans.lproj/Main.storyboardc/UITableViewController-Kzn-J4-oBc.nib"
python3 "$ROOT/scripts/patch_ctwpro_amg456_main.py" verify "$VERIFY_MAIN"
python3 "$ROOT/scripts/patch_ctwpro_amg456_license.py" verify "$VERIFY_LICENSE"
verify_offline_random_helpers "$VERIFY_LICENSE"
verify_random_action_contract "$VERIFY_MAIN" "$VERIFY_RANDOM_ACTION_NIB" disabled
codesign --verify --strict "$VERIFY_FIX"
codesign --verify --deep --strict "$VERIFY_APP"
codesign --verify --strict "$VERIFY_LICENSE"
codesign --verify --strict "$VERIFY_IDENTITY_BRIDGE"
plutil -lint "$VERIFY_IDENTITY_FILTER"

grep -qx 'Package: com.amg456.CTWPro.rootless560' "$VERIFY/control/control"
grep -qx 'Version: 5.6.0-offline17' "$VERIFY/control/control"
grep -qx 'Conflicts: com.xxdevice.ctwpro.rootless560' "$VERIFY/control/control"
grep -qx 'Provides: com.xxdevice.ctwpro.rootless560' "$VERIFY/control/control"
grep -qx 'Replaces: com.xxdevice.ctwpro.rootless560' "$VERIFY/control/control"

python3 - "$AUDIT/rootfs" "$VERIFY/rootfs" <<'PY'
import hashlib
import sys
from pathlib import Path

source = Path(sys.argv[1])
patched = Path(sys.argv[2])

def manifest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }

before = manifest(source)
after = manifest(patched)
added = set(after) - set(before)
removed = set(before) - set(after)
changed = {name for name in set(before) & set(after) if before[name] != after[name]}
expected_added = {
    "var/jb/Applications/CTW Pro.app/_CodeSignature/CodeResources",
    "var/jb/Applications/CTW Pro.app/fix.dylib",
    "var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.dylib",
    "var/jb/Library/MobileSubstrate/DynamicLibraries/zzCTWIdentityBridge.plist",
}
expected_changed = {
    "var/jb/Applications/CTW Pro.app/CTW Pro",
    "var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib",
}
if added != expected_added or removed or changed != expected_changed:
    raise SystemExit(
        f"unexpected payload diff: added={sorted(added)} "
        f"removed={sorted(removed)} changed={sorted(changed)}"
    )
print("payload diff verified: 4 added, 2 changed, 0 removed")
PY

for file in \
  "$VERIFY_MAIN" \
  "$VERIFY_FIX" \
  "$VERIFY_LICENSE" \
  "$VERIFY_IDENTITY_BRIDGE" \
  "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib" \
  "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/ctwsup.dylib" \
  "$VERIFY/rootfs/var/jb/usr/bin/ctwsrv"; do
  test "$(stat -f '%OLp' "$file")" = "755"
done
test "$(stat -f '%OLp' "$VERIFY_IDENTITY_FILTER")" = "644"

python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$CANDIDATE" --out "$PREPUBLISH_AUDIT"

cp "$CANDIDATE" "$PUBLISH_TMP"
cmp "$CANDIDATE" "$PUBLISH_TMP"
mv -f "$PUBLISH_TMP" "$OUTPUT"
trap - EXIT

candidate_sha256="$(shasum -a 256 "$CANDIDATE" | awk '{print $1}')"
output_sha256="$(shasum -a 256 "$OUTPUT" | awk '{print $1}')"
if [[ "$candidate_sha256" != "$output_sha256" ]]; then
  echo "published deb hash differs from verified candidate" >&2
  exit 1
fi

shasum -a 256 "$OUTPUT"
stat -f 'size=%z bytes' "$OUTPUT"
