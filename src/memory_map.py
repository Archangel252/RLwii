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
    # READ-ONLY in practice: a write lands but is recomputed back within
    # ~12 frames, so the tank cannot be teleported through these. MEM1 and
    # MEM2 y also hold genuinely different values (44.9 vs -70.0 observed
    # simultaneously), so they are not two copies of one coordinate.
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
    "level_index": 0x91D27FFF,          # byte, 0-based (level 1 reads 0)
    "enemies_remaining": 0x91CFAB8B,    # byte; writing 0 completes the level
    "frame_counter": 0x8043BFD4,        # word, +1/frame, survives level loads
}

# Verified at exactly +1 per frame, 59.9/s, no irregular steps. Use it to pace
# steps -- wall-clock sleeps drift once emulation speed is uncapped.
# Equivalent global mirrors: 0x8043C064, 0x804D1CFC, 0x804D1D54.
#
# 0x80B19D4C looked like a per-level counter (reset on level load) but is NOT
# one: it ticks ~25/s, not 60, and was seen going backwards. Track episode
# length by counting steps in Python instead.

# Level jumping, no save states needed. Writing "level_index" alone does
# nothing -- geometry only loads on a level transition -- but zeroing
# "enemies_remaining" triggers one, and the transition increments the index
# and loads whatever it lands on. So:
#
#     write level_index = target - 2
#     write enemies_remaining = 0      -> transition loads `target`
#
# Verified on levels never visited or saved (7, 12, 15, 20, 25, 30). Confirm
# with "block_count" rather than re-reading level_index, which is racy right
# after the write. Jump from a settled in-level state; chaining jumps
# back-to-back lands mid-transition and silently fails.
#
# Mirrors that are NOT authoritative: 0x91D27EF3 / 0x91D28537 (level, 1-based)
# and 0x91D27EFF (enemy count). Writing those alone advances by one level
# instead of jumping, or does nothing.
#
# Note the enemy arena's own active flags are effects, not causes -- zeroing
# them removes tanks from a scan but never completes the level.

# Bullets: fixed-stride arena, not a fixed address.
BULLET_ARENA_BASE = 0x91D0F7AC              # pos_a of slot 0
BULLET_ARENA_STRIDE = 0x710
BULLET_OFF_POS_A = 0x0                      # float
BULLET_OFF_POS_B = 0x8                      # float
BULLET_OFF_ACTIVE = 0x3C                    # word
BULLET_ACTIVE = 0x01000000
BULLET_SLOT_COUNT = 31                      # k=0..30; k=31 is unrelated memory

# NOTE: unlike the block arena this one does NOT move -- every bullet seen
# across every level this session landed on this exact stride grid, so slots
# can just be walked directly. Reading only BULLET_OFF_ACTIVE at each stride
# step also sidesteps the duplicate mirror copies living at sub-offsets
# inside each slot, which is what made diff-based detection misfire.
# ADDRESSES["active_bullet_count"] has been seen reading one higher than the
# number of real bullets -- don't use it as ground truth; trust this scan.
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
# Not health -- a per-block frame counter ticking +1/frame since the block
# spawned, set to -999 on destruction. (Every block's +0x60 showed up in the
# frame-counter search, spaced one BLOCK_ARENA_STRIDE apart.) Its value is
# just time-since-level-load, which is why it differs on every load.
BLOCK_OFF_AGE_FRAMES = 0x60                 # word; -999 once destroyed
BLOCK_AGE_DEAD = -999
BLOCK_OFF_DESTROYED = 0x108                 # word, 0 intact -> 0x01000000

# Struct actually starts at -0x40; its first word is a C++ vtable pointer.
# Ruled OUT as a type discriminator -- holes, cork and solid walls all share
# vtable 0x8035B684, so they're one class and type must be a data field.
BLOCK_OFF_VTABLE = -0x40

# NEIGHBOUR-type table, in directions (up, right, down, left) where up is
# -Y. Each entry is the type of the ADJACENT block in that direction, NOT
# this block's own type -- there appears to be no own-type field anywhere in
# the struct (whole 0x564 range was swept). Used by the game for edge/render
# variants, which is why these look like positional noise at a glance.
#   0 = no block there, 1 = hole, 2 = wall (cork and solid both read 2)
# Derive a block's own type by asking any neighbour what it sees in this
# block's direction -- see block_types() below. Matters for RL: bullets
# cross holes but are blocked by walls.
BLOCK_OFF_NEIGHBOUR_TYPE = (0xF8, 0xFC, 0x100, 0x104)
BLOCK_TYPE_EMPTY = 0
BLOCK_TYPE_HOLE = 1
BLOCK_TYPE_WALL = 2

# (dx, dy) to a neighbour, paired with the index of the neighbour's field
# that points back at us. Grid step is BLOCK_GRID_STEP.
BLOCK_NEIGHBOUR_PROBES = (
    ((0, -1), 2),   # neighbour above -- its "down" entry describes us
    ((1, 0), 3),    # neighbour right -- its "left" entry
    ((0, 1), 0),    # neighbour below -- its "up" entry
    ((-1, 0), 1),   # neighbour left  -- its "right" entry
)


def block_types(dme, slot_addrs):
    """Map {(x, y): type} for each block, derived from neighbour tables.

    Verified on a holes+walls level: 28 walls / 10 holes, no conflicts.
    A block with no occupied neighbour can't be typed this way and is
    omitted -- possible in principle, not seen in any level so far.
    """
    step = BLOCK_GRID_STEP
    table = {}
    for base in slot_addrs:
        x = round(dme.read_float(base + BLOCK_OFF_X), 1)
        y = round(dme.read_float(base + BLOCK_OFF_Y), 1)
        table[(x, y)] = [dme.read_word(base + o) for o in BLOCK_OFF_NEIGHBOUR_TYPE]

    types = {}
    for (x, y) in table:
        votes = set()
        for (dx, dy), back in BLOCK_NEIGHBOUR_PROBES:
            neighbour = table.get((round(x + dx * step, 1), round(y + dy * step, 1)))
            if neighbour and neighbour[back] != BLOCK_TYPE_EMPTY:
                votes.add(neighbour[back])
        if len(votes) == 1:
            types[(x, y)] = votes.pop()
    return types

# Bombs: fixed-address arena like bullets, starting just past the bullet
# arena's end. Offsets are relative to the ACTIVE flag, and x/y sit at the
# same -0x3c/-0x34 the block and enemy arenas use.
# Do NOT region-scan for BOMB_ACTIVE: ~7 unrelated objects nearby match the
# signature even with no bomb placed, and each slot mirrors its active flag
# again at +0x8c. Walking the stride and reading only +0x0 avoids both.
BOMB_ARENA_BASE = 0x91D1D378                # active flag of slot 0
BOMB_ARENA_STRIDE = 0x8BC
BOMB_SLOT_COUNT = 16                        # k=0..15; k=16 is unrelated memory
BOMB_ACTIVE = 0x01000000
BOMB_OFF_X = -0x3C                          # float
BOMB_OFF_Y = -0x34                          # float
BOMB_OFF_FUSE = 0x50                        # float, 12.0 at placement
BOMB_FUSE_SECONDS = 12.0

# Inactive slots keep stale values here (1.0 if never used, otherwise the
# last bomb's), so only trust these fields when the slot is active.

# Multiple enemy tanks: ADDRESSES["enemy_tank_x/y_pos"] is slot 0 of this
# arena. Slot count varies per level/session -- rescan for BLOCK_ACTIVE-style
# hits rather than assuming a fixed count.
ENEMY_ARENA_BASE = 0x91CFDDC0               # active flag of slot 0
ENEMY_ARENA_STRIDE = 0x18C8
ENEMY_ACTIVE = 0x01000000                   # word
ENEMY_OFF_X = -0x3C                         # float
ENEMY_OFF_Y = -0x34                         # float
ENEMY_SLOT_COUNT = 8                        # k=0..7; k=8+ is unrelated memory

# Slots are NOT packed -- a dead tank leaves an inactive gap with live tanks
# after it, so always walk the full range and skip inactive slots rather
# than stopping at the first one.

# Level boundary -- confirmed by driving the tank to each edge and reading
# its stopped world position (not derived from block data; no address for
# this, it's just the measured drivable extent). Varies per level like
# everything else here -- this is one measured example, not a constant.
LEVEL_BOUND_X = 369.0
LEVEL_BOUND_Y = 281.5

# Memory scan regions, for locating an arena's current address at runtime
# (see README.md). All entity arenas live in MEM2.
MEM2_START = 0x90000000
MEM2_SIZE = 0x04000000

BLOCK_SCAN_START = MEM2_START
BLOCK_SCAN_SIZE = MEM2_SIZE

