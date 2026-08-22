"""Level sampling strategies for training."""

import numpy as np


class AdaptiveSampler:
    """Uniform to start, then biased toward levels the agent clears least.

    Weight per level is (1 - clear_rate) + floor. The floor matters: without
    it a level the agent has fully mastered drops to zero probability and it
    can quietly forget how to play it.

    `warmup` episodes per level are sampled uniformly first, so early noise
    (one lucky clear) doesn't skew the distribution.
    """

    def __init__(self, levels, floor=0.1, warmup=3, rng=None):
        self.levels = list(levels)
        self.floor = floor
        self.warmup = warmup
        self.rng = rng or np.random.default_rng()
        self.stats = {lvl: {"episodes": 0, "cleared": 0} for lvl in self.levels}

    def record(self, level, cleared):
        if level in self.stats:
            self.stats[level]["episodes"] += 1
            self.stats[level]["cleared"] += bool(cleared)

    def clear_rate(self, level):
        s = self.stats[level]
        return s["cleared"] / s["episodes"] if s["episodes"] else 0.0

    def weights(self):
        if any(s["episodes"] < self.warmup for s in self.stats.values()):
            return np.ones(len(self.levels)) / len(self.levels)
        w = np.array([(1.0 - self.clear_rate(l)) + self.floor for l in self.levels])
        return w / w.sum()

    def __call__(self, env):
        # The env hands itself over, which is how the previous episode's
        # outcome gets folded in -- reset() is the only hook that runs
        # between episodes.
        last = getattr(env, "last_episode", None)
        if last:
            self.record(last["level"], last["outcome"] == "cleared")
            env.last_episode = None
        return int(self.rng.choice(self.levels, p=self.weights()))

    def summary(self):
        return {
            lvl: {
                "episodes": s["episodes"],
                "cleared": s["cleared"],
                "clear_rate": round(self.clear_rate(lvl), 3),
                "weight": round(float(w), 3),
            }
            for (lvl, s), w in zip(self.stats.items(), self.weights())
        }
