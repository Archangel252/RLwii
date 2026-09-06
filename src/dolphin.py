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
LEVELS_DIR = os.path.join(PROJECT_ROOT, "Games", "Levels")


def level_state(level):
    """Path to a level's save state, or None if we don't have one."""
    path = os.path.join(LEVELS_DIR, f"level{level}.sav")
    return path if os.path.exists(path) else None


def focus():
    subprocess.run(["osascript", "-e", 'tell application "Dolphin" to activate'],
                   capture_output=True)


def load_state(controller, state_path=CLEAN_STATE, attempts=3):
    """Restore a known-good state. Works from any state, including game-over.

    Needs HotkeysRequireFocus=False in Dolphin.ini (see README); without it
    the hotkey is dropped whenever Dolphin isn't frontmost. Retries anyway,
    since a silently dropped load used to leave callers running against a
    dead game.
    """
    for attempt in range(attempts):
        if _try_load_state(controller, state_path):
            return True
        print(f"[dolphin] state load attempt {attempt + 1} failed", flush=True)
    raise RuntimeError(f"could not load save state after {attempts} attempts")


def _try_load_state(controller, state_path):
    import dolphin_memory_engine as _dme
    from src import memory_map as _m

    shutil.copyfile(state_path, SLOT_FILE)

    # Detect the load by watching the tank snap back to the state's position.
    # The frame counter is not usable for this: a state carries its own
    # counter value, which can be higher than the current one (notably right
    # after a launch), so "counter went backwards" silently misses real loads.
    def snapshot():
        return (round(_dme.read_float(_m.ADDRESSES["tank_x_pos"]), 1),
                round(_dme.read_float(_m.ADDRESSES["tank_y_pos_mem2"]), 1),
                _dme.read_word(_m.ADDRESSES["lives_remaining"]),
                _dme.read_byte(_m.ADDRESSES["level_index"]))

    before = snapshot()
    controller.press(SLOT_BUTTON)
    time.sleep(0.12)
    controller.release(SLOT_BUTTON)

    deadline = time.time() + 8.0
    while time.time() < deadline:
        if snapshot() != before:
            return True
        time.sleep(0.02)
    # State may match the live game exactly (e.g. loading twice in a row),
    # in which case nothing changes and there is nothing to detect.
    return snapshot() == before
