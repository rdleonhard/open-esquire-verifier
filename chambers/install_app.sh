#!/bin/bash
# Build "Open Esquire Chambers.app" and install it to ~/Applications.
# Rerunnable; the bundle just execs chambers/app.py from this checkout.
set -euo pipefail
cd "$(dirname "$0")"

PY="$(command -v python3)"
APP="$HOME/Applications/Open Esquire Chambers.app"
CHAMBERS="$(pwd)"

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Open Esquire Chambers</string>
  <key>CFBundleDisplayName</key><string>Open Esquire Chambers</string>
  <key>CFBundleIdentifier</key><string>com.openesquire.chambers</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>chambers</string>
  <key>CFBundleIconFile</key><string>chambers</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
</dict>
</plist>
EOF

cat > "$APP/Contents/MacOS/chambers" <<EOF
#!/bin/bash
exec "$PY" "$CHAMBERS/app.py"
EOF
chmod +x "$APP/Contents/MacOS/chambers"

# icon: gold diamond seal on near-black, matching the letterhead
"$PY" make_icon.py "$APP/Contents/Resources/chambers.icns"

# refresh LaunchServices so Finder picks up the (re)built bundle
touch "$APP"
echo "installed: $APP"
