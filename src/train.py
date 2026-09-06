"""Training entry point.  python -m src.train

Launches Dolphin headless/uncapped (~11x realtime), trains PPO, and evaluates
periodically against held-out levels.
"""

import argparse
import json
import os

import dolphin_memory_engine as dme
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from src import dolphin
from src.controller import PipeController
from src.encoders.grid import GridEncoder
from src.env import TanksEnv
from src.levels import AdaptiveSampler
from src.policy import POLICY_KWARGS
from src.reward_funcs.combat import CombatReward

START_STATE = os.path.join(dolphin.PROJECT_ROOT, "Games", "Levels", "level1.sav")
MODEL_DIR = os.path.join(dolphin.PROJECT_ROOT, "models")
LOG_DIR = os.path.join(dolphin.PROJECT_ROOT, "logs")
LATEST_PATH = os.path.join(MODEL_DIR, "latest")

# Level 2 excluded: its single enemy frequently kills itself on its own
# ricochet within a couple of steps, so it hands out clears the agent didn't
# earn and pollutes the reward signal.
TRAIN_LEVELS = [3, 4]
EVAL_LEVELS = [5, 6]        # held out, to show generalisation rather than memorisation


class PeriodicEval(BaseCallback):
    """Freeze the policy every `every_steps` and score it on EVAL_LEVELS.

    SB3's EvalCallback wants a second env, but there's only one Dolphin
    instance -- so this reuses the training env and just overrides the level
    per episode. Eval episodes therefore interleave with training ones; that's
    the cost of a single emulator.
    """

    def __init__(self, env, every_steps, episodes, levels, model_dir,
                 sampler=None, log_dir=None, verbose=1):
        super().__init__(verbose)
        self.env = env
        self.every_steps = every_steps
        self.episodes = episodes
        self.levels = levels
        self.model_dir = model_dir
        self.sampler = sampler
        self.history_path = os.path.join(log_dir or model_dir, "eval_history.json")
        self.history = []
        self.best = -np.inf

    def _on_step(self) -> bool:
        if self.n_calls % self.every_steps != 0:
            return True

        # Per level, not just aggregate -- an average hides "solid on 5,
        # never clears 6", which is exactly what you want to see.
        per_level = {lvl: {"episodes": 0, "cleared": 0, "returns": []}
                     for lvl in self.levels}

        for i in range(self.episodes):
            level = self.levels[i % len(self.levels)]
            obs, _ = self.env.reset(options={"level": level})
            done, total = False, 0.0
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, term, trunc, info = self.env.step(action)
                total += reward
                done = term or trunc
            rec = per_level[level]
            rec["episodes"] += 1
            rec["cleared"] += info.get("outcome") == "cleared"
            rec["returns"].append(total)

        all_returns = [r for rec in per_level.values() for r in rec["returns"]]
        mean = float(np.mean(all_returns))
        cleared = sum(rec["cleared"] for rec in per_level.values())

        entry = {"timesteps": int(self.num_timesteps), "mean_return": mean,
                 "levels": {}}
        for lvl, rec in per_level.items():
            if not rec["episodes"]:
                continue
            rate = rec["cleared"] / rec["episodes"]
            entry["levels"][str(lvl)] = {
                "episodes": rec["episodes"],
                "cleared": rec["cleared"],
                "clear_rate": rate,
                "mean_return": float(np.mean(rec["returns"])),
            }
            self.logger.record(f"eval/level_{lvl}/clear_rate", rate)
            self.logger.record(f"eval/level_{lvl}/mean_return",
                               float(np.mean(rec["returns"])))

        if self.sampler is not None:
            entry["train_sampler"] = self.sampler.summary()

        self.history.append(entry)
        with open(self.history_path, "w") as f:
            json.dump(self.history, f, indent=2)

        self.logger.record("eval/mean_return", mean)
        self.logger.record("eval/cleared_rate", cleared / self.episodes)
        if self.verbose:
            detail = " ".join(
                f"L{lvl}:{v['cleared']}/{v['episodes']}"
                for lvl, v in entry["levels"].items())
            print(f"[eval @ {self.num_timesteps}] mean_return={mean:.2f} "
                  f"cleared={cleared}/{self.episodes}  {detail}", flush=True)

        if mean > self.best:
            self.best = mean
            self.model.save(os.path.join(self.model_dir, "best_model"))
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=100_000)
    parser.add_argument("--eval-every", type=int, default=10_000)
    parser.add_argument("--eval-episodes", type=int, default=4)
    parser.add_argument("--resume", help="path to a saved model to continue from")
    args = parser.parse_args()

    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    dolphin.launch(state=START_STATE, headless=True, uncapped=True)
    print("Dolphin ready", flush=True)

    controller = PipeController(dolphin.PIPE_PATH)
    sampler = AdaptiveSampler(TRAIN_LEVELS)

    def recover(env):
        """Relaunch Dolphin and reconnect. The pipe FD dies with the old
        process, so the controller has to be reopened too."""
        controller.close()
        dolphin.launch(state=START_STATE, headless=True, uncapped=True)
        controller.open()

    env = TanksEnv(
        dme=dme,
        controller=controller,
        encoder=GridEncoder(),
        reward_fn=CombatReward(),
        levels=sampler,
        on_stuck=recover,
    )
    # Monitor records episode return/length, which is what the reward curve
    # is read from.
    monitored = Monitor(env, os.path.join(LOG_DIR, "monitor.csv"))

    resume_from = args.resume
    if not resume_from and os.path.exists(LATEST_PATH + ".zip"):
        resume_from = LATEST_PATH
    if resume_from:
        print(f"resuming from {resume_from}", flush=True)
        model = PPO.load(resume_from, env=monitored, tensorboard_log=LOG_DIR)
    else:
        model = PPO(
            "CnnPolicy",
            monitored,
            policy_kwargs=POLICY_KWARGS,
            n_steps=128,          # episodes are only a few steps, so a long
                                  # rollout spans many of them and delays
                                  # feedback while the reward is being tuned
            batch_size=64,
            verbose=1,
            tensorboard_log=LOG_DIR,
        )

    callbacks = [
        CheckpointCallback(save_freq=args.eval_every, save_path=MODEL_DIR,
                           name_prefix="ckpt"),
        PeriodicEval(env, args.eval_every, args.eval_episodes, EVAL_LEVELS,
                     MODEL_DIR, sampler=sampler, log_dir=LOG_DIR),
    ]

    # `--steps` is a cumulative target, so a resumed run continues counting
    # rather than starting over.
    remaining = max(0, args.steps - model.num_timesteps)
    print(f"at {model.num_timesteps} steps, {remaining} remaining", flush=True)

    try:
        if remaining:
            model.learn(total_timesteps=remaining, callback=callbacks,
                        reset_num_timesteps=False)
        model.save(os.path.join(MODEL_DIR, "final"))
    finally:
        # Save before anything else so a crash never loses progress; the
        # wrapper resumes from here.
        model.save(LATEST_PATH)
        print(f"saved {LATEST_PATH} at {model.num_timesteps} steps", flush=True)
        env.close()


if __name__ == "__main__":
    main()
