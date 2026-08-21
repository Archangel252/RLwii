import math
import struct

import pygame
import memory_map

WORLD_SCALE = 1

TANK_RADIUS_WORLD = 15
BULLET_RADIUS_WORLD = 4
BOMB_RADIUS_WORLD = 8

BOMB_COLOR_EARLY = (245, 215, 70)   # full fuse
BOMB_COLOR_LATE = (220, 40, 30)     # about to detonate

BLOCK_RECHECK_FRAMES = 30       # ~twice a second at 60fps

BLOCK_COLOR_SOLID = "tan"
BLOCK_COLOR_CORK = (198, 124, 106)
BLOCK_COLOR_HOLE = (38, 30, 26)
BLOCK_COLOR_UNKNOWN = "magenta"


class GameRender:
    def __init__(self, screen, clock, dme):
        self.running = True
        self.dme = dme
        self.screen = screen
        self.clock = clock
        self.frames_since_block_check = 0
        self.last_relocate_count = None
        self._refresh_blocks()
        self.last_tank_alive = self.dme.read_word(memory_map.ADDRESSES["tank_alive"])

    def render_game(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

        self._check_respawn()
        self._check_blocks_stale()

        self.screen.fill("black")

        self._draw_boundary()
        self._draw_blocks()
        self._draw_bombs()
        self._draw_tank()
        self._draw_enemy_tanks()
        self._draw_bullets()

        pygame.display.flip()
        self.clock.tick(60)

    def _check_respawn(self):
        # Respawn reallocates the block arena, same as a level change.
        tank_alive = self.dme.read_word(memory_map.ADDRESSES["tank_alive"])
        if tank_alive == 1 and self.last_tank_alive == 0:
            self._refresh_blocks()
        self.last_tank_alive = tank_alive

    def _check_blocks_stale(self):
        # Destruction keeps both counts in sync, so a mismatch means the
        # arena moved (level change). Retry only once per block_count value:
        # a mismatch we can't fix would otherwise re-scan forever.
        self.frames_since_block_check += 1
        if self.frames_since_block_check < BLOCK_RECHECK_FRAMES:
            return
        self.frames_since_block_check = 0

        expected = self.dme.read_word(memory_map.ADDRESSES["block_count"])
        actual = sum(
            1 for base in self.block_slot_addrs
            if self.dme.read_word(base) == memory_map.BLOCK_ACTIVE
        )
        if actual != expected and self.last_relocate_count != expected:
            self.last_relocate_count = expected
            self._refresh_blocks()

    def _refresh_blocks(self):
        self.block_slot_addrs = self._locate_block_slots()
        self.block_colors = self._block_colors()
        self.frames_since_block_check = 0

    def _block_colors(self):
        # Type never changes, so resolve once per locate, not per frame.
        types = memory_map.block_types(self.dme, self.block_slot_addrs)
        colors = {}
        for base in self.block_slot_addrs:
            x = round(self.dme.read_float(base + memory_map.BLOCK_OFF_X), 1)
            y = round(self.dme.read_float(base + memory_map.BLOCK_OFF_Y), 1)
            block_type = types.get((x, y))
            if block_type == memory_map.BLOCK_TYPE_HOLE:
                colors[base] = BLOCK_COLOR_HOLE
            elif block_type == memory_map.BLOCK_TYPE_WALL:
                solid = self.dme.read_word(base + memory_map.BLOCK_OFF_DESTRUCTIBLE)
                colors[base] = BLOCK_COLOR_SOLID if solid else BLOCK_COLOR_CORK
            else:
                colors[base] = BLOCK_COLOR_UNKNOWN
        return colors

    def _draw_boundary(self):
        left, top = self._world_to_screen(-memory_map.LEVEL_BOUND_X, -memory_map.LEVEL_BOUND_Y)
        right, bottom = self._world_to_screen(memory_map.LEVEL_BOUND_X, memory_map.LEVEL_BOUND_Y)
        rect = pygame.Rect(left, top, right - left, bottom - top)
        pygame.draw.rect(self.screen, "white", rect, width=2)

    def _draw_blocks(self):
        block_pixel_size = int(memory_map.BLOCK_GRID_STEP * WORLD_SCALE)
        for base in self.block_slot_addrs:
            if self.dme.read_word(base) != memory_map.BLOCK_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.BLOCK_OFF_X)
            y = self.dme.read_float(base + memory_map.BLOCK_OFF_Y)
            sx, sy = self._world_to_screen(x, y)
            rect = pygame.Rect(0, 0, block_pixel_size, block_pixel_size)
            rect.center = (sx, sy)
            color = self.block_colors.get(base, BLOCK_COLOR_UNKNOWN)
            if color == BLOCK_COLOR_HOLE:
                pygame.draw.ellipse(self.screen, color, rect)
            else:
                pygame.draw.rect(self.screen, color, rect)

    def _draw_tank(self):
        x = self.dme.read_float(memory_map.ADDRESSES["tank_x_pos"])
        y = self.dme.read_float(memory_map.ADDRESSES["tank_y_pos_mem2"])
        sx, sy = self._world_to_screen(x, y)
        radius = int(TANK_RADIUS_WORLD * WORLD_SCALE)
        pygame.draw.circle(self.screen, "blue", (sx, sy), radius)

    def _draw_bullets(self):
        # Fixed-address arena; walking it catches bullets that spawn while
        # others are still airborne.
        radius = int(BULLET_RADIUS_WORLD * WORLD_SCALE)
        for k in range(memory_map.BULLET_SLOT_COUNT):
            base = memory_map.BULLET_ARENA_BASE + k * memory_map.BULLET_ARENA_STRIDE
            if self.dme.read_word(base + memory_map.BULLET_OFF_ACTIVE) != memory_map.BULLET_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.BULLET_OFF_POS_A)
            y = self.dme.read_float(base + memory_map.BULLET_OFF_POS_B)
            if not (math.isfinite(x) and math.isfinite(y)) or (x == 0.0 and y == 0.0):
                continue
            sx, sy = self._world_to_screen(x, y)
            pygame.draw.circle(self.screen, "red", (sx, sy), radius)

    def _draw_enemy_tanks(self):
        # Slots aren't packed: a dead tank leaves a gap with live tanks
        # after it, so never stop at the first inactive slot.
        radius = int(TANK_RADIUS_WORLD * WORLD_SCALE)
        for k in range(memory_map.ENEMY_SLOT_COUNT):
            base = memory_map.ENEMY_ARENA_BASE + k * memory_map.ENEMY_ARENA_STRIDE
            if self.dme.read_word(base) != memory_map.ENEMY_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.ENEMY_OFF_X)
            y = self.dme.read_float(base + memory_map.ENEMY_OFF_Y)
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            sx, sy = self._world_to_screen(x, y)
            pygame.draw.circle(self.screen, "red", (sx, sy), radius)

    def _draw_bombs(self):
        # Fixed-address arena; walking the stride avoids both the unrelated
        # objects nearby and each slot's mirrored active flag at +0x8c.
        radius = int(BOMB_RADIUS_WORLD * WORLD_SCALE)
        for k in range(memory_map.BOMB_SLOT_COUNT):
            base = memory_map.BOMB_ARENA_BASE + k * memory_map.BOMB_ARENA_STRIDE
            if self.dme.read_word(base) != memory_map.BOMB_ACTIVE:
                continue
            x = self.dme.read_float(base + memory_map.BOMB_OFF_X)
            y = self.dme.read_float(base + memory_map.BOMB_OFF_Y)
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            fuse = self.dme.read_float(base + memory_map.BOMB_OFF_FUSE)
            sx, sy = self._world_to_screen(x, y)
            pygame.draw.circle(self.screen, self._fuse_color(fuse), (sx, sy), radius)
            pygame.draw.circle(self.screen, "white", (sx, sy), radius, width=1)

    @staticmethod
    def _fuse_color(timer):
        # Yellow when fresh, red as the fuse runs out.
        if not math.isfinite(timer):
            return BOMB_COLOR_LATE
        frac = max(0.0, min(1.0, timer / memory_map.BOMB_FUSE_SECONDS))
        return tuple(
            int(late + (early - late) * frac)
            for early, late in zip(BOMB_COLOR_EARLY, BOMB_COLOR_LATE)
        )

    def _locate_block_slots(self):
        data = self.dme.read_bytes(memory_map.BLOCK_SCAN_START, memory_map.BLOCK_SCAN_SIZE)
        stride = memory_map.BLOCK_ARENA_STRIDE
        hits = set()
        for off in range(0, len(data) - 4, 4):
            if struct.unpack_from(">I", data, off)[0] == memory_map.BLOCK_ACTIVE:
                hits.add(memory_map.BLOCK_SCAN_START + off)

        MIN_CHAIN_LENGTH = 4
        chains = []
        for h in hits:
            if (h - stride) in hits:
                continue
            chain = [h]
            addr = h + stride
            while addr in hits:
                chain.append(addr)
                addr += stride
            if len(chain) >= MIN_CHAIN_LENGTH:
                chains.append(chain)

        slots = []
        for chain in chains:
            for base in chain:
                x = self.dme.read_float(base + memory_map.BLOCK_OFF_X)
                y = self.dme.read_float(base + memory_map.BLOCK_OFF_Y)
                if math.isfinite(x) and math.isfinite(y) and abs(x) < 1000 and abs(y) < 1000:
                    slots.append(base)

        block_count = self.dme.read_word(memory_map.ADDRESSES["block_count"])
        print(f"located {len(slots)} block slot(s) (block_count reports {block_count})")
        return slots

    def _world_to_screen(self, x, y):
        sx = self.screen.get_width() // 2 + x * WORLD_SCALE
        sy = self.screen.get_height() // 2 + y * WORLD_SCALE
        return int(sx), int(sy)
