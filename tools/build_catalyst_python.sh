#!/bin/bash
# Builds CPython for Mac Catalyst (arm64-apple-ios-macabi) and adds an ios-arm64-maccatalyst slice
# to dist/ios/Python.xcframework. Run after the iOS slices exist.
#
#   tools/build_catalyst_python.sh [path/to/Python-3.13.x source] [path/to/openssl-3.x source]
#
# A Catalyst binary runs on the Mac, so this is a native (not cross) build: macOS SDK + `-target ...-macabi`.
# ffi, bz2, zlib, sqlite3 and expat come from the macOS SDK (it ships Catalyst stubs). The SDK has no OpenSSL,
# so it is built here as static libraries and linked into _ssl and _hashlib (same version as the iOS slices).
# Get the source from https://github.com/openssl/openssl/releases (check the .sha256). No xz yet, so `lzma` is
# missing from this slice.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$REPO/.cache/Python-3.13.7}"
OPENSSL_SRC="${2:-$REPO/.cache/openssl-3.5.9}"
BUILD="$SRC/cross-build/arm64-apple-ios-macabi"
OPENSSL="$BUILD/openssl"
XC="$REPO/dist/ios/Python.xcframework"
SLICE="$XC/ios-arm64-maccatalyst"
TARGET="arm64-apple-ios15.0-macabi"
SDK="$(xcrun --sdk macosx --show-sdk-path)"

[ -f "$OPENSSL_SRC/Configure" ] || { echo "no OpenSSL source at $OPENSSL_SRC" >&2; exit 1; }
mkdir -p "$BUILD"
export MACOSX_DEPLOYMENT_TARGET=11.0

# OpenSSL, static, built out of tree. Its default CA paths (under /usr/local/ssl) do not exist on a Mac; the runtime
# points SSL_CERT_FILE at the system bundle (pyxpo._internal.apple).
if [ ! -f "$OPENSSL/lib/libssl.a" ]; then
  rm -rf "$BUILD/openssl-build"
  mkdir -p "$BUILD/openssl-build"
  (cd "$BUILD/openssl-build" &&
    CFLAGS="-O3 -target $TARGET -isysroot $SDK" LDFLAGS="-target $TARGET -isysroot $SDK" \
      "$OPENSSL_SRC/Configure" darwin64-arm64-cc no-shared no-tests no-module no-engine \
      --prefix="$OPENSSL" --libdir=lib >/dev/null &&
    make -j"$(sysctl -n hw.ncpu)" build_libs >/dev/null &&
    make install_dev >/dev/null)
fi

cd "$BUILD"
# Catalyst marks these unavailable: system(), clock_settime(), and SystemConfiguration proxies (_scproxy).
CC=clang CFLAGS="-target $TARGET -isysroot $SDK" LDFLAGS="-target $TARGET -isysroot $SDK" \
  ac_cv_func_system=no ac_cv_func_clock_settime=no py_cv_module__scproxy=n/a \
  "$SRC/configure" --enable-shared --prefix="$BUILD/install" --without-ensurepip --disable-test-modules -q \
  --with-openssl="$OPENSSL"
make -j"$(sysctl -n hw.ncpu)"
make install >/dev/null

INST="$BUILD/install"
rm -rf "$SLICE"
FW="$SLICE/Python.framework"
mkdir -p "$FW/Versions/A/Resources" "$SLICE/lib"
cp "$INST/lib/libpython3.13.dylib" "$FW/Versions/A/Python"
install_name_tool -id @rpath/Python.framework/Versions/A/Python "$FW/Versions/A/Python"
cp -R "$INST/include/python3.13" "$FW/Versions/A/Headers"
cat > "$FW/Versions/A/Resources/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleExecutable</key><string>Python</string>
	<key>CFBundleIdentifier</key><string>org.python.python</string>
	<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
	<key>CFBundleName</key><string>Python</string>
	<key>CFBundlePackageType</key><string>FMWK</string>
	<key>CFBundleShortVersionString</key><string>3.13</string>
	<key>CFBundleVersion</key><string>3.13</string>
</dict>
</plist>
EOF
ln -s A "$FW/Versions/Current"
ln -s Versions/Current/Python "$FW/Python"
ln -s Versions/Current/Headers "$FW/Headers"
ln -s Versions/Current/Resources "$FW/Resources"
# Stdlib without the Mac-only extras; lib-dynload holds the Catalyst extension modules.
rsync -a --exclude test --exclude idlelib --exclude tkinter --exclude turtledemo --exclude __pycache__ \
  "$INST/lib/python3.13" "$SLICE/lib/"
# Extension modules link libpython with -undefined dynamic_lookup, so they need no install-name fix.
for m in _ssl _hashlib; do
  ls "$SLICE/lib/python3.13/lib-dynload/$m".*.so >/dev/null 2>&1 || { echo "$m was not built" >&2; exit 1; }
done

# Register the slice in the xcframework Info.plist (idempotent).
PL="$XC/Info.plist"
if ! /usr/libexec/PlistBuddy -c "Print" "$PL" | grep -q "ios-arm64-maccatalyst"; then
  N=$(/usr/libexec/PlistBuddy -c "Print :AvailableLibraries" "$PL" | grep -c "LibraryIdentifier")
  /usr/libexec/PlistBuddy \
    -c "Add :AvailableLibraries:$N dict" \
    -c "Add :AvailableLibraries:$N:LibraryIdentifier string ios-arm64-maccatalyst" \
    -c "Add :AvailableLibraries:$N:LibraryPath string Python.framework" \
    -c "Add :AvailableLibraries:$N:SupportedArchitectures array" \
    -c "Add :AvailableLibraries:$N:SupportedArchitectures:0 string arm64" \
    -c "Add :AvailableLibraries:$N:SupportedPlatform string ios" \
    -c "Add :AvailableLibraries:$N:SupportedPlatformVariant string maccatalyst" \
    "$PL"
fi
echo "catalyst slice: $SLICE"
