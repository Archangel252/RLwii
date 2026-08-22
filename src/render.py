import math

import pygame

from src import memory_map

WORLD_SCALE = 1

TANK_RADIUS_WORLD = 15
BULLET_RADIUS_WORLD = 4
BOMB_RADIUS_WORLD = 8

BOMB_COLOR_EARLY = (245, 215, 70)
BOMB_COLOR_LATE = (220, 40, 30)

BLOCK_COLOR_SOLID = "tan"
BLOCK_COLOR_CORK = (198, 124, 106)
BLOCK_COLOR_HOLE = (38, 30, 26)
BLOCK_COLOR_UNKNOWN = "magenta"


class GameRender:
    def __init__(self, screen, clock, env):
        self.running = True
        self.env = env
        self.screen = screen
        self.clock = clock

    def render_game(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

        self.env.poll()

        self.screen.fill("black")

        self._draw_boundary()
        self._draw_blocks()
        self._draw_bombs()
        self._draw_tank()
        self._draw_enemy_tanks()
        self._draw_bullets()

        pygame.display.flip()
        self.clock.tick(60)

    def _draw_boundary(self):
        left, top = self._world_to_screen(-memory_map.LEVEL_BOUND_X, -memory_map.LEVEL_BOUND_Y)
        right, bottom = self._world_to_screen(memory_map.LEVEL_BOUND_X, memory_map.LEVEL_BOUND_Y)
        pygame.draw.rect(self.screen, "white",
                         pygame.Rect(left, top, right - left, bottom - top), width=2)

    def _draw_blocks(self):
        size = int(memory_map.BLOCK_GRID_STEP * WORLD_SCALE)
        for x, y, block_type, solid in self.env.blocks():
            rect = pygame.Rect(0, 0, size, size)
            rect.center = self._world_to_screen(x, y)
            if block_type == memory_map.BLOCK_TYPE_HOLE:
                pygame.draw.ellipse(self.screen, BLOCK_COLOR_HOLE, rect)
            elif block_type == memory_map.BLOCK_TYPE_WALL:
                pygame.draw.rect(self.screen, BLOCK_COLOR_SOLID if solid else BLOCK_COLOR_CORK, rect)
            else:
                pygame.draw.rect(self.screen, BLOCK_COLOR_UNKNOWN, rect)

    def _draw_tank(self):
        x, y = self.env.tank_pos()
        pygame.draw.circle(self.screen, "blue", self._world_to_screen(x, y),
                           int(TANK_RADIUS_WORLD * WORLD_SCALE))

    def _draw_enemy_tanks(self):
        radius = int(TANK_RADIUS_WORLD * WORLD_SCALE)
        for x, y in self.env.enemy_tanks():
            pygame.draw.circle(self.screen, "red", self._world_to_screen(x, y), radius)

    def _draw_bullets(self):
        radius = int(BULLET_RADIUS_WORLD * WORLD_SCALE)
        for x, y in self.env.bullets():
            pygame.draw.circle(self.screen, "red", self._world_to_screen(x, y), radius)

    def _draw_bombs(self):
        radius = int(BOMB_RADIUS_WORLD * WORLD_SCALE)
        for x, y, fuse in self.env.bombs():
            pos = self._world_to_screen(x, y)
            pygame.draw.circle(self.screen, self._fuse_color(fuse), pos, radius)
            pygame.draw.circle(self.screen, "white", pos, radius, width=1)

    @staticmethod
    def _fuse_color(fuse):
        if not math.isfinite(fuse):
            return BOMB_COLOR_LATE
        frac = max(0.0, min(1.0, fuse / memory_map.BOMB_FUSE_SECONDS))
        return tuple(
            int(late + (early - late) * frac)
            for early, late in zip(BOMB_COLOR_EARLY, BOMB_COLOR_LATE)
        )

    def _world_to_screen(self, x, y):
        return (int(self.screen.get_width() // 2 + x * WORLD_SCALE),
                int(self.screen.get_height() // 2 + y * WORLD_SCALE))
