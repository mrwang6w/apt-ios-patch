#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CASE="$ROOT/work/ctwpro-5.6.0"
SOURCE="$ROOT/downloads/fuyonghua-repo/debs/560_CTW_Pro(无根版)_5.6.0_com.amg456.CTWPro.rootless560.deb"
SOURCE_SHA256="38234f4381b36587d43fc0f78dd77e9d386b7760a5412152024379233c1891b4"
OUTPUT_NAME="560_CTW_Pro(无根版)_5.6.0-offline4_com.amg456.CTWPro.rootless560_deep_offline_ustar.deb"
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
PATCH_SOURCE="$ROOT/work/ctwpro-rootless-5.6.0/patch-src/CTWProDeepPatch.m"
PUBLISH_TMP="$ROOT/patched/.$OUTPUT_NAME.tmp"

trap 'rm -f "$PUBLISH_TMP"' EXIT

verify_offline_random_contract() {
  local dylib="$1"
  local metadata
  metadata="$(otool -ov "$dylib")"
  for expected in \
    'imp     0x9958 +[LKVdConfig randomConfig]' \
    'imp     0xb6f8 -[LKDeviceConfig writeCachedConfigString:]' \
    'imp     0xc064 -[LKDeviceConfig randomHexStringWithLength:]' \
    'imp     0xc0f8 -[LKDeviceConfig randomAlphanumericStringWithLength:]' \
    'imp     0xcae8 -[LKDeviceConfig randomMacAddress]' \
    'imp     0xcbb0 -[LKDeviceConfig randomUnknownNumber]' \
    'imp     0xcc0c -[LKDeviceConfig makeRandomConfig]' \
    'imp     0xd6f4 -[LKDeviceConfig defaultConfig]'; do
    if ! rg -Fq "$expected" <<<"$metadata"; then
      echo "offline random method contract is missing: $expected" >&2
      return 1
    fi
  done
}

actual_sha256="$(shasum -a 256 "$SOURCE" | awk '{print $1}')"
if [[ "$actual_sha256" != "$SOURCE_SHA256" ]]; then
  echo "unexpected source deb SHA256: $actual_sha256" >&2
  exit 1
fi

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
        line = "Version: 5.6.0-offline4"
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
if not inserted or "Version: 5.6.0-offline4" not in result:
    raise SystemExit("failed to update control metadata")
path.write_text("\n".join(result) + "\n", encoding="utf-8")
PY
chmod 0644 "$ROOTFS/DEBIAN/control"
chmod 0755 "$ROOTFS/DEBIAN/postinst" "$ROOTFS/DEBIAN/prerm"

APP="$ROOTFS/var/jb/Applications/CTW Pro.app"
MAIN="$APP/CTW Pro"
FIX="$APP/fix.dylib"
LICENSE_DYLIB="$ROOTFS/var/jb/Library/MobileSubstrate/DynamicLibraries/CTW.dylib"

ldid -e "$MAIN" > "$ENTITLEMENTS"
plutil -lint "$ENTITLEMENTS"

python3 "$ROOT/scripts/patch_ctwpro_amg456_main.py" patch "$MAIN" "$MAIN"
python3 "$ROOT/scripts/patch_ctwpro_amg456_license.py" \
  patch "$LICENSE_DYLIB" "$LICENSE_DYLIB"
codesign --force --sign - --timestamp=none "$LICENSE_DYLIB"
codesign --verify --strict "$LICENSE_DYLIB"
python3 "$ROOT/scripts/patch_ctwpro_amg456_license.py" verify "$LICENSE_DYLIB"
verify_offline_random_contract "$LICENSE_DYLIB"

SDK="$(xcrun --sdk iphoneos --show-sdk-path)"
xcrun --sdk iphoneos clang \
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
  randomConfig \
  defaultConfig \
  randomHexStringWithLength: \
  randomAlphanumericStringWithLength: \
  randomMacAddress \
  randomUnknownNumber \
  writeCachedConfigString: \
  setDevice_updated:; do
  if ! strings -a "$FIX" | rg -Fxq "$selector"; then
    echo "fix.dylib is missing offline random selector: $selector" >&2
    exit 1
  fi
done

codesign --force --sign - --timestamp=none \
  --identifier com.xxdevice.CTWPro \
  --entitlements "$ENTITLEMENTS" "$APP"
codesign --verify --deep --strict "$APP"
python3 "$ROOT/scripts/patch_ctwpro_amg456_main.py" verify "$MAIN"

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

if ! otool -l "$MAIN" | rg -A6 -B4 '@executable_path/fix\.dylib' \
  | rg -q 'LC_LOAD_DYLIB'; then
  echo "strong fix.dylib load command is missing" >&2
  exit 1
fi
if ! otool -D "$FIX" | rg -q '^@executable_path/fix\.dylib$'; then
  echo "fix.dylib install name is incorrect" >&2
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
python3 "$ROOT/scripts/patch_ctwpro_amg456_main.py" verify "$VERIFY_MAIN"
python3 "$ROOT/scripts/patch_ctwpro_amg456_license.py" verify "$VERIFY_LICENSE"
verify_offline_random_contract "$VERIFY_LICENSE"
codesign --verify --strict "$VERIFY_FIX"
codesign --verify --deep --strict "$VERIFY_APP"
codesign --verify --strict "$VERIFY_LICENSE"

grep -qx 'Package: com.amg456.CTWPro.rootless560' "$VERIFY/control/control"
grep -qx 'Version: 5.6.0-offline4' "$VERIFY/control/control"
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
print("payload diff verified: 2 added, 2 changed, 0 removed")
PY

for file in \
  "$VERIFY_MAIN" \
  "$VERIFY_FIX" \
  "$VERIFY_LICENSE" \
  "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib" \
  "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/ctwsup.dylib" \
  "$VERIFY/rootfs/var/jb/usr/bin/ctwsrv"; do
  test "$(stat -f '%OLp' "$file")" = "755"
done

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
