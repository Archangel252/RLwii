"""Per-platform Dolphin locations and process control.

Dolphin keeps its user data in a different place on each OS and there is no
single "launch it" command, so everything OS-specific lives here. Linux is
the container target; macOS is the dev machine.
"""

import os
import platform
import subprocess

IS_MAC = platform.system() == "Darwin"

if IS_MAC:
    USER_DIR = os.path.expanduser("~/Library/Application Support/Dolphin")
    BINARY = "/Applications/Dolphin.app/Contents/MacOS/Dolphin"
    # `open -a` is needed rather than exec'ing the binary directly, otherwise
    # macOS treats it as a background process with no window.
    LAUNCH_PREFIX = ["open", "-a", "/Applications/Dolphin.app", "--args"]
    QUIT_CMD = ["osascript", "-e", 'quit app "Dolphin"']
    FOCUS_CMD = ["osascript", "-e", 'tell application "Dolphin" to activate']
else:
    # Dolphin follows the XDG spec on Linux; config and data are split.
    USER_DIR = os.environ.get(
        "DOLPHIN_USER_DIR", os.path.expanduser("~/.config/dolphin-emu"))
    BINARY = os.environ.get("DOLPHIN_BINARY", "dolphin-emu")
    # The Qt binary, not dolphin-emu-nogui: the headless frontend has no
    # hotkey polling, so save states can never be loaded there. Under Xvfb
    # this runs windowless in practice.
    LAUNCH_PREFIX = [BINARY]
    QUIT_CMD = None                      # no scriptable quit; signal instead
    FOCUS_CMD = None                     # unnecessary once hotkeys ignore focus

CONFIG_DIR = os.path.join(USER_DIR, "Config")
PIPES_DIR = os.path.join(USER_DIR, "Pipes")
STATES_DIR = os.path.join(USER_DIR, "StateSaves")


def process_matches():
    """Pattern identifying the Dolphin process for pgrep/pkill."""
    return BINARY


def focus():
    if FOCUS_CMD:
        subprocess.run(FOCUS_CMD, capture_output=True)


def quit_command():
    return QUIT_CMD


def launch_command(args):
    return LAUNCH_PREFIX + list(args)
