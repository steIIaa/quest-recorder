#!/usr/bin/env bash
# build-appimage.sh
# wraps the standalone binary (run build-binary.sh first) into an AppImage -
# a single double-clickable file that runs on pretty much any linux distro,
# no install step needed at all for whoever's running it.

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [ ! -f "dist/QuestRecorder" ]; then
    echo "dist/QuestRecorder not found - run ./build-binary.sh first"
    exit 1
fi

APPDIR="QuestRecorder.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"

cp dist/QuestRecorder "$APPDIR/usr/bin/"
cp quest-record-icon.png "$APPDIR/quest-recorder.png"

cat > "$APPDIR/quest-recorder.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Quest Recorder
Comment=Grab Quest gameplay recordings over adb
Exec=QuestRecorder
Icon=quest-recorder
Terminal=false
Categories=Utility;AudioVideo;
EOF

cat > "$APPDIR/AppRun" << 'EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/QuestRecorder" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# grab appimagetool if it's not already sitting around
if [ ! -f appimagetool.AppImage ]; then
    echo "downloading appimagetool..."
    wget -q -O appimagetool.AppImage \
        https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool.AppImage
fi

./appimagetool.AppImage "$APPDIR"

echo ""
echo "done - you should have a Quest_Recorder-x86_64.AppImage sitting here now"
echo "chmod +x it and double click to run, no install needed"
