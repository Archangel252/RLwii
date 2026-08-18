"""
RAM address map for Wii Play Tanks (Dolphin, game ID RHAE01).

See README.md for how these were found and how to read them live via
dolphin-memory-engine.

Addresses are virtual addresses as Dolphin exposes them. Two RAM pools:
    MEM1: 0x80000000 - 0x817FFFFF (24MB)
    MEM2: 0x90000000 - 0x93FFFFFF (64MB)

Coordinate system (blocks/tanks/bullets/bombs all share it): grid step 35.0,
X spans -367.5..367.5, Y spans -175.0..175.0.
"""

ADDRESSES: dict[str, int] = {
    "score": 0x91D28100,                # word
    "tank_y_pos": 0x815EAE98,           # float, MEM1 copy
    "tank_x_pos": 0x921EC84C,           # float, MEM2
    "tank_y_pos_mem2": 0x921EC86C,      # float, MEM2 -- prefer over
                                         # tank_y_pos when comparing against
                                         # blocks/bullets/bombs (same pool)
    "active_bullet_count": 0x91D0EFC0,  # word
    "block_count": 0x91C0CFDC,          # word, live block count
    "tank_alive": 0x91CFACA4,           # word, 1=alive, 0=dead. Read-only.
    "lives_remaining": 0x91D281FC,      # word. Feeds loading screen only,
                                         # not the in-level HUD.
    "enemy_tank_x_pos": 0x91CFDD84,     # float, enemy arena slot 0
    "enemy_tank_y_pos": 0x91CFDD8C,     # float, enemy arena slot 0
}

# Bullets: fixed-stride arena, not a fixed address.
BULLET_ARENA_BASE = 0x91D0F7AC              # pos_a of slot 0
BULLET_ARENA_STRIDE = 0x710
BULLET_OFF_POS_A = 0x0                      # float
BULLET_OFF_POS_B = 0x8                      # float
BULLET_OFF_ACTIVE = 0x3C                    # word, 0x01000000 = active
BULLET_OFF_VELOCITY = 0x4C                  # float
BULLET_OFF_BOUNCES_REMAINING = 0xAC         # word
BULLET_OFF_BOUNCES_USED = 0x184             # word

# Blocks/obstacles: fixed-stride entity arena (not a tilemap).
BLOCK_ARENA_BASE = 0x91C0D44C               # active flag of slot 0
BLOCK_ARENA_STRIDE = 0x564
BLOCK_SLOT_COUNT = 34                       # level 1; read "block_count"
                                             # for the live value
BLOCK_ACTIVE = 0x01000000                   # word; 0 once destroyed
BLOCK_OFF_X = -0x3C                         # float
BLOCK_OFF_Y = -0x34                         # float
BLOCK_OFF_DESTRUCTIBLE = 0x70               # word, 0 = destructible (cork),
                                             # 1 = solid
BLOCK_GRID_STEP = 35.0
BLOCK_OFF_HEALTH = 0x60                     # word, 3498 intact -> -999 dead
BLOCK_OFF_DESTROYED = 0x108                 # word, 0 intact -> 0x01000000
BLOCK_HEALTH_INTACT = 3498

# Bombs: fixed-stride entity arena, smaller slot than bullets. Must be
# re-found per instance -- search for BOMB_ACTIVE near 0x91d1c000-0x91d20000.
BOMB_ARENA_STRIDE = 0x50
BOMB_ACTIVE = 0x01000000
BOMB_OFF_TIMER = 0x0                        # float, fuse countdown
BOMB_OFF_ACTIVE = 0x40                      # word
BOMB_OFF_X = 0x4                            # float
BOMB_OFF_Y = 0xC                            # float

# Multiple enemy tanks: ADDRESSES["enemy_tank_x/y_pos"] is slot 0 of this
# arena. Slot count varies per level/session -- rescan for BLOCK_ACTIVE-style
# hits rather than assuming a fixed count.
ENEMY_ARENA_BASE = 0x91CFDDC0               # active flag of slot 0
ENEMY_ARENA_STRIDE = 0x18C8
ENEMY_ACTIVE = 0x01000000                   # word
ENEMY_OFF_X = -0x3C                         # float
ENEMY_OFF_Y = -0x34                         # float
