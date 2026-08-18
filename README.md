# Wii Play Tank AI

Learning project: train an RL agent to play the Tanks minigame from Wii Play,
running in Dolphin. Game logic and RL training are intentionally left as
`# TODO:` stubs to be filled in by hand; RAM addresses are mapped in
`memory_map.py` and live reads/writes work via `dolphin-memory-engine`.

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python smoke_test.py   # sanity check, doesn't need Dolphin running
```

## `dolphin-memory-engine` on macOS -- SOLVED

The package publishes a working macOS arm64 wheel, but by default it can't
hook into Dolphin: `dme.hook()` leaves `is_hooked()` False and
`get_status()` at `notRunning`, even as root. Root cause: macOS requires a
process to carry the `com.apple.security.get-task-allow` code-signing
entitlement before another process can attach to it via `task_for_pid`
(which is how `dolphin-memory-engine` reads Dolphin's RAM) -- SIP blocks
this otherwise, and the Dolphin.app build/install doesn't include that
entitlement.

Fix -- re-sign the installed app with that entitlement added:

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

## Manual Dolphin-side configuration (not automatable, do by hand)

1. **Pipe Input controller** (for actions):
   - Config -> Controllers -> set the port the game reads (usually Port 1)
     to device `Pipe/0/<name>` (e.g. `Pipe/0/tank-agent`).
   - Dolphin reads named pipes from its user `Pipes/` folder. On macOS:
     `~/Library/Application Support/Dolphin/Pipes/<name>`. Create the
     folder if it doesn't exist.
   - See `controller.py` for the command syntax once this is wired up.

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
   - See `memory_map.py` for everything found so far.

## Files

- `env.py` -- Gymnasium `Env` skeleton (`reset`/`step`/`get_obs`), bodies
  are all `# TODO:`.
- `memory_map.py` -- RAM addresses and arena formulas found so far.
- `controller.py` -- Pipe Input wrapper skeleton.
- `train.py` -- empty training entry point stub.
- `smoke_test.py` -- confirms the venv and skeleton modules import cleanly.
  Does not require Dolphin.
- `dolphin_entitlements.plist` -- entitlements (incl. `get-task-allow`) used
  to re-sign `/Applications/Dolphin.app`; see the macOS hook section above.

## References

- [`vvolhejn/Twentie`](https://github.com/vvolhejn/Twentie) -- Melee AI,
  useful for the general Dolphin-memory-hook + pipe-input pattern.
- [`ENPH-479/dolphin-env-api`](https://github.com/ENPH-479/dolphin-env-api) --
  similar Dolphin-as-Gym-env pattern.
