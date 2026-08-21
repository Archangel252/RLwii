import dolphin_memory_engine as dme
import time
import pygame

from render import GameRender

if __name__ == "__main__":

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()
    # hook onto the dolphin game
    dme.hook()

    render_engine = GameRender(screen=screen, clock=clock, dme=dme)


    if dme.is_hooked():
        print("Hooked into Dolphin")
    else:
        raise RuntimeError("Failed to hook - is Dolphin running with a game loaded?")

    while dme.is_hooked() and render_engine.running:
        render_engine.render_game()
    pygame.quit()
