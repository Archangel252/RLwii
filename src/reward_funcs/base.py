"""Abstract base for reward functions."""

from abc import ABC, abstractmethod


class RewardFunction(ABC):
    """Scores the step that just completed.

    Kept separate from the env so reward shaping can be swapped without
    touching state reading -- reward is usually the most-iterated part of
    an RL project.
    """

    @abstractmethod
    def reset(self, env) -> None:
        """Called from env.reset(); cache any per-episode baselines."""

    @abstractmethod
    def __call__(self, env) -> float:
        """Reward for the step just taken. Called once per env.step()."""
