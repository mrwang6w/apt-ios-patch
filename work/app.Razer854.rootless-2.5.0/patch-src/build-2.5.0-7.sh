#!/bin/zsh
set -euo pipefail

ROOT="/Users/zest/myworks/apt-ios-patch"
WORK="$ROOT/work/app.Razer854.rootless-2.5.0"
PKGROOT="$WORK/pkgroot-2.5.0-7-build6"
REPACK="$WORK/repack-2.5.0-7-build6"
VERIFY="$WORK/verify-final-2.5.0-7-build6"
OUT="$ROOT/patched/2.5.0_Razer雷蛇(无根)_2.5.0-7_app.Razer854.rootless_authstate_no-ui-swizzle.deb"
HOOK_SRC="$WORK/patch-src/RazerAuth2099Hook.m"
HOOK="$WORK/patch-src/RazerAuth2099.dylib.v7"
SDK="$(xcrun --sdk iphoneos --show-sdk-path)"

test ! -e "$PKGROOT"
test ! -e "$REPACK"
test ! -e "$VERIFY"
test ! -e "$OUT"

xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=12.0 \
  -dynamiclib -fobjc-arc -fblocks -O2 -Wall -Wextra \
  -framework Foundation -framework CoreFoundation -lobjc \
  -install_name /var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib \
  -o "$HOOK" "$HOOK_SRC"
codesign -s - --force "$HOOK"

cp -a "$WORK/final-audit-2.5.0-6/rootfs" "$PKGROOT"
mkdir -p "$PKGROOT/DEBIAN"
cp -a "$WORK/final-audit-2.5.0-6/control/." "$PKGROOT/DEBIAN/"
cp "$HOOK" "$PKGROOT/var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib"
sed -i '' 's/^Version: .*/Version: 2.5.0-7/' "$PKGROOT/DEBIAN/control"

# Restore the original VM trampoline prologues. v6's four RET patches suppress
# authorization UI but cannot make the protected action succeed.
RAZER="$PKGROOT/var/jb/Applications/razer.app/Razer"
for off in 0x3d2018 0x3d2fe0 0xd97694 0xd9b8c0; do
  printf '\xff\x03\x10\xd1' | dd of="$RAZER" bs=1 seek=$((off)) conv=notrunc status=none
done

codesign -s - --force --entitlements "$WORK/evidence/razer-app.entitlements.plist" "$PKGROOT/var/jb/Applications/razer.app"
codesign --verify --deep --strict "$PKGROOT/var/jb/Applications/razer.app"
codesign --verify --strict "$PKGROOT/var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib"

mkdir -p "$REPACK"
cp "$WORK/final-audit-2.5.0-6/raw/debian-binary" "$REPACK/debian-binary"
tar -C "$PKGROOT/DEBIAN" -czf "$REPACK/control.tar.gz" .
tar -C "$PKGROOT" --exclude='./DEBIAN' -czf "$REPACK/data.tar.gz" ./var
python3 "$WORK/patch-src/pack_deb.py" "$OUT" "$REPACK/debian-binary" "$REPACK/control.tar.gz" "$REPACK/data.tar.gz"

mkdir -p "$VERIFY/parts" "$VERIFY/control" "$VERIFY/rootfs"
cp "$OUT" "$VERIFY/final.deb"
(cd "$VERIFY/parts" && ar -x ../final.deb)
tar -C "$VERIFY/control" -xzf "$VERIFY/parts/control.tar.gz"
tar -C "$VERIFY/rootfs" -xzf "$VERIFY/parts/data.tar.gz"
codesign --verify --deep --strict "$VERIFY/rootfs/var/jb/Applications/razer.app"
codesign --verify --strict "$VERIFY/rootfs/var/jb/Library/MobileSubstrate/DynamicLibraries/RazerAuth2099.dylib"
