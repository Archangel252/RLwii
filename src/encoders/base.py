import gymnasium as gym
import numpy as np

from abc import ABC, abstractmethod




class Encoder(ABC):
    """Translates between game state and the RL spaces."""


    @property
    @abstractmethod
    def observation_space(self) -> gym.Space:
        """Shape/bounds of what encode() returns."""

    @property
    @abstractmethod
    def action_space(self) -> gym.Space:
        """What apply() accepts."""
    @abstractmethod
    def encode(self, env) -> np.ndarray:
        """Read game state off `env` and pack it into observation_space."""

    @abstractmethod
    def apply(self, action, controller) -> None:
        """Drive `controller` from an action_space sample.

        Actions are held for the whole frame-skip window (PRESS is
        level-triggered), so release anything the new action doesn't want.
        """
