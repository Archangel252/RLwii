"""Launching Dolphin with the right flags, and waiting until it's usable."""

import os
import shutil
import subprocess
import time

import dolphin_memory_engine as dme

APP = "/Applications/Dolphin.app"
BINARY = f"{APP}/Contents/MacOS/Dolphin"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(PROJECT_ROOT, "Games", "wii_play.wbfs")
PIPE_PATH = os.path.expanduser("~/Library/Application Support/Dolphin/Pipes/test")


def is_running():
    return subprocess.run(["pgrep", "-f", BINARY],
                          capture_output=True).returncode == 0


def quit_dolphin(timeout=30):
    subprocess.run(["osascript", "-e", 'quit app "Dolphin"'],
                   capture_output=True)
    deadline = time.time() + timeout
    while is_running() and time.time() < deadline:
        time.sleep(1)
    if is_running():
        subprocess.run(["pkill", "-9", "-f", BINARY], capture_output=True)
        time.sleep(2)


def launch(state=None, headless=False, uncapped=False, game=GAME, timeout=90):
    """Start Dolphin and block until memory and pipe are both usable.

    headless/uncapped give ~11x realtime for training (see README); leave both
    off to actually watch the game.
    """
    quit_dolphin()

    args = ["-e", game]
    if state:
        args += ["-s", state]
    if uncapped:
        args += ["-C", "Dolphin.Core.EmulationSpeed=0"]
    if headless:
        args += ["-v", "Null"]
    subprocess.run(["open", "-a", APP, "--args"] + args, check=True)

    wait_until_ready(timeout)


def wait_until_ready(timeout=90):
    """Hook first, then the pipe.

    Opening the pipe for writing blocks until Dolphin has the read end, so
    polling with O_NONBLOCK here avoids hanging forever when it never appears.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        dme.hook()
        if dme.is_hooked():
            break
        time.sleep(1)
    else:
        raise RuntimeError("Dolphin never became hookable")

    while time.time() < deadline:
        try:
            os.close(os.open(PIPE_PATH, os.O_WRONLY | os.O_NONBLOCK))
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Dolphin never opened the pipe at {PIPE_PATH}")


# Save-state recovery. Load-state is a hotkey and hotkeys are ignored unless
# Dolphin is frontmost, so this steals focus -- it's the fallback path, used
# only when a memory-write level jump leaves the game wedged.
SLOT_FILE = os.path.expanduser(
    "~/Library/Application Support/Dolphin/StateSaves/RHAE01.s01")
SLOT_BUTTON = "X"                                    # bound to Load State Slot 1
CLEAN_STATE = os.path.join(PROJECT_ROOT, "Games", "Levels", "level1.sav")


def focus():
    subprocess.run(["osascript", "-e", 'tell application "Dolphin" to activate'],
                   capture_output=True)


def load_state(controller, state_path=CLEAN_STATE):
    """Restore a known-good state. Works from any state, including game-over,
    which the memory-write level jump cannot do.

    Dolphin re-reads the slot file from disk on every load, so any state file
    can be used by copying it over the slot first.
    """
    shutil.copyfile(state_path, SLOT_FILE)
    focus()
    time.sleep(0.4)
    controller.press(SLOT_BUTTON)
    time.sleep(0.2)
    controller.release(SLOT_BUTTON)
    time.sleep(1.5)
