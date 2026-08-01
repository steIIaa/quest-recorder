#!/usr/bin/env bash
# build-binary.sh
# bundles quest_recorder.py + a python interpreter + tkinter into one
# standalone executable, so nobody running it needs python installed.
# output ends up at dist/QuestRecorder

set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if ! python3 -m pyinstaller --version >/dev/null 2>&1; then
    echo "pyinstaller not found, installing it..."
    pip install --user pyinstaller
fi

python3 -m PyInstaller \
    --onefile \
    --windowed \
    --name QuestRecorder \
    --add-data "quest-record-icon.png:." \
    quest_recorder.py

echo ""
echo "done - built binary at dist/QuestRecorder"
echo "you can hand that single file to people, they don't need python installed"
