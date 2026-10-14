#!/bin/bash
# Build phase: copy the Python stdlib, app and site-packages into the app bundle, then wrap
# native extension modules as frameworks and sign them. Runs before the final bundle signing.
set -euo pipefail

STAGE="$PROJECT_DIR/pyxpo-gen/stage"
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
/usr/bin/python3 "$PROJECT_DIR/pyxpo-gen/scripts/ios_wrap.py" \
  --bundle "$DEST" --bundle-id "$PRODUCT_BUNDLE_IDENTIFIER" --template "$PROJECT_DIR/pyxpo-gen/scripts/dylib-Info-template.plist" \
  --sdk "$PLATFORM_NAME" --sign "$SIGN"

# Usage-description keys the linked native modules need. Keys already in the app's Info.plist win.
if [ -f "$PROJECT_DIR/pyxpo-gen/ModulesInfo.plist" ]; then
  /usr/bin/python3 - "$PROJECT_DIR/pyxpo-gen/ModulesInfo.plist" "$DEST/Info.plist" <<'PY'
import plistlib, sys
with open(sys.argv[1], "rb") as f:
    extra = plistlib.load(f)
with open(sys.argv[2], "rb") as f:
    info = plistlib.load(f)
missing = {k: v for k, v in extra.items() if k not in info}
if missing:
    info.update(missing)
    with open(sys.argv[2], "wb") as f:
        plistlib.dump(info, f)
PY
fi
