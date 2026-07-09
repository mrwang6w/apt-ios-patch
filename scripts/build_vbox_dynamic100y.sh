#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/work/vbox-5.5-dynamic100y"
DEB_ROOT="$ROOT/work/vbox-5.5-patched/deb-root"
ORIGINAL_VBOX="$ROOT/work/vbox-5.5-audit/rootfs/var/jb/Applications/VBox.app/VBox"
PATCHED_APP="$DEB_ROOT/var/jb/Applications/VBox.app"
PATCHED_VBOX="$DEB_ROOT/var/jb/Applications/VBox.app/VBox"
ENTITLEMENTS="$ROOT/work/vbox-5.5-patched/VBox.entitlements.plist"
OUTPUT_NAME="VBox_5.5_rootless_5.5-3_com.amg456.VBox1_nolicense_dynamic100y_ustar.deb"
PUBLISHED_NAME="VBox_5.5「无根」_5.5-3_com.amg456.VBox1_nolicense_dynamic100y_ustar.deb"

if ! grep -qx 'Version: 5.5-3' "$DEB_ROOT/DEBIAN/control"; then
  echo "unexpected VBox control version" >&2
  exit 1
fi

python3 "$ROOT/scripts/patch_vbox_dynamic_expiry.py" "$ORIGINAL_VBOX" "$PATCHED_VBOX"
codesign --force --sign - --timestamp=none --identifier com.google.vbox \
  --entitlements "$ENTITLEMENTS" "$PATCHED_APP"
codesign -v --strict "$PATCHED_APP"

rm -rf "$WORK/package" "$WORK/verify"
mkdir -p "$WORK/package" "$WORK/verify"
printf '2.0\n' > "$WORK/package/debian-binary"

COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' \
  -cf "$WORK/package/control.tar" -C "$DEB_ROOT/DEBIAN" .
COPYFILE_DISABLE=1 gtar --format=ustar --sort=name --numeric-owner \
  --owner=0 --group=0 --mtime='@0' \
  -cf "$WORK/package/data.tar" -C "$DEB_ROOT" var
gzip -n -9 -c "$WORK/package/control.tar" > "$WORK/package/control.tar.gz"
gzip -n -9 -c "$WORK/package/data.tar" > "$WORK/package/data.tar.gz"

python3 "$ROOT/scripts/build_deb_ar.py" "$WORK/$OUTPUT_NAME" \
  "$WORK/package/debian-binary" \
  "$WORK/package/control.tar.gz" \
  "$WORK/package/data.tar.gz"
python3 - "$ROOT" "$WORK/$OUTPUT_NAME" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from scripts.build_pages_repo import validate_deb_archive

validate_deb_archive(Path(sys.argv[2]), root / "work/vbox-5.5-dynamic100y/verify")
PY

cp "$WORK/$OUTPUT_NAME" "$ROOT/patched/$PUBLISHED_NAME"
for dir in \
  "$ROOT/work/vbox-5.5-patched/deb-stage" \
  "$ROOT/work/vbox-5.5-patched/archive-validator" \
  "$ROOT/work/vbox-5.5-patched/final-verify"; do
  cp "$WORK/package/debian-binary" "$WORK/package/control.tar.gz" \
    "$WORK/package/data.tar.gz" "$dir/"
done
gtar -xzf "$WORK/package/control.tar.gz" \
  -C "$ROOT/work/vbox-5.5-patched/deb-stage/control" --strip-components=1
gtar -xzf "$WORK/package/data.tar.gz" \
  -C "$ROOT/work/vbox-5.5-patched/final-verify"
shasum -a 256 "$WORK/$OUTPUT_NAME" "$ROOT/patched/$PUBLISHED_NAME"
rm -rf "$WORK/package" "$WORK/verify"
