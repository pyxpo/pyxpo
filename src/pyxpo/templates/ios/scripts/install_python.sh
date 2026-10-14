#!/bin/bash
# Build phase: copy the Python stdlib, app and site-packages into the app bundle, then wrap
# native extension modules as frameworks and sign them. Runs before the final bundle signing.
set -euo pipefail

STAGE="$PROJECT_DIR/stage"
DEST="$CODESIGNING_FOLDER_PATH"
case "$PLATFORM_NAME" in
  iphonesimulator) SLICE=simulator ;;
  *) SLICE=device ;;
esac

mkdir -p "$DEST/python" "$DEST/app_root" "$DEST/app_packages"
rsync -a --delete "$STAGE/python-$SLICE/" "$DEST/python/"
rsync -a --delete "$STAGE/app_root/" "$DEST/app_root/"
rsync -a --delete "$STAGE/site-$SLICE/" "$DEST/app_packages/"

SIGN="${EXPANDED_CODE_SIGN_IDENTITY:--}"
/usr/bin/python3 "$PROJECT_DIR/scripts/ios_wrap.py" \
  --bundle "$DEST" --bundle-id "$PRODUCT_BUNDLE_IDENTIFIER" --template "$PROJECT_DIR/App/dylib-Info-template.plist" \
  --sdk "$PLATFORM_NAME" --sign "$SIGN"
