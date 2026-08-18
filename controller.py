"""
Dolphin "Pipe Input" controller wrapper.

One-time manual Dolphin configuration (must be done by hand, once, in the
Dolphin GUI -- not automatable from here):
  1. Config -> Controllers -> pick the port the game reads from (usually
     Port 1) -> set device to "Pipe/0/<name>" (e.g. Pipe/0/tank-agent).
  2. Dolphin needs a named pipe at that name inside its user Pipes/ folder
     (on macOS: ~/Library/Application Support/Dolphin/Pipes/<name>, create
     the folder if it doesn't exist -- Dolphin creates the actual FIFO when
     it starts, or you may need to mkfifo it yourself depending on version).
  3. With Dolphin running and the game loaded, writing text commands into
     that pipe drives the controller as if a real pad were plugged in.

Command syntax (one command per line, examples):
    PRESS A
    RELEASE A
    SET MAIN 0.7 0.3      # main stick, x y in [-1, 1]
    SET TRIGGER L 1.0     # analog trigger
    SET BUTTON A 1.0      # digital button pressure, alternate form

Full command reference: Dolphin's source
(Source/Core/InputCommon/ControllerInterface/Pipe/Pipe.cpp).
"""

class PipeController:
    """Thin wrapper around a Dolphin Pipe Input FIFO."""

    def __init__(self, pipe_path: str):
        self.pipe_path = pipe_path
        self._pipe = None

    def open(self) -> None:
        # TODO: open self.pipe_path for writing (os.open with O_WRONLY, or
        # plain open() -- decide based on whether we need non-blocking
        # writes so a stalled Dolphin doesn't hang the training loop).
        raise NotImplementedError

    def close(self) -> None:
        # TODO: close the underlying pipe handle if open.
        raise NotImplementedError

    def press(self, button: str) -> None:
        # TODO: write f"PRESS {button}\n" to the pipe.
        raise NotImplementedError

    def release(self, button: str) -> None:
        # TODO: write f"RELEASE {button}\n" to the pipe.
        raise NotImplementedError

    def set_main_stick(self, x: float, y: float) -> None:
        # TODO: write f"SET MAIN {x} {y}\n" to the pipe. Validate x, y in
        # [-1, 1] first.
        raise NotImplementedError

    def __enter__(self) -> "PipeController":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
