#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CASE="$ROOT/work/awz-rootful-15.0.1"
AUDIT="$CASE/audit"
BUILD="$CASE/build"
BUILDROOT="$BUILD/root"
PARTS="$BUILD/parts"
VERIFY="$CASE/verify-final-15.0.1-1"
FINAL_AUDIT="$CASE/final-audit-15.0.1-1"
ENTITLEMENTS="$CASE/evidence/AWZ.entitlements.plist"
SOURCE_DEB="$ROOT/downloads/amg456-repo/debs/AWZ爱伪装_修复(有根)_15.0.1_app.awz4854.rootful.deb"
SOURCE_SHA256="ef6fdc13cddb733b48688b76e7ac0dff2e4ccc8db70e429856d23cf11b6bad0b"
OUTPUT_NAME="AWZ爱伪装_修复(有根)_15.0.1-1_app.awz4854.rootful_nolicense_ustar.deb"
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
mkdir -p "$BUILDROOT/DEBIAN" "$PARTS" "$VERIFY/control" "$VERIFY/rootfs" \
  "$CASE/evidence" "$ROOT/patched"
cp -a "$AUDIT/rootfs/." "$BUILDROOT/"
cp -a "$AUDIT/control/." "$BUILDROOT/DEBIAN/"

perl -0pi -e '
  $count = s/^Version: 15\.0\.1$/Version: 15.0.1-1/m;
  die "unexpected control Version field\n" unless $count == 1;
' "$BUILDROOT/DEBIAN/control"
perl -0pi -e '
  $count = s{\nif \[ -f "/usr/bin/aloader" \]; then\n[ \t]+/usr/bin/aloader\nfi\n}{\n# The patched app is complete; do not reinstall the injected card-license layer.\n};
  die "unexpected aloader maintainer-script block\n" unless $count == 1;
' "$BUILDROOT/DEBIAN/extrainst_"

chmod 0644 "$BUILDROOT/DEBIAN/control" "$BUILDROOT/DEBIAN/icon.png"
chmod 0755 "$BUILDROOT/DEBIAN/extrainst_" "$BUILDROOT/DEBIAN/prerm"
if rg -q '/usr/bin/aloader' "$BUILDROOT/DEBIAN/extrainst_"; then
  echo "aloader invocation remains in extrainst_" >&2
  exit 1
fi

APP="$BUILDROOT/Applications/AWZ.app"
python3 "$ROOT/scripts/patch_awz_nolicense.py" patch "$APP/AWZZ" "$APP/AWZ"
rm -f "$APP/mapsdk.bundle"

codesign -d --arch armv7 --xml --entitlements - \
  "$AUDIT/rootfs/Applications/AWZ.app/AWZ" > "$BUILD/AWZ.armv7.entitlements.plist"
codesign -d --arch arm64 --xml --entitlements - \
  "$AUDIT/rootfs/Applications/AWZ.app/AWZ" > "$BUILD/AWZ.arm64.entitlements.plist"
python3 - "$BUILD/AWZ.armv7.entitlements.plist" \
  "$BUILD/AWZ.arm64.entitlements.plist" "$ENTITLEMENTS" <<'PY'
import plistlib
import sys
from pathlib import Path


def load_ldid_entitlements(path: Path) -> dict[str, object]:
    data = path.read_bytes().strip()
    if data.count(b"<plist") != 1 or not data.endswith(b"</plist>"):
        raise SystemExit(f"unexpected ldid entitlement output: {path}")
    if data.startswith(b"<!DOCTYPE"):
        data = b'<?xml version="1.0" encoding="UTF-8"?>\n' + data
    return plistlib.loads(data)


armv7 = load_ldid_entitlements(Path(sys.argv[1]))
arm64 = load_ldid_entitlements(Path(sys.argv[2]))
if armv7 != arm64:
    raise SystemExit("armv7 and arm64 entitlements differ")
if len(arm64) != 12:
    raise SystemExit(f"unexpected entitlement key count: {len(arm64)}")
Path(sys.argv[3]).write_bytes(Path(sys.argv[2]).read_bytes())
PY
plutil -lint "$ENTITLEMENTS"
codesign --force --sign - --timestamp=none --identifier AWZ \
  --entitlements "$ENTITLEMENTS" "$APP"
codesign --verify --deep --strict "$APP"
python3 "$ROOT/scripts/patch_awz_nolicense.py" verify "$APP/AWZ"
if otool -L "$APP/AWZ" | rg -q 'mapsdk\.bundle|OOXXPlay'; then
  echo "card-license dylib is still loaded by the patched executable" >&2
  exit 1
fi
if [[ -e "$APP/mapsdk.bundle" ]]; then
  echo "mapsdk.bundle remains in the patched app" >&2
  exit 1
fi
if rg -q 'mapsdk\.bundle' "$APP/_CodeSignature/CodeResources"; then
  echo "mapsdk.bundle remains in CodeResources" >&2
  exit 1
fi

printf '2.0\n' > "$PARTS/debian-binary"
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' --no-xattrs \
  -cf "$PARTS/control.tar" -C "$BUILDROOT/DEBIAN" .
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' --no-xattrs \
  -cf "$PARTS/data.tar" -C "$BUILDROOT" Applications Library usr
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
gtar -xzf "$VERIFY/data.tar.gz" -C "$VERIFY/rootfs"
python3 "$ROOT/scripts/patch_awz_nolicense.py" verify \
  "$VERIFY/rootfs/Applications/AWZ.app/AWZ"
codesign --verify --deep --strict "$VERIFY/rootfs/Applications/AWZ.app"
test ! -e "$VERIFY/rootfs/Applications/AWZ.app/mapsdk.bundle"
if rg -q 'mapsdk\.bundle' "$VERIFY/rootfs/Applications/AWZ.app/_CodeSignature/CodeResources"; then
  echo "mapsdk.bundle remains in the repacked CodeResources" >&2
  exit 1
fi
grep -qx 'Package: app.awz4854.rootful' "$VERIFY/control/control"
grep -qx 'Version: 15.0.1-1' "$VERIFY/control/control"
grep -qx 'Architecture: iphoneos-arm' "$VERIFY/control/control"
grep -qx 'Conflicts: app.awzios6.awz' "$VERIFY/control/control"
if rg -q '/usr/bin/aloader' "$VERIFY/control/extrainst_"; then
  echo "aloader invocation remains in the repacked extrainst_" >&2
  exit 1
fi
test "$(stat -f '%OLp' "$VERIFY/control/extrainst_")" = "755"
test "$(stat -f '%OLp' "$VERIFY/control/prerm")" = "755"

python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$CANDIDATE" --out "$PREPUBLISH_AUDIT"
cp "$CANDIDATE" "$PUBLISH_TMP"
mv -f "$PUBLISH_TMP" "$OUTPUT"
python3 "$ROOT/skills/ios-deb-reverse-patcher/scripts/deb_audit.py" \
  "$OUTPUT" --out "$FINAL_AUDIT"
shasum -a 256 "$OUTPUT"
stat -f 'size=%z bytes' "$OUTPUT"
