"""Sparse reward: kills, level clear, death."""

from src.reward_funcs.base import RewardFunction


class SimpleReward(RewardFunction):
    def __init__(self, kill=1.0, clear=5.0, death=-5.0):
        self.kill = kill
        self.clear = clear
        self.death = death
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
        return reward
