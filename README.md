# Quest Recorder

a small desktop app that pulls meta quest recordings onto your pc over `adb`.

it doesn't access the headset's raw camera/lens feed. It uses the same flat spectator view as the built-in **Record Video** feature (Meta + Trigger), just with a bit more control over quality and without having to manually copy files around.

## What it does

sets fps, resolution, bitrate, and aspect ratio before you record
watches the headset's recordings folder and automatically copies new videos to your PC
can optionally delete recordings from the headset after they've been copied

recording still has to be started and stopped from the headset. Meta removed the ability to trigger recordings remotely, so use **Meta + Trigger** to start recording, then do it again to stop.

## Requirements

Python 3 with Tkinter (`python3-tk` on debian/ubuntu, `tk` on arch, `python3-tkinter` on fedora)
`adb` on your `PATH`
a quest headset in dev dode connected over usb or adb over wifi (recommended)

## Setup

```bash
git clone https://github.com/steIIaa/quest-recorder/
cd quest-recorder
./install.sh
```

this adds **Quest Recorder** to your app launcher using whatever directory you cloned it into.

or just run it directly:

```bash
python3 quest_recorder.py
```

## Building

you don't need to do this unless you want to share the app with someone who doesn't have Python installed.

```bash
./build-binary.sh     # dist/QuestRecorder
./build-appimage.sh   # Quest_Recorder-x86_64.AppImage
```

## Notes

aspect ratio and fps settings depend on the headset's capture pipeline, so newer horizon OS versions might ignore some of them.
if your recordings aren't stored in `/sdcard/Oculus/VideoShots`, change `REMOTE_VIDEO_DIR` at the top of `quest_recorder.py`.
