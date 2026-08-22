"""
Gymnasium Env for Wii Play Tanks, driven via Dolphin.

Owns all memory reading; render.py draws whatever this exposes.
"""

import math
import time
import struct

import gymnasium as gym
import numpy as np

import memory_map

BLOCK_RECHECK_FRAMES = 30
MIN_BLOCK_CHAIN = 4


class TanksEnv(gym.Env):
    """Gymnasium Env wrapping the Tanks minigame running in Dolphin."""

    def __init__(self, dme, controller):
        super().__init__()
        self.dme = dme
        self.controller = controller
        # TODO: define self.observation_space / self.action_space.
        self.frames_since_block_check = 0
        self.last_relocate_count = None
        self.block_slot_addrs = []
        self.block_types = {}
        self.refresh_blocks()
        self.last_tank_alive = self.tank_alive()

    # ---------- lifecycle ----------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        # TODO: load a save state (hotkeys bound to pipe buttons X/Y/Z/START/L/R),
        # or jump levels via memory_map's level_index + enemies_remaining writes.
        # TODO: return (observation, info) per Gymnasium API.
        raise NotImplementedError

    def step(self, action):
        # TODO: translate `action` into controller.py calls, advance N frames,
        # then compute reward from score delta + alive flag.
        raise NotImplementedError

    def get_obs(self) -> np.ndarray:
        # TODO: pack the state below into a fixed-shape array matching
        # self.observation_space (pad bullets/enemies to a max count).
        raise NotImplementedError

    def close(self):
        self.controller.release_all()
        self.controller.close()
        self.dme.un_hook()

    # ---------- scalar state ----------

    def tank_alive(self):
        return self.dme.read_word(memory_map.ADDRESSES["tank_alive"])

    def score(self):
        return self.dme.read_word(memory_map.ADDRESSES["score"])

    def block_count(self):
        return self.dme.read_word(memory_map.ADDRESSES["block_count"])

    def level(self):
        return self.dme.read_byte(memory_map.ADDRESSES["level_index"]) + 1

    def frame_count(self):
        return self.dme.read_word(memory_map.ADDRESSES["frame_counter"])

    def wait_frames(self, n):
        """Block until n emulated frames have elapsed."""
        target = self.frame_count() + n
        while self.frame_count() < target:
            time.sleep(0.001)

    def tank_pos(self):
        return (
            self.dme.read_float(memory_map.ADDRESSES["tank_x_pos"]),
            self.dme.read_float(memory_map.ADDRESSES["tank_y_pos_mem2"]),
        )

    # ---------- entities ----------

    def blocks(self):
        """[(x, y, type)] for live blocks; type per memory_map.BLOCK_TYPE_*."""
        out = []
        for base in self.block_slot_addrs:
            if self.dme.read_word(base) != memory_map.BLOCK_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.BLOCK_OFF_X)
            y = self.dme.read_float(base + memory_map.BLOCK_OFF_Y)
            solid = self.dme.read_word(base + memory_map.BLOCK_OFF_DESTRUCTIBLE)
            block_type = self.block_types.get((round(x, 1), round(y, 1)))
            out.append((x, y, block_type, bool(solid)))
        return out

    def bullets(self):
        out = []
        for k in range(memory_map.BULLET_SLOT_COUNT):
            base = memory_map.BULLET_ARENA_BASE + k * memory_map.BULLET_ARENA_STRIDE
            if self.dme.read_word(base + memory_map.BULLET_OFF_ACTIVE) != memory_map.BULLET_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.BULLET_OFF_POS_A)
            y = self.dme.read_float(base + memory_map.BULLET_OFF_POS_B)
            if self._sane(x, y) and not (x == 0.0 and y == 0.0):
                out.append((x, y))
        return out

    def enemy_tanks(self):
        out = []
        for k in range(memory_map.ENEMY_SLOT_COUNT):
            base = memory_map.ENEMY_ARENA_BASE + k * memory_map.ENEMY_ARENA_STRIDE
            if self.dme.read_word(base) != memory_map.ENEMY_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.ENEMY_OFF_X)
            y = self.dme.read_float(base + memory_map.ENEMY_OFF_Y)
            if self._sane(x, y):
                out.append((x, y))
        return out

    def bombs(self):
        """[(x, y, fuse_seconds)]"""
        out = []
        for k in range(memory_map.BOMB_SLOT_COUNT):
            base = memory_map.BOMB_ARENA_BASE + k * memory_map.BOMB_ARENA_STRIDE
            if self.dme.read_word(base) != memory_map.BOMB_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.BOMB_OFF_X)
            y = self.dme.read_float(base + memory_map.BOMB_OFF_Y)
            if self._sane(x, y):
                out.append((x, y, self.dme.read_float(base + memory_map.BOMB_OFF_FUSE)))
        return out

    # ---------- block arena bookkeeping ----------

    def poll(self):
        """Per-frame upkeep: re-locate the block arena when it moves."""
        self._check_respawn()
        self._check_blocks_stale()

    def refresh_blocks(self):
        self.block_slot_addrs = self._locate_block_slots()
        self.block_types = memory_map.block_types(self.dme, self.block_slot_addrs)
        self.frames_since_block_check = 0

    def _check_respawn(self):
        # Respawn reallocates the block arena, same as a level change.
        alive = self.tank_alive()
        if alive == 1 and self.last_tank_alive == 0:
            self.refresh_blocks()
        self.last_tank_alive = alive

    def _check_blocks_stale(self):
        # Destruction keeps both counts in sync, so a mismatch means the arena
        # moved. Retry once per block_count value or we'd re-scan forever.
        self.frames_since_block_check += 1
        if self.frames_since_block_check < BLOCK_RECHECK_FRAMES:
            return
        self.frames_since_block_check = 0

        expected = self.block_count()
        actual = sum(
            1 for base in self.block_slot_addrs
            if self.dme.read_word(base) == memory_map.BLOCK_ACTIVE
        )
        if actual != expected and self.last_relocate_count != expected:
            self.last_relocate_count = expected
            self.refresh_blocks()

    def _locate_block_slots(self):
        data = self.dme.read_bytes(memory_map.BLOCK_SCAN_START, memory_map.BLOCK_SCAN_SIZE)
        stride = memory_map.BLOCK_ARENA_STRIDE
        hits = set()
        for off in range(0, len(data) - 4, 4):
            if struct.unpack_from(">I", data, off)[0] == memory_map.BLOCK_ACTIVE:
                hits.add(memory_map.BLOCK_SCAN_START + off)

        slots = []
        for h in hits:
            if (h - stride) in hits:
                continue
            chain = []
            addr = h
            while addr in hits:
                chain.append(addr)
                addr += stride
            if len(chain) < MIN_BLOCK_CHAIN:
                continue
            for base in chain:
                x = self.dme.read_float(base + memory_map.BLOCK_OFF_X)
                y = self.dme.read_float(base + memory_map.BLOCK_OFF_Y)
                if self._sane(x, y) and abs(x) < 1000 and abs(y) < 1000:
                    slots.append(base)
        return slots

    @staticmethod
    def _sane(x, y):
        return math.isfinite(x) and math.isfinite(y)
