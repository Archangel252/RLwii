import os

import dolphin_memory_engine as dme
import pygame

from controller import PipeController
from env import TanksEnv
from render import GameRender

PIPE_PATH = os.path.expanduser("~/Library/Application Support/Dolphin/Pipes/test")

if __name__ == "__main__":
    dme.hook()
    if not dme.is_hooked():
        raise RuntimeError("Failed to hook - is Dolphin running with a game loaded?")
    print("Hooked into Dolphin")

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    controller = PipeController(PIPE_PATH)
    env = TanksEnv(dme=dme, controller=controller)
    render_engine = GameRender(screen=screen, clock=clock, env=env)

    try:
        while dme.is_hooked() and render_engine.running:
            render_engine.render_game()
    finally:
        env.close()
        pygame.quit()
