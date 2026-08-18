"""
Gymnasium Env for Wii Play Tanks, driven via Dolphin.

Wires together memory_map.py (state, via dolphin-memory-engine) and
controller.py (actions, via Dolphin Pipe Input) into a standard
reset/step/observation interface any RL library (SB3, CleanRL, etc.) can
train against.
"""

import gymnasium as gym
import numpy as np


class TanksEnv(gym.Env):
    """Gymnasium Env wrapping the Tanks minigame running in Dolphin."""

    def __init__(self):
        super().__init__()
        # TODO: define self.observation_space (Box over whatever state
        # get_obs() returns -- tank position, aim, alive/dead flag, enemy
        # state, ...) and self.action_space (Discrete or Box, depending on
        # how actions get mapped to controller.py calls).

        # TODO: connect to dolphin-memory-engine (dme.hook()) and construct
        # a PipeController pointed at the configured pipe name.
        pass

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        # TODO: reset the in-game round to a known state. Tanks may not have
        # a scripted "restart" -- figure out whether this means navigating
        # menus via controller inputs, or savestating to a fixed point via
        # Dolphin's save state API/hotkeys.
        # TODO: return (observation, info) per Gymnasium API.
        raise NotImplementedError

    def step(self, action):
        # TODO: translate `action` into controller.py press/release/
        # set_main_stick calls.
        # TODO: advance the emulator by one "step" worth of frames (decide
        # step granularity -- every frame vs. every N frames).
        # TODO: read new state via get_obs(), compute reward from score
        # delta and the alive/dead flag (Tanks is one-hit-kill, no health
        # to track), determine terminated/truncated.
        # TODO: return (observation, reward, terminated, truncated, info).
        raise NotImplementedError

    def get_obs(self) -> np.ndarray:
        # TODO: read the addresses in memory_map.ADDRESSES via
        # dolphin-memory-engine and pack them into the observation array
        # matching self.observation_space.
        # TODO: bullets are a special case -- not a fixed address. Scan
        # slot_k = 0x91d0f7ac + k*0x710 over a range of k (see
        # memory_map.py's bullet section for the confirmed arena formula),
        # read slot_k_active at each, and collect pos_a/pos_b for slots
        # reading 0x01000000. Pad/truncate to a fixed max bullet count for
        # a stable observation shape.
        # TODO: blocks/obstacles use the same scan pattern, and their arena
        # is fully mapped (see memory_map.BLOCK_ARENA_* constants): walk
        # k in range(BLOCK_SLOT_COUNT), keep slots whose active word reads
        # BLOCK_ACTIVE, read x/y at BLOCK_OFF_X / BLOCK_OFF_Y. Blocks never
        # spawn or move -- they only get destroyed -- so this can be read
        # once in reset() and then refreshed only when "block_count"
        # changes, instead of re-scanning every frame.
        raise NotImplementedError

    def render(self):
        # Dolphin renders its own window; likely a no-op or just a note
        # that the game window itself is the render output.
        pass

    def close(self):
        # TODO: un-hook dolphin-memory-engine, close the pipe controller.
        pass
