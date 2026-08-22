"""Sparse reward plus survival shaping.

Measured baseline: a stationary tank survives 60+ seconds of game time, while
random movement burns 3 lives in ~10-20 steps. Deaths are self-inflicted --
wandering into fire -- so the shaping targets staying alive and keeping away
from incoming bullets.
"""

import math

from src.reward_funcs.base import RewardFunction

# Per step. Must stay small enough that stalling can't beat winning:
# ALIVE_BONUS * MAX_EPISODE_STEPS (2000) = 4.0 < clear (5) + kills.
ALIVE_BONUS = 0.002

# One grid cell is 35 units; penalise bullets within ~2 cells.
DANGER_RADIUS = 70.0
DANGER_WEIGHT = 0.05


class ShapedReward(RewardFunction):
    def __init__(self, kill=1.0, clear=5.0, death=-5.0,
                 alive_bonus=ALIVE_BONUS, danger_weight=DANGER_WEIGHT,
                 danger_radius=DANGER_RADIUS):
        self.kill = kill
        self.clear = clear
        self.death = death
        self.alive_bonus = alive_bonus
        self.danger_weight = danger_weight
        self.danger_radius = danger_radius
        self.prev_enemies = 0

    def reset(self, env) -> None:
        self.prev_enemies = env.enemies_remaining()

    def __call__(self, env) -> float:
        # Kills come from the enemy counter dropping rather than score, since
        # score may move by more than one per kill.
        enemies = env.enemies_remaining()
        reward = self.kill * max(0, self.prev_enemies - enemies)
        self.prev_enemies = enemies

        if env.level_cleared():
            reward += self.clear
        if env.died():
            reward += self.death
            return reward          # no survival credit on the step you die

        reward += self.alive_bonus
        reward -= self.danger_weight * self._threat(env)
        return reward

    def _threat(self, env):
        """0 when no bullet is near, rising to 1 as one closes in.

        Uses the nearest bullet only -- summing over all of them would make
        crowded moments dominate the sparse rewards entirely.
        """
        tx, ty = env.tank_pos()
        nearest = None
        for bx, by in env.bullets():
            d = math.hypot(bx - tx, by - ty)
            if nearest is None or d < nearest:
                nearest = d
        if nearest is None or nearest >= self.danger_radius:
            return 0.0
        return 1.0 - nearest / self.danger_radius
