"""Watch a trained policy: python -m src.main --model models/best_model

Shows the policy's action distribution rather than the game -- Dolphin's own
window is the game view. GameRender (src/render.py) still exists and can be
swapped back in if you want the 2D state view instead.
"""

import argparse
import os

import dolphin_memory_engine as dme
import pygame
from stable_baselines3 import PPO

from src import dolphin
from src.controller import PipeController
from src.encoders.grid import GridEncoder
from src.env import TanksEnv
from src.policy_render import PolicyRender, action_probabilities

START_STATE = os.path.join(dolphin.PROJECT_ROOT, "Games", "Levels", "level1.sav")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="path to a saved model")
    parser.add_argument("--level", type=int, default=2)
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--attach", action="store_true",
                        help="use a running Dolphin instead of launching one")
    parser.add_argument("--deterministic", action="store_true")
    args = parser.parse_args()

    if args.attach:
        dolphin.wait_until_ready()
    else:
        # normal speed, video on -- this is the watchable configuration
        dolphin.launch(state=START_STATE)
    print("Dolphin ready", flush=True)

    pygame.init()
    screen = pygame.display.set_mode((520, 420))
    pygame.display.set_caption("policy")
    clock = pygame.time.Clock()

    controller = PipeController(dolphin.PIPE_PATH)
    env = TanksEnv(dme=dme, controller=controller, encoder=GridEncoder(),
                   levels=args.level)
    model = PPO.load(args.model)
    view = PolicyRender(screen, clock)

    try:
        for episode in range(args.episodes):
            if not view.running:
                break
            obs, info = env.reset()
            done, total, steps = False, 0.0, 0
            while not done and view.running:
                action, _ = model.predict(obs, deterministic=args.deterministic)
                view.draw(action_probabilities(model, obs), action,
                          f"ep {episode}  L{info['level']}  step {steps}  "
                          f"return {total:+.1f}")
                obs, reward, term, trunc, info = env.step(action)
                total += reward
                steps += 1
                done = term or trunc
            print(f"ep {episode}: L{info['level']} steps={steps} "
                  f"return={total:+.1f} outcome={info['outcome']}", flush=True)
    finally:
        env.close()
        pygame.quit()


if __name__ == "__main__":
    main()
