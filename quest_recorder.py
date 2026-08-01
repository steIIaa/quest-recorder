#!/usr/bin/env python3

# quest_recorder.py
#
# grabs gameplay recordings off a quest over adb. you still have to actually
# start/stop the recording in the headset yourself (meta button + trigger,
# same as the normal "Record Video" thing) - there used to be a way to
# trigger that over adb too but meta patched it out at some point.
#
# what this actually does:
#   - pushes fps/resolution/bitrate to the headset before you hit record
#   - watches the video folder on the headset, grabs new files automatically
#   - optionally deletes them off the headset once they're safely copied

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

# when this is running as a bundled pyinstaller binary, __file__ points into
# a temp extraction folder instead of wherever the actual exe lives, so we
# need two different "here"s: one for bundled resources (icon), one for
# stuff that should live next to the actual binary (recordings, the .desktop
# Exec= line).
#
# AppImages add another wrinkle: sys.executable points inside the read-only
# squashfs mount (/tmp/.mount_XXXX/...), not the real file on disk, so
# writing anything there fails. AppImage runtimes set an APPIMAGE env var
# with the real path though, so use that when it's present.
if getattr(sys, 'frozen', False):
    RESOURCE_DIR = sys._MEIPASS
    IS_BINARY = True
    if os.environ.get('APPIMAGE'):
        APP_DIR = os.path.dirname(os.environ['APPIMAGE'])
        EXEC_TARGET = os.environ['APPIMAGE']
    else:
        APP_DIR = os.path.dirname(sys.executable)
        EXEC_TARGET = sys.executable
else:
    RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RESOURCE_DIR
    IS_BINARY = False
    EXEC_TARGET = None

ICON_PATH = os.path.join(RESOURCE_DIR, 'quest-record-icon.png')
SAVE_DIR = os.path.join(APP_DIR, 'recordings')

VIDEO_FOLDER = '/sdcard/Oculus/VideoShots'
BITRATE = 40_000_000  # 40mbps, works fine for me, bump it up if you want

CONFIG_DIR = os.path.expanduser('~/.config/quest-recorder')
SHORTCUT_ASKED_FILE = os.path.join(CONFIG_DIR, 'asked_shortcut')
DESKTOP_FILE = os.path.expanduser('~/.local/share/applications/quest-recorder.desktop')

ASPECTS = {
    '16:9 (standard)': (1920, 1080),
    '4:3': (1440, 1080),
    '1:1 (square)': (1080, 1080),
    '21:9 (ultrawide)': (2560, 1080),
    '9:16 (portrait)': (1080, 1920),
}

FPS_CHOICES = ['30', '60', '72', '90', '120']


def install_shortcut():
    apps_dir = os.path.expanduser('~/.local/share/applications')
    icons_dir = os.path.expanduser('~/.local/share/icons')
    os.makedirs(apps_dir, exist_ok=True)
    os.makedirs(icons_dir, exist_ok=True)

    icon_dest = os.path.join(icons_dir, 'quest-record-icon.png')
    with open(ICON_PATH, 'rb') as f_in, open(icon_dest, 'wb') as f_out:
        f_out.write(f_in.read())

    if IS_BINARY:
        exec_line = 'Exec=' + EXEC_TARGET
    else:
        exec_line = 'Exec=python3 ' + os.path.join(APP_DIR, 'quest_recorder.py')

    desktop_contents = '\n'.join([
        '[Desktop Entry]',
        'Type=Application',
        'Name=Quest Recorder',
        'Comment=Grab Quest gameplay recordings over adb',
        exec_line,
        'Icon=' + icon_dest,
        'Terminal=false',
        'Categories=Utility;AudioVideo;',
        ''
    ])

    with open(DESKTOP_FILE, 'w') as f:
        f.write(desktop_contents)
    os.chmod(DESKTOP_FILE, 0o755)

    try:
        subprocess.run(['update-desktop-database', apps_dir], capture_output=True, timeout=5)
    except Exception:
        pass  # not every distro has this, whatever


class App:
    def __init__(self, root):
        self.root = root
        self.watching = False

        root.title('Quest Recorder')
        root.geometry('540x460')
        root.resizable(False, False)

        if os.path.exists(ICON_PATH):
            # need to hang onto this reference or tkinter will garbage
            # collect it and the icon just disappears, ask me how I know
            self.icon_img = tk.PhotoImage(file=ICON_PATH)
            root.iconphoto(True, self.icon_img)

        self.build_ui()

        os.makedirs(SAVE_DIR, exist_ok=True)
        self.check_device()

        root.after(400, self.maybe_ask_about_shortcut)

    def build_ui(self):
        title = ttk.Label(self.root, text='Quest Recorder', font=('Sans', 15, 'bold'))
        title.pack(padx=10, pady=6)

        row = ttk.Frame(self.root)
        row.pack(padx=10, pady=6)

        ttk.Label(row, text='FPS:').grid(row=0, column=0, padx=4, pady=4, sticky='e')
        self.fps_var = tk.StringVar(value='60')
        fps_box = ttk.Combobox(row, textvariable=self.fps_var, values=FPS_CHOICES, width=6, state='readonly')
        fps_box.grid(row=0, column=1, padx=4, pady=4, sticky='w')

        ttk.Label(row, text='Aspect ratio:').grid(row=1, column=0, padx=4, pady=4, sticky='e')
        self.aspect_var = tk.StringVar(value='16:9 (standard)')
        aspect_box = ttk.Combobox(row, textvariable=self.aspect_var, values=list(ASPECTS.keys()), width=24, state='readonly')
        aspect_box.grid(row=1, column=1, padx=4, pady=4, sticky='w')

        self.delete_after = tk.BooleanVar(value=False)
        del_check = ttk.Checkbutton(self.root, text="Delete from headset once it's copied over", variable=self.delete_after)
        del_check.pack(padx=10, pady=6)

        self.status = tk.StringVar(value='checking for a headset...')
        ttk.Label(self.root, textvariable=self.status, foreground='gray').pack(padx=10, pady=6)

        btn_row = ttk.Frame(self.root)
        btn_row.pack(padx=10, pady=6)
        self.go_btn = ttk.Button(btn_row, text='Apply Settings + Watch for Recording', command=self.on_go)
        self.go_btn.pack(side='left', padx=5)
        ttk.Button(btn_row, text='Open Recordings Folder', command=self.open_recordings).pack(side='left', padx=5)

        ttk.Label(self.root, text='Log:').pack(anchor='w', padx=10)
        self.log_box = tk.Text(self.root, height=14, width=64, bg='#111318', fg='#d8d8d8', state='disabled')
        self.log_box.pack(padx=10, pady=(0, 10))

    def log(self, msg):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', msg + '\n')
        self.log_box.see('end')
        self.log_box.configure(state='disabled')

    def open_recordings(self):
        try:
            subprocess.Popen(['xdg-open', SAVE_DIR])
        except Exception:
            messagebox.showinfo('Recordings folder', SAVE_DIR)

    def maybe_ask_about_shortcut(self):
        if os.path.exists(SHORTCUT_ASKED_FILE) or os.path.exists(DESKTOP_FILE):
            return

        yes = messagebox.askyesno(
            'Add to app launcher?',
            "Want Quest Recorder added to your app launcher so you don't need "
            "a terminal to open it next time?"
        )
        if yes:
            try:
                install_shortcut()
                messagebox.showinfo('Added', "Done, 'Quest Recorder' should show up in your launcher now.")
            except Exception as e:
                messagebox.showwarning('Hmm', f"Couldn't set that up: {e}")

        os.makedirs(CONFIG_DIR, exist_ok=True)
        open(SHORTCUT_ASKED_FILE, 'w').close()

    def run_adb(self, args):
        try:
            result = subprocess.run(['adb'] + args, capture_output=True, text=True, timeout=15)
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 1, '', "adb isn't installed / not on PATH"
        except subprocess.TimeoutExpired:
            return 1, '', 'adb timed out'

    def check_device(self):
        code, _, _ = self.run_adb(['get-state'])
        if code == 0:
            self.status.set('headset connected')
        else:
            self.status.set('no headset found - plug it in')

    def on_go(self):
        if self.watching:
            return
        self.go_btn.configure(state='disabled')
        t = threading.Thread(target=self.record_flow, daemon=True)
        t.start()

    def record_flow(self):
        code, _, _ = self.run_adb(['get-state'])
        if code != 0:
            self.log('no headset detected, plug it in and try again')
            self.go_btn.configure(state='normal')
            return

        fps = self.fps_var.get()
        width, height = ASPECTS[self.aspect_var.get()]

        self.log(f'setting {fps}fps @ {width}x{height}...')

        prop_cmd = ' && '.join([
            f'setprop debug.oculus.capture.fps {fps}',
            f'setprop debug.oculus.capture.width {width}',
            f'setprop debug.oculus.capture.height {height}',
            f'setprop debug.oculus.capture.bitrate {BITRATE}',
            'setprop debug.oculus.fullRateCapture 1',
        ])
        code, _, err = self.run_adb(['shell', prop_cmd])
        if code != 0:
            self.log(f"couldn't set capture props: {err}")
            self.go_btn.configure(state='normal')
            return

        self.log('settings applied.')
        self.log('in the headset: hold Meta button + trigger to start recording, same again to stop.')
        self.log(f'watching {VIDEO_FOLDER} now...')

        self.watching = True
        _, before, _ = self.run_adb(['shell', 'ls', VIDEO_FOLDER])
        before_files = set(before.split())

        new_file = None
        while self.watching:
            time.sleep(4)
            code, after, _ = self.run_adb(['shell', 'ls', VIDEO_FOLDER])
            if code != 0:
                continue
            new_ones = set(after.split()) - before_files
            if new_ones:
                new_file = sorted(new_ones)[0]
                break

        if new_file is None:
            self.watching = False
            self.go_btn.configure(state='normal')
            return

        self.log(f'found it: {new_file}')
        self.log('giving it a few seconds to finish writing before pulling...')
        tremote_path = f'{VIDEO_FOLDER}/{new_file}'
local_path = os.path.join(SAVE_DIR, new_file)

print("Waiting for recording to finish...")

last_size = -1
stable_count = 0

while stable_count < 3:
    code, out, _ = self.run_adb(
        ['shell', 'stat', '-c', '%s', remote_path]
    )

    try:
        size = int(out.strip())
    except:
        size = -1

    if size == last_size:
        stable_count += 1
    else:
        stable_count = 0

    last_size = size
    time.sleep(2)

print("File finished, pulling...")

code, _, err = self.run_adb(['pull', remote_path, local_path])
        if code != 0:
            self.log(f'pull failed: {err}')
        else:
            self.log(f'saved -> {local_path}')
            if self.delete_after.get():
                self.log('deleting the copy on the headset...')
                dcode, _, derr = self.run_adb(['shell', 'rm', remote_path])
                if dcode == 0:
                    self.log('done')
                else:
                    self.log(f"couldn't delete it: {derr}")

        self.watching = False
        self.go_btn.configure(state='normal')


def main():
    root = tk.Tk(className='Quest Recorder')  # sets WM_CLASS so it's not just labeled "Tk" everywhere
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
