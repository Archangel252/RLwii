"""Write Dolphin's config and create the input pipe.

Dolphin needs several non-default settings before any of this works, and they
were painful to rediscover -- see README. Templates live in config/ with
PIPE_NAME substituted so multiple instances can each own a pipe.

    python -m src.provision
"""

import os
import shutil

from src import dolphin
from src import platform_paths as plat

TEMPLATE_DIR = os.path.join(dolphin.PROJECT_ROOT, "config")
TEMPLATES = ["WiimoteNew.ini", "Hotkeys.ini", "Dolphin.ini"]


def provision(pipe_name=None, overwrite=True):
    pipe_name = pipe_name or dolphin.PIPE_NAME
    for directory in (plat.CONFIG_DIR, plat.PIPES_DIR, plat.STATES_DIR):
        os.makedirs(directory, exist_ok=True)

    for name in TEMPLATES:
        dest = os.path.join(plat.CONFIG_DIR, name)
        if os.path.exists(dest) and not overwrite:
            continue
        text = open(os.path.join(TEMPLATE_DIR, name)).read()
        with open(dest, "w") as f:
            f.write(text.replace("PIPE_NAME", pipe_name))

    pipe = os.path.join(plat.PIPES_DIR, pipe_name)
    if not os.path.exists(pipe):
        os.mkfifo(pipe)
    return pipe


def main():
    pipe = provision()
    print(f"config -> {plat.CONFIG_DIR}")
    print(f"pipe   -> {pipe}")


if __name__ == "__main__":
    main()
