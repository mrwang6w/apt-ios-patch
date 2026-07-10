#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CASE="$ROOT/work/ctwpro-rootless-5.6.0"
AUDIT="$CASE/audit-deep"
BUILD="$CASE/build-deep"
BUILDROOT="$BUILD/root"
PARTS="$BUILD/parts"
VERIFY="$CASE/verify-final-5.6.0-2"
FINAL_AUDIT="$CASE/final-audit-5.6.0-2"
PATCH_SOURCE="$CASE/patch-src/CTWProDeepPatch.m"
ENTITLEMENTS="$CASE/evidence/CTWPro.entitlements.plist"
SIGNED_ENTITLEMENTS="$BUILD/CTWPro.signed.entitlements.plist"
SOURCE_DEB="$ROOT/downloads/ctwpro-repo/debs/CTW_Pro(无根版)_5.6.0_com.xxdevice.CTWPro.Rootless560.deb"
SOURCE_SHA256="f10c545f65c81bc4d69afd5335c7fcd19d00ab3ca8b74d1227820996ebca54ef"
OUTPUT_NAME="CTW_Pro企业级(无根版)_5.6.0-2_com.xxdevice.CTWPro.Rootless560_deep_nolicense_ustar.deb"
OUTPUT="$ROOT/patched/$OUTPUT_NAME"
CANDIDATE="$BUILD/$OUTPUT_NAME"
PREPUBLISH_AUDIT="$BUILD/prepublish-audit"
PUBLISH_TMP="$ROOT/patched/.$OUTPUT_NAME.tmp"

trap 'rm -f "$PUBLISH_TMP"' EXIT

actual_sha256="$(shasum -a 256 "$SOURCE_DEB" | awk '{print $1}')"
if [[ "$actual_sha256" != "$SOURCE_SHA256" ]]; then
  echo "unexpected source deb SHA256: $actual_sha256" >&2
  exit 1
fi

rm -rf "$AUDIT" "$BUILD" "$VERIFY" "$FINAL_AUDIT"
python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$SOURCE_DEB" --out "$AUDIT"
mkdir -p "$BUILDROOT/DEBIAN" "$PARTS" "$VERIFY/control" \
  "$VERIFY/rootfs" "$CASE/evidence" "$ROOT/patched"

COPYFILE_DISABLE=1 gtar -xzf "$AUDIT/raw/data.tar.gz" \
  --no-same-owner --same-permissions -C "$BUILDROOT"
cp -a "$AUDIT/control/." "$BUILDROOT/DEBIAN/"

perl -0pi -e '
  $count = s/^Version: 5\.6\.0$/Version: 5.6.0-2/m;
  die "unexpected control Version field\n" unless $count == 1;
' "$BUILDROOT/DEBIAN/control"
chmod 0644 "$BUILDROOT/DEBIAN/control"
chmod 0755 "$BUILDROOT/DEBIAN/postinst" "$BUILDROOT/DEBIAN/prerm"

APP="$BUILDROOT/var/jb/Applications/CTW Pro.app"
MAIN="$APP/CTW Pro"
EXTEND="$APP/extend.bin"
FIX="$APP/fix.dylib"
ORIGINAL_MAIN="$AUDIT/rootfs/var/jb/Applications/CTW Pro.app/CTW Pro"

ldid -e "$ORIGINAL_MAIN" > "$ENTITLEMENTS"
plutil -lint "$ENTITLEMENTS"
python3 "$ROOT/scripts/patch_ctwpro_rootless_deep.py" patch "$MAIN" "$MAIN"
rm -f "$EXTEND"

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

codesign --force --sign - --timestamp=none \
  --identifier com.xxdevice.CTWPro \
  --entitlements "$ENTITLEMENTS" "$APP"
codesign --verify --deep --strict "$APP"
python3 "$ROOT/scripts/patch_ctwpro_rootless_deep.py" verify "$MAIN"

ldid -e "$MAIN" > "$SIGNED_ENTITLEMENTS"
python3 - "$ENTITLEMENTS" "$SIGNED_ENTITLEMENTS" <<'PY'
import plistlib
import sys
from pathlib import Path

original = plistlib.loads(Path(sys.argv[1]).read_bytes())
signed = plistlib.loads(Path(sys.argv[2]).read_bytes())
if original != signed:
    raise SystemExit("signed CTW Pro entitlements differ from the original")
print(f"entitlements verified: {len(original)} keys")
PY

if otool -L "$MAIN" | rg -q '@executable_path/extend\.bin'; then
  echo "extend.bin load remains in the patched executable" >&2
  exit 1
fi
if ! otool -l "$MAIN" | rg -A6 -B4 '@executable_path/fix\.dylib' \
  | rg -q 'LC_LOAD_DYLIB'; then
  echo "strong fix.dylib load command is missing" >&2
  exit 1
fi
if ! otool -D "$FIX" | rg -q '^@executable_path/fix\.dylib$'; then
  echo "fix.dylib install name is incorrect" >&2
  exit 1
fi
if [[ -e "$EXTEND" ]]; then
  echo "extend.bin remains in the patched app" >&2
  exit 1
fi
if ! rg -q 'fix\.dylib' "$APP/_CodeSignature/CodeResources"; then
  echo "fix.dylib is missing from CodeResources" >&2
  exit 1
fi
if rg -q 'extend\.bin' "$APP/_CodeSignature/CodeResources"; then
  echo "extend.bin remains in CodeResources" >&2
  exit 1
fi
python3 - "$FIX" <<'PY'
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
for marker in (
    "CTWProDeepPatchLocalAuthorization",
    "测试权限:永久",
    "网络节点已就绪",
):
    encodings = (marker.encode("utf-8"), marker.encode("utf-16le"))
    if not any(encoded in data for encoded in encodings):
        raise SystemExit(f"fix.dylib marker is missing: {marker}")
print("fix.dylib runtime markers verified")
PY

printf '2.0\n' > "$PARTS/debian-binary"
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' --no-xattrs \
  -cf "$PARTS/control.tar" -C "$BUILDROOT/DEBIAN" .
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' --no-xattrs \
  -cf "$PARTS/data.tar" -C "$BUILDROOT" var
gzip -n -9 -c "$PARTS/control.tar" > "$PARTS/control.tar.gz"
gzip -n -9 -c "$PARTS/data.tar" > "$PARTS/data.tar.gz"

python3 "$ROOT/scripts/build_deb_ar.py" "$CANDIDATE" \
  "$PARTS/debian-binary" "$PARTS/control.tar.gz" "$PARTS/data.tar.gz"
python3 - "$ROOT" "$CANDIDATE" "$BUILD/archive-check" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from scripts.build_pages_repo import validate_deb_archive

validate_deb_archive(Path(sys.argv[2]), Path(sys.argv[3]))
PY

(cd "$VERIFY" && ar -x "$CANDIDATE")
test "$(cat "$VERIFY/debian-binary")" = "2.0"
gtar -xzf "$VERIFY/control.tar.gz" -C "$VERIFY/control"
gtar -xzf "$VERIFY/data.tar.gz" --same-permissions -C "$VERIFY/rootfs"

VERIFY_APP="$VERIFY/rootfs/var/jb/Applications/CTW Pro.app"
VERIFY_MAIN="$VERIFY_APP/CTW Pro"
VERIFY_FIX="$VERIFY_APP/fix.dylib"
python3 "$ROOT/scripts/patch_ctwpro_rootless_deep.py" verify "$VERIFY_MAIN"
codesign --verify --strict "$VERIFY_FIX"
codesign --verify --deep --strict "$VERIFY_APP"
test ! -e "$VERIFY_APP/extend.bin"
test -f "$VERIFY_FIX"
if ! rg -q 'fix\.dylib' "$VERIFY_APP/_CodeSignature/CodeResources"; then
  echo "fix.dylib is missing from repacked CodeResources" >&2
  exit 1
fi
if rg -q 'extend\.bin' "$VERIFY_APP/_CodeSignature/CodeResources"; then
  echo "extend.bin remains in repacked CodeResources" >&2
  exit 1
fi

grep -qx 'Package: com.xxdevice.CTWPro.Rootless560' "$VERIFY/control/control"
grep -qx 'Version: 5.6.0-2' "$VERIFY/control/control"
grep -qx 'Architecture: iphoneos-arm64' "$VERIFY/control/control"
test "$(stat -f '%OLp' "$VERIFY/control/control")" = "644"
test "$(stat -f '%OLp' "$VERIFY/control/postinst")" = "755"
test "$(stat -f '%OLp' "$VERIFY/control/prerm")" = "755"
test "$(stat -f '%OLp' "$VERIFY_MAIN")" = "755"
test "$(stat -f '%OLp' "$VERIFY_FIX")" = "755"
test "$(stat -f '%OLp' "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/0CTW.dylib")" = "766"
test "$(stat -f '%OLp' "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/ctwsup.dylib")" = "766"
test "$(stat -f '%OLp' "$VERIFY/rootfs/var/jb/usr/bin/ctwsrv")" = "766"

python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$CANDIDATE" --out "$PREPUBLISH_AUDIT"
cp "$CANDIDATE" "$PUBLISH_TMP"
mv -f "$PUBLISH_TMP" "$OUTPUT"
python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$OUTPUT" --out "$FINAL_AUDIT"
shasum -a 256 "$OUTPUT"
stat -f 'size=%z bytes' "$OUTPUT"
