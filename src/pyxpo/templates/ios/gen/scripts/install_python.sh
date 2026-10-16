#!/bin/bash
# Build phase: copy the Python stdlib, app and site-packages into the app bundle, then wrap
# native extension modules as frameworks and sign them. Runs before the final bundle signing.
set -euo pipefail

STAGE="$PROJECT_DIR/pyxpo-gen/stage"
DEST="$CODESIGNING_FOLDER_PATH"
case "$PLATFORM_NAME" in
  iphonesimulator) SLICE=simulator ;;
  macosx) SLICE=catalyst; DEST="$CODESIGNING_FOLDER_PATH/Contents/Resources" ;;  # Mac Catalyst desktop app
  *) SLICE=device ;;
esac

mkdir -p "$DEST/python" "$DEST/app_root" "$DEST/app_packages"
rsync -a --delete "$STAGE/python-$SLICE/" "$DEST/python/"
rsync -a --delete "$STAGE/app_root/" "$DEST/app_root/"
rsync -a --delete "$STAGE/site-$SLICE/" "$DEST/app_packages/"

SIGN="${EXPANDED_CODE_SIGN_IDENTITY:--}"
if [ "$SLICE" = catalyst ]; then
  # macOS loads extension modules from anywhere in the bundle: sign them in place, no framework wrapping.
  find "$DEST/python" "$DEST/app_packages" \( -name '*.so' -o -name '*.dylib' \) -print0 |
    xargs -0 -r /usr/bin/codesign --force --sign "$SIGN" --timestamp=none
  exit 0
fi
/usr/bin/python3 "$PROJECT_DIR/pyxpo-gen/scripts/ios_wrap.py" \
  --bundle "$DEST" --bundle-id "$PRODUCT_BUNDLE_IDENTIFIER" --template "$PROJECT_DIR/pyxpo-gen/scripts/dylib-Info-template.plist" \
  --sdk "$PLATFORM_NAME" --sign "$SIGN"
