"""
Gymnasium Env for Wii Play Tanks, driven via Dolphin.

Owns all memory reading; render.py draws whatever this exposes.
"""

import math
import time

import gymnasium as gym
import numpy as np

from src import dolphin, memory_map

BLOCK_RECHECK_FRAMES = 30
MIN_BLOCK_CHAIN = 4

# Frames the action is held per step. Higher = more game time per decision
# (faster learning per wall-clock second) but coarser control.
FRAME_SKIP = 4

# Episode cap, in steps. Without one, an agent that learns to hide in a
# corner produces endless episodes and training stalls.
MAX_EPISODE_STEPS = 2000

# Topped up every reset. The tank gets 3 lives and there is no respawn once
# they run out -- the game sits at "alive = 0" forever and recovering needs a
# save-state load (which needs window focus). Writing lives sticks, so
# refilling each episode keeps an unattended run from wedging on a dead game.
RESET_LIVES = 3

DEFAULT_LEVEL = 2
LOAD_TIMEOUT_SECONDS = 20.0
LOAD_SETTLE_FRAMES = 60
ALIVE_CONFIRM_CHECKS = 3
RESET_ATTEMPTS = 3


class TanksEnv(gym.Env):
    """Gymnasium Env wrapping the Tanks minigame running in Dolphin."""

    def __init__(self, dme, controller, encoder=None, reward_fn=None, levels=None):
        """`levels` picks the level each episode. SB3 calls reset() without
        options, so training-time level control has to live here:
            levels=3            fixed
            levels=[2, 5, 9]    sampled uniformly each episode
            levels=callable     called with the env, returns a level number
        """
        super().__init__()
        self.dme = dme
        self.controller = controller
        self.encoder = encoder
        self.reward_fn = reward_fn
        self.levels = levels if levels is not None else DEFAULT_LEVEL
        self.episodes = 0
        self.episode_level = None
        self.last_episode = None
        if encoder is not None:
            self.observation_space = encoder.observation_space
            self.action_space = encoder.action_space
        self.frames_since_block_check = 0
        self.last_relocate_count = None
        self.block_slot_addrs = []
        self.block_types = {}
        self.refresh_blocks()
        self.last_tank_alive = self.tank_alive()

    # ---------- lifecycle ----------

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        level = (options or {}).get("level") or self._pick_level()
        self.episodes += 1

        self.controller.release_all()
        if hasattr(self.encoder, "reset"):
            self.encoder.reset()

        # The tank can be shot between the liveness check and here, so verify
        # and retry -- otherwise the episode starts dead and terminates on
        # step 1, feeding a degenerate transition to the learner.
        for attempt in range(RESET_ATTEMPTS):
            self._load_level(level)
            self.refresh_blocks()
            if self.tank_alive() == 1 and self.enemies_remaining() > 0:
                break
        else:
            raise RuntimeError(
                f"could not reach level {level} after {RESET_ATTEMPTS} attempts: "
                f"level={self.level()} alive={self.tank_alive()} "
                f"enemies={self.enemies_remaining()}"
            )

        self.steps = 0
        self.episode_level = self.level()
        self.last_tank_alive = self.tank_alive()
        if self.reward_fn is not None:
            self.reward_fn.reset(self)

        return self.get_obs(), {"level": self.level()}

    def step(self, action):
        self.encoder.apply(action, self.controller)
        self.wait_frames(FRAME_SKIP)
        self.steps += 1
        self.poll()

        obs = self.get_obs()

        # Win and loss both end the episode, so the outcome has to be exposed
        # explicitly -- otherwise clearing a level and dying are
        # indistinguishable to the reward function and to logging.
        cleared = self.level_cleared()
        died = self.died()
        terminated = cleared or died
        truncated = self.steps >= MAX_EPISODE_STEPS

        if terminated or truncated:
            # Kept so a level sampler can see how the episode went; it only
            # runs at the next reset, by which point the level has changed.
            self.last_episode = {"level": self.episode_level,
                                 "outcome": "cleared" if cleared else "died"}

        reward = self.reward_fn(self) if self.reward_fn is not None else 0.0
        info = {
            "level": self.level(),
            "score": self.score(),
            "outcome": "cleared" if cleared else "died" if died else None,
        }
        return obs, reward, terminated, truncated, info

    def _pick_level(self):
        if callable(self.levels):
            return int(self.levels(self))
        if isinstance(self.levels, (list, tuple)):
            # self.np_random comes from super().reset(seed=...), so level
            # sampling honours the seed like the rest of the env.
            return int(self.levels[self.np_random.integers(len(self.levels))])
        return int(self.levels)

    def _load_level(self, target):
        """Put the game into a playable `target` level.

        The fast path fakes a level completion with two memory writes, but it
        only fires from a healthy in-level state -- once the tank is dead or
        the game is mid-transition the writes do nothing and we'd return a
        broken state (notably enemies_remaining still 0, which reads as an
        instant false "cleared"). So verify, and fall back to a save state,
        which recovers from anything but steals window focus.
        """
        # An episode almost always ends with a dead tank, and the jump can't
        # fire from there -- trying anyway would burn the full timeout every
        # reset. Go straight to the save state when the game isn't playable.
        if self.tank_alive() == 1 and self._jump_to(target):
            return True

        dolphin.load_state(self.controller)
        # The restored state needs to become playable before a jump can fire
        # from it -- attempting one against a not-yet-alive tank leaves the
        # index write sitting there with no transition.
        self._wait_playable()

        return self.level() == target or self._jump_to(target)

    def _wait_playable(self, timeout=LOAD_TIMEOUT_SECONDS):
        """Wait for a live tank, tolerating the spawn-sequence flicker."""
        deadline = time.time() + timeout
        streak = 0
        while time.time() < deadline and streak < ALIVE_CONFIRM_CHECKS:
            self.wait_frames(LOAD_SETTLE_FRAMES)
            streak = streak + 1 if self.tank_alive() == 1 else 0
        return streak >= ALIVE_CONFIRM_CHECKS

    def _jump_to(self, target):
        """Try the memory-write jump. Returns True only if it left the game
        actually playable."""
        if self.level() != target:
            # -1 wraps to 255 for target=1; the transition's +1 carries it
            # back to 0. Untested for level 1, verified for levels >= 2.
            self.dme.write_byte(memory_map.ADDRESSES["level_index"],
                                (target - 2) % 256)
            self.dme.write_byte(memory_map.ADDRESSES["enemies_remaining"], 0)

        deadline = time.time() + LOAD_TIMEOUT_SECONDS
        while time.time() < deadline and self.level() != target:
            self.wait_frames(15)

        # Lives must be topped up AFTER the transition -- a level load resets
        # them, so writing beforehand is silently discarded.
        self.dme.write_word(memory_map.ADDRESSES["lives_remaining"], RESET_LIVES)

        # "alive" flickers during the spawn sequence, so require it to hold
        # across consecutive checks rather than returning on the flicker.
        self._wait_playable(max(0.0, deadline - time.time()))

        return (self.level() == target
                and self.tank_alive() == 1
                and self.enemies_remaining() > 0)

    def get_obs(self) -> np.ndarray:
        return self.encoder.encode(self)

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

    def lives(self):
        return self.dme.read_word(memory_map.ADDRESSES["lives_remaining"])

    def enemies_remaining(self):
        return self.dme.read_byte(memory_map.ADDRESSES["enemies_remaining"])

    def died(self):
        return self.tank_alive() == 0

    def level_cleared(self):
        """Win condition. Note reset() zeroes this counter to force a level
        transition, so it only means 'cleared' during normal play."""
        return self.enemies_remaining() == 0

    def frame_count(self):
        return self.dme.read_word(memory_map.ADDRESSES["frame_counter"])

    def wait_frames(self, n, timeout=10.0):
        """Block until n emulated frames have elapsed.

        The wall-clock timeout is a safety net: if emulation stalls or the
        frame counter goes stale, this would otherwise spin forever and wedge
        a training run with no error.
        """
        target = self.frame_count() + n
        deadline = time.time() + timeout
        while self.frame_count() < target:
            if time.time() > deadline:
                return False
            time.sleep(0.001)
        return True

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
        # Vectorised: a Python loop over 16M words takes ~1s, which at 11x
        # emulation speed is ~11s of game time -- long enough for the tank to
        # die between reset()'s liveness check and returning.
        words = np.frombuffer(data, dtype=">u4")
        offsets = np.flatnonzero(words == memory_map.BLOCK_ACTIVE) * 4
        hits = set((memory_map.BLOCK_SCAN_START + offsets).tolist())

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
