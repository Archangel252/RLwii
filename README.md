# Wii Play Tank AI

This is my first ML project on a game I was obsessed with as a kid. Wii Play was one of my favorite video games specifically the Tank Game. I wanted to get an intro into ML and I figured this would be a good start. Most used Claude Code to assist in mapping the memory (bc that part stinks manually) but the game is being run on Dolphin emulator and we are able to use the python package and hook into the live game and read from the memory addresses to get all the state we need. We are feeding the state into the ML model and the taking the actions and Piping them through back to Dolphin to process the inputs. There is also a very poor pygame rendered version of the state for viewing while training beacuse we are able to increase frames 11x if we run dolphin headless. 

## Dolphin setup gotchas

Two settings in `Dolphin.ini` that are not obvious and cost a lot of time:

- `[Input] BackgroundInput = True` -- lets the emulated controller receive
  piped input while Dolphin is not the frontmost window.
- `[General] HotkeysRequireFocus = False` -- does the same for *hotkeys*,
  which are separate. Save-state loading is a hotkey, so without this every
  episode reset had to steal window focus and the machine was unusable while
  training. Also the reason `dolphin-emu-nogui` can't be used: its main loop
  has no hotkey polling at all, so states can never be loaded there.

## First try

After watching some youtube the strategy is to train a Proximal Policy Optimization model with a CNN policy archetecture to take in the state at each state

For the reward function we are doing is below:

┌───────────────────────────────┬────────┐
│           situation           │ reward │
├───────────────────────────────┼────────┤
│ alive, no threat              │ +0.002 │
├───────────────────────────────┼────────┤
│ bullet 35 units away (1 cell) │ −0.023 │
├───────────────────────────────┼────────┤
│ bullet 7 units away           │ −0.043 │
├───────────────────────────────┼────────┤
│ kill                          │ +1.002 │
├───────────────────────────────┼────────┤
│ final kill + clear            │ +6.002 │
├───────────────────────────────┼────────┤
│ death                         │ −5.000 │
└───────────────────────────────┴────────┘

We are also cycling in harder levels in more often to train it more on the ones it is bad at.

## Second try

The first reward function accidentally taught the model to hide. Hiding for a full episode scored +4.0, which is almost as good as winning (+6.0) and much better than trying and dying (-5.0), so on any level it couldn't reliably beat, not engaging was the correct play. Rebalanced so that engaging pays:

┌────────────────┬───────────┬───────────┐
│                │    old    │    new    │
├────────────────┼───────────┼───────────┤
│ survival bonus │ +0.002/st │  removed  │
├────────────────┼───────────┼───────────┤
│ time cost      │     —     │ −0.002/st │
├────────────────┼───────────┼───────────┤
│ kill           │     +1    │     +2    │
├────────────────┼───────────┼───────────┤
│ clear          │     +5    │    +10    │
├────────────────┼───────────┼───────────┤
│ death          │     −5    │     −2    │
├────────────────┼───────────┼───────────┤
│ danger penalty │ −0.05×thr │ −0.02×thr │
└────────────────┴───────────┴───────────┘

Death got *less* punishing on purpose -- dying already ends the episode and forfeits all future reward, so an extra -5 on top just made it refuse to take any risk. Now clearing level 2 is worth +12 against -2 for dying, and hiding for a full episode scores -4.0 instead of +4.0.

## Model specifics

## Results

First run was 50k steps (~6.5 hours) training on levels 2, 3 and 4, holding out 5 and 6. It learned exactly one level: level 2 clears 6/8 deterministically (+3.39 mean return), while every other level -- trained or held out -- clears 0/8. Deterministic beat stochastic everywhere, so the gap is a real generalization failure rather than an eval artifact. The failure mode is visible in the episode lengths: on levels it can't beat it survives 30-73 steps and then dies without killing anything, which looks like the +0.002/step survival bonus teaching it to hide instead of fight.
