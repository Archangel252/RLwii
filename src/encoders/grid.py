"""Grid encoder: the arena as a multi-channel occupancy tensor.

Entities are binned into the game's own 35-unit grid, so variable entity
counts need no padding and slot ordering is irrelevant -- position is the
encoding. Spatial relationships ("bullet two cells to my left") become local
patterns a convolution can pick up directly.
"""

import gymnasium as gym
import numpy as np

from src import memory_map
from src.encoders.base import Encoder

# Fixed grid sized to the largest level observed (x +/-367.5, y +/-280).
# Smaller levels simply leave the margins empty, which keeps the observation
# shape constant across levels -- a network can't cope with it changing.
X_MIN, Y_MIN = -367.5, -280.0
COLS, ROWS = 22, 17

(CH_WALL, CH_CORK, CH_HOLE, CH_SELF, CH_ENEMY,
 CH_BULLET, CH_BOMB, CH_AIM_X, CH_AIM_Y) = range(9)
N_CHANNELS = 9

MOVES = [None, "D_UP", "D_DOWN", "D_LEFT", "D_RIGHT"]

# The IR pointer is an absolute screen position and the turret points AT it,
# so aim is a position, not a direction -- the firing angle depends on where
# the tank happens to be standing. Actions therefore pick a pointer position;
# the policy learns what each one means.
AIM_COLS, AIM_ROWS = 5, 5
AIM_CENTRE = (0.5, 0.5)


class GridEncoder(Encoder):
    def __init__(self):
        self._held = set()
        self._aim = AIM_CENTRE

    # ---------- spaces ----------

    @property
    def observation_space(self) -> gym.Space:
        return gym.spaces.Box(
            low=0.0, high=1.0, shape=(N_CHANNELS, ROWS, COLS), dtype=np.float32
        )

    @property
    def action_space(self) -> gym.Space:
        # Sizes derive from the tables above so they can't drift out of sync.
        return gym.spaces.MultiDiscrete(
            [len(MOVES), 2, 2, AIM_COLS, AIM_ROWS]
        )

    # ---------- observation ----------

    def encode(self, env) -> np.ndarray:
        grid = np.zeros((N_CHANNELS, ROWS, COLS), dtype=np.float32)

        for x, y, block_type, solid in env.blocks():
            if block_type == memory_map.BLOCK_TYPE_HOLE:
                channel = CH_HOLE
            elif block_type == memory_map.BLOCK_TYPE_WALL:
                channel = CH_WALL if solid else CH_CORK
            else:
                # Untypable block (no occupied neighbour). Treat as solid --
                # over-estimating an obstacle is the safer error.
                channel = CH_WALL
            self._mark(grid, channel, x, y)

        self._mark(grid, CH_SELF, *env.tank_pos())

        for x, y in env.enemy_tanks():
            self._mark(grid, CH_ENEMY, x, y)

        for x, y in env.bullets():
            self._mark(grid, CH_BULLET, x, y)

        for x, y, fuse in env.bombs():
            # Value carries urgency rather than just presence: 1.0 freshly
            # placed, approaching 0.0 as it is about to detonate.
            frac = fuse / memory_map.BOMB_FUSE_SECONDS
            self._mark(grid, CH_BOMB, x, y, max(0.0, min(1.0, frac)))

        # Pointer state as two constant planes. The screen->world mapping is
        # uncalibrated, so the pointer can't be placed in a world cell; these
        # just tell the policy where it is currently aiming. Wasteful (a full
        # plane per scalar) -- a Dict space with MultiInputPolicy would be
        # tidier if the observation ever needs more scalars.
        grid[CH_AIM_X, :, :] = self._aim[0]
        grid[CH_AIM_Y, :, :] = self._aim[1]

        return grid

    @staticmethod
    def _mark(grid, channel, x, y, value=1.0):
        col = int(round((x - X_MIN) / memory_map.BLOCK_GRID_STEP))
        row = int(round((y - Y_MIN) / memory_map.BLOCK_GRID_STEP))
        if 0 <= row < ROWS and 0 <= col < COLS:
            grid[channel, row, col] = value

    # ---------- action ----------

    def apply(self, action, controller) -> None:
        move_idx, fire, bomb, aim_col, aim_row = (int(a) for a in action)

        wanted = set()
        if MOVES[move_idx]:
            wanted.add(MOVES[move_idx])
        if fire:
            wanted.add("B")
        if bomb:
            wanted.add("A")

        # PRESS is level-triggered, so send only the differences; anything
        # not explicitly released stays held into the next step.
        for button in self._held - wanted:
            controller.release(button)
        for button in wanted - self._held:
            controller.press(button)
        self._held = wanted

        # Cell centres, so the extremes of the stick range are never used.
        self._aim = ((aim_col + 0.5) / AIM_COLS, (aim_row + 0.5) / AIM_ROWS)
        controller.set_main_stick(*self._aim)

    def reset(self) -> None:
        """Forget held buttons and re-centre aim; call when an episode restarts."""
        self._held = set()
        self._aim = AIM_CENTRE
