"""Reward tuned to make engaging worthwhile.

ShapedReward's survival bonus made hiding (+4.0) nearly as good as winning
(+6.0), so the agent stopped fighting. See README.
"""

import math

from src.reward_funcs.base import RewardFunction

KILL = 2.0
CLEAR = 10.0
DEATH = -2.0

# Small on purpose: near the death penalty it would suicide to end episodes.
TIME_COST = 0.002

DANGER_RADIUS = 70.0      # ~2 grid cells
DANGER_WEIGHT = 0.02


class CombatReward(RewardFunction):
    def __init__(self, kill=KILL, clear=CLEAR, death=DEATH,
                 time_cost=TIME_COST, danger_weight=DANGER_WEIGHT,
                 danger_radius=DANGER_RADIUS):
        self.kill = kill
        self.clear = clear
        self.death = death
        self.time_cost = time_cost
        self.danger_weight = danger_weight
        self.danger_radius = danger_radius
        self.prev_enemies = 0

    def reset(self, env) -> None:
        self.prev_enemies = env.enemies_remaining()

    def __call__(self, env) -> float:
        # Enemy counter, not score -- score can move by >1 per kill.
        enemies = env.enemies_remaining()
        reward = self.kill * max(0, self.prev_enemies - enemies)
        self.prev_enemies = enemies

        if env.level_cleared():
            return reward + self.clear
        if env.died():
            return reward + self.death

        reward -= self.time_cost
        reward -= self.danger_weight * self._threat(env)
        return reward

    def _threat(self, env):
        """0 when no bullet is near, rising to 1 as one closes in.

        Nearest only; summing would swamp the sparse kill/clear rewards.
        """
        tx, ty = env.tank_pos()
        nearest = min(
            (math.hypot(bx - tx, by - ty) for bx, by in env.bullets()),
            default=None)
        if nearest is None or nearest >= self.danger_radius:
            return 0.0
        return 1.0 - nearest / self.danger_radius
