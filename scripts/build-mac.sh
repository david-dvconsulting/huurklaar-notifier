#!/bin/bash
# Bouwt "Huurklaar Meldingen.app" (Python ingebouwd), ondertekent ze ad hoc en maakt een .dmg.
# Lokaal en in de releaseworkflow (.github/workflows/release.yml). Gebruik: scripts/build-mac.sh [versie]
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="Huurklaar Meldingen"
BUNDLE_ID="be.huurklaar.meldingen"
VERSION="${1:-$(.venv/bin/python -c 'import huurklaar_notifier as h; print(h.__version__)')}"
APP="dist/$NAME.app"

rm -rf build dist
.venv/bin/python scripts/make-icons.py
.venv/bin/pyinstaller --noconfirm --windowed --name "$NAME" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --icon assets/AppIcon.icns \
  --add-data "assets:assets" \
  --collect-submodules keyring.backends \
  --hidden-import objc --hidden-import UserNotifications --hidden-import AppKit --hidden-import Foundation \
  --paths src \
  scripts/entry.py >/dev/null

PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST"   # geen Dock-icoon, enkel menubalk
for key in CFBundleShortVersionString CFBundleVersion; do
  /usr/libexec/PlistBuddy -c "Set :$key $VERSION" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :$key string $VERSION" "$PLIST"
done

# Ad hoc ('-') is gratis en nodig op Apple Silicon; er is geen Apple Developer-account.
codesign --force --deep -s - "$APP"
codesign --verify --deep --strict "$APP"

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "$NAME" -srcfolder "$STAGE" -ov -format UDZO "dist/Huurklaar-Meldingen-$VERSION.dmg"
rm -rf "$STAGE"
echo "Klaar: $APP en dist/Huurklaar-Meldingen-$VERSION.dmg"
