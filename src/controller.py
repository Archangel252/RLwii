"""
Dolphin "Pipe Input" controller wrapper.

Setup (see README): a FIFO at ~/Library/Application Support/Dolphin/Pipes/<name>,
the Wiimote port bound to Pipe/0/<name>, and BackgroundInput enabled.

Wire format is one command per line (Dolphin drains all pending lines once per
frame, then parses up to each newline):

    PRESS <button>            # level-triggered: stays held until RELEASE
    RELEASE <button>
    SET MAIN <x> <y>          # both in [0, 1]; 0.5 0.5 is centre
    SET <axis> <v>            # single-axis form, v in [-1, 1]

Buttons: A B X Y Z START L R D_UP D_DOWN D_LEFT D_RIGHT
Axes:    MAIN C (X/Y pairs), L R (shoulders)

Reference: Dolphin's Source/Core/InputCommon/ControllerInterface/Pipes/Pipes.cpp
"""

BUTTONS = frozenset(
    {"A", "B", "X", "Y", "Z", "START", "L", "R",
     "D_UP", "D_DOWN", "D_LEFT", "D_RIGHT"}
)


class PipeController:
    """Thin wrapper around a Dolphin Pipe Input FIFO."""

    def __init__(self, pipe_path: str):
        self.pipe_path = pipe_path
        self._pipe = None
        self.open()

    def open(self) -> None:
        # Blocks until Dolphin has the read end open
        if self._pipe is None:
            self._pipe = open(self.pipe_path, "w", buffering=1)

    def close(self) -> None:
        if self._pipe is not None:
            self._pipe.close()
            self._pipe = None

    def _send(self, command: str) -> None:
        if self._pipe is None:
            raise RuntimeError("pipe is closed")
        self._pipe.write(command + "\n")

    def press(self, button: str) -> None:
        self._send(f"PRESS {self._check(button)}")

    def release(self, button: str) -> None:
        self._send(f"RELEASE {self._check(button)}")

    def set_main_stick(self, x: float, y: float) -> None:
        """x, y in [0, 1]; 0.5, 0.5 is centre."""
        self._send(f"SET MAIN {self._clamp(x):.4f} {self._clamp(y):.4f}")

    def set_axis(self, axis: str, value: float) -> None:
        """Single-axis form; value in [-1, 1]."""
        self._send(f"SET {axis.upper()} {max(-1.0, min(1.0, float(value))):.4f}")

    def release_all(self) -> None:
        for button in BUTTONS:
            self.release(button)
        self.set_main_stick(0.5, 0.5)

    @staticmethod
    def _check(button: str) -> str:
        button = button.upper()
        if button not in BUTTONS:
            raise ValueError(f"unknown button {button!r}; expected one of {sorted(BUTTONS)}")
        return button

    @staticmethod
    def _clamp(v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    def __enter__(self) -> "PipeController":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
