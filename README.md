# Wii Play Tank AI

This is my first ML project on a game I was obsessed with as a kid. Wii Play was one of my favorite video games specifically the Tank Game. I wanted to get an intro into ML and I figured this would be a good start. Most used Claude Code to assist in mapping the memory (bc that part stinks manually) but the game is being run on Dolphin emulator and we are able to use the python package and hook into the live game and read from the memory addresses to get all the state we need. We are feeding the state into the ML model and the taking the actions and Piping them through back to Dolphin to process the inputs. There is also a very poor pygame rendered version of the state for viewing while training beacuse we are able to increase frames 11x if we run dolphin headless. 

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
## Model specifics

## Results
