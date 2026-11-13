#!/bin/bash
# Bouwt en ondertekent het prototype ad hoc; levert dist/Huurklaar\ Meldingen.app
set -euo pipefail
cd "$(dirname "$0")"
rm -rf build dist
../.venv/bin/pyinstaller --windowed --noconfirm --name "Huurklaar Meldingen" \
  --osx-bundle-identifier be.huurklaar.meldingen.proto \
  --hidden-import objc --hidden-import UserNotifications proto.py >/dev/null 2>&1
PLIST="dist/Huurklaar Meldingen.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST"
codesign --force --deep -s - "dist/Huurklaar Meldingen.app"
codesign -dv "dist/Huurklaar Meldingen.app" 2>&1 | grep -E "Identifier|Signature"
