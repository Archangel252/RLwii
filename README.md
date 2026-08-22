# Wii Play Tank AI

Learning project: train an RL agent to play the Tanks minigame from Wii Play,
running in Dolphin. Game logic and RL training are intentionally left as
`# TODO:` stubs to be filled in by hand; RAM addresses are mapped in
`src/memory_map.py` and live reads/writes work via `dolphin-memory-engine`.

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Python lives in `src/`. With Dolphin running and a level loaded:

```
python src/main.py     # live 2D view of game state
```

## `dolphin-memory-engine` on macOS

The package publishes a working macOS arm64 wheel, but by default it can't
hook into Dolphin: `dme.hook()` leaves `is_hooked()` False and
`get_status()` at `notRunning`, even as root. Root cause: macOS requires a
process to carry the `com.apple.security.get-task-allow` code-signing
entitlement before another process can attach to it via `task_for_pid`
(which is how `dolphin-memory-engine` reads Dolphin's RAM) -- SIP blocks
this otherwise, and the Dolphin.app build/install doesn't include that
entitlement.

Re-sign the installed app with that entitlement added:

1. **Grant your terminal app "App Management" permission**: System Settings
   -> Privacy & Security -> App Management -> enable whatever terminal app
   you're running commands from. Without this, `codesign` fails with
   `Operation not permitted` / an internal Code Signing subsystem error when
   it tries to modify `/Applications/Dolphin.app` -- this is a separate
   macOS privacy protection from SIP itself.
2. Quit Dolphin.
3. Re-sign using `dolphin_entitlements.plist` (in this repo -- Dolphin's
   normal entitlements plus `get-task-allow`):
   ```
   codesign --force --deep --sign - --entitlements dolphin_entitlements.plist /Applications/Dolphin.app
   ```
4. Relaunch Dolphin **with a game actually loaded** -- `hook()` needs live
   emulated RAM to attach to, not just the Dolphin process running at its
   main menu (`get_status()` reports `noEmu` until a game is running):
   ```
   open -a /Applications/Dolphin.app --args -e /path/to/game.wbfs
   ```
5. Confirm:
   ```python
   import dolphin_memory_engine as dme
   dme.hook()
   dme.is_hooked()   # -> True
   ```

**This has to be redone after every Dolphin update/reinstall** -- installing
a new build replaces the binary and wipes the custom signature.

## Running fast (training throughput)

The emulator is the bottleneck, and rendering is most of it. Measured on this
machine, same game and level:

| config | speed |
|---|---|
| default | 1.0x (60 fps) |
| `-C Dolphin.Core.EmulationSpeed=0` | 2.0x |
| `+ -v Null` (no rendering) | **10.9x** (655 fps) |

CPU stayed at ~1 core throughout, so the gain is from skipping rendering, not
from more compute. For training:

```
open -a /Applications/Dolphin.app --args \
  -e Games/wii_play.wbfs -s Games/Levels/level1.sav \
  -C Dolphin.Core.EmulationSpeed=0 -v Null
```

Memory reads and pipe input are unaffected, so `src/render.py` still shows
live state -- Dolphin's own window is blank and unnecessary. Drop the flags
when you actually want to watch a policy play.

At frame-skip 4 that's ~164 agent steps/sec, so 1M steps is ~1.7h rather
than ~18h.

**Never mix `time.sleep()` with game timing at these speeds** -- a 12s bomb
fuse elapses in ~1.1s wall clock. Use `env.wait_frames()`, which counts
emulated frames and stays correct at any speed.

Note `-C` is runtime-only and isn't written back to `Dolphin.ini`.

## Save states (level select / episode reset)

Level snapshots live in `Games/Levels/level1..6.sav`. Two ways to load them:

**At launch** -- any state file, no slots involved:

```
open -a /Applications/Dolphin.app --args \
  -e /path/to/Games/wii_play.wbfs \
  -s /path/to/Games/Levels/level1.sav
```

**In-session, over the pipe** -- what `env.reset()` needs, since relaunching
Dolphin per episode is far too slow. Hotkeys can only load numbered *slots*,
not named files, so the `.sav` files are copied into slot files first:

```
cp Games/Levels/level$N.sav ~/Library/Application\ Support/Dolphin/StateSaves/RHAE01.s0$N
```

Then load-state hotkeys are bound to pipe buttons the game doesn't use
(gameplay only uses A, B and the D-pad), in `Config/Hotkeys.ini`:

```
Load State/Load State Slot 1 = F1 | `Pipe/0/test:Button X`
```

so `echo "PRESS X"` into the pipe loads level 1. Slots 1-6 are bound to
X / Y / Z / START / L / R respectively; the `F1`-`F6` keyboard bindings still
work alongside them. Verified: cycling these mid-session switches levels
instantly (`block_count` and tank position both change as expected).

### Scaling past 8 levels

Dolphin only has 8 hotkey slots, but **it re-reads the slot file from disk on
every load** (verified: overwriting `RHAE01.s01` mid-session and loading it
again yields the new level). So any number of levels can share one slot --
copy the wanted `.sav` over the slot file, then press its button. The copy is
~18ms for a 32MB state, so it's not worth optimising.

### Jumping levels without save states

Save states aren't actually needed to reach a level. Two memory writes do it
(see `src/memory_map.py` for the addresses):

```python
dme.write_byte(ADDRESSES["level_index"], target - 2)   # 0-based
dme.write_byte(ADDRESSES["enemies_remaining"], 0)      # triggers transition
```

Zeroing the enemy counter makes the game think the level is cleared; the
transition then increments the index and loads whatever it points at. Works
for levels never visited or saved -- verified on 7, 12, 15, 20, 25 and 30.

Caveats: jump from a settled in-level state (chained jumps land mid-
transition and fail), and confirm with `block_count` rather than re-reading
`level_index`, which is racy immediately after the write.

This makes save states optional -- useful to keep one clean state to jump
*from*, but there's no need to hand-save 30 of them.

### Hotkeys need window focus

Emulated controller input works fine with Dolphin in the background, but
**hotkeys do not** -- `BackgroundInput = True` covers the former, not the
latter, and there's no hotkey-specific equivalent. A load-state press is
silently ignored unless Dolphin is frontmost, so a reset has to activate it
first:

```python
subprocess.run(["osascript", "-e", 'tell application "Dolphin" to activate'])
```

This means an episode reset steals focus. Fine for a dedicated training run
(park Dolphin on its own Space), but worth knowing before wiring up `reset()`.

Note this overwrote `StateSaves/RHAE01.s01`; the original is kept as
`RHAE01.s01.bak`.

## Manual Dolphin-side configuration (not automatable, do by hand)

1. **Pipe Input controller** (for actions):
   - Config -> Controllers -> set the port the game reads (usually Port 1)
     to device `Pipe/0/<name>` (e.g. `Pipe/0/tank-agent`).
   - Dolphin reads named pipes from its user `Pipes/` folder. On macOS:
     `~/Library/Application Support/Dolphin/Pipes/<name>`. Create the
     folder if it doesn't exist.
   - See `src/controller.py` for the command syntax once this is wired up.

2. **RAM addresses**: use Dolphin's built-in Cheat Search (Tools -> Cheats)
   to snapshot memory, change something in-game (tank position, score),
   refine, and narrow down to the real address. Workflow used for this repo:
   - Snapshot memory in a known state, change something in-game, search for
     values that changed/stayed the same as expected, and repeat until one
     address remains. Confirm with a force-write and watch it affect the
     game live.
   - For entities that aren't singletons (bullets, bombs, blocks, enemy
     tanks): these live in fixed-stride arenas, not one fixed address. A
     candidate found from one instance only applies to that instance --
     find the per-slot stride by comparing two simultaneous instances, then
     confirm with a teleport/force-write test on each before trusting it.
   - Dolphin's Tools -> Export -> Dump MRAM/ExRAM writes raw memory to
     `~/Library/Application Support/Dolphin/Dump/mem1.raw` (MEM1, base
     `0x80000000`) and `mem2.raw` (MEM2, base `0x90000000`) -- useful for
     diffing snapshots in a script instead of the GUI search tool.
   - See `src/memory_map.py` for everything found so far.

## Files

- `src/memory_map.py` -- RAM addresses, arena formulas, block-type derivation.
- `src/env.py` -- Gymnasium `Env`. Owns all memory reading and exposes game
  state (`blocks`, `bullets`, `enemy_tanks`, `bombs`, frame counters);
  `reset`/`step`/`get_obs` are still `# TODO:`.
- `src/controller.py` -- Pipe Input wrapper (buttons, stick, validation).
- `src/render.py` -- pygame 2D view; draws whatever `env` exposes.
- `src/main.py` -- entry point for the live viewer.
- `src/train.py` -- empty training entry point stub.
- `Games/` -- game image, level save states, and the pipe bindings reference.
- `dolphin_entitlements.plist` -- entitlements (incl. `get-task-allow`) used
  to re-sign `/Applications/Dolphin.app`; see the macOS hook section above.

## References

- [`vvolhejn/Twentie`](https://github.com/vvolhejn/Twentie) -- Melee AI,
  useful for the general Dolphin-memory-hook + pipe-input pattern.
- [`ENPH-479/dolphin-env-api`](https://github.com/ENPH-479/dolphin-env-api) --
  similar Dolphin-as-Gym-env pattern.
