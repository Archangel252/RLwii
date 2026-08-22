"""Live view of the policy's action distribution.

One bar group per action dimension; the chosen action is highlighted. Shows
what the model is actually deciding, which the game view can't.
"""

import numpy as np
import pygame

BG = (18, 18, 22)
BAR = (70, 110, 190)
BAR_PICKED = (240, 180, 60)
TEXT = (225, 225, 230)
MUTED = (130, 130, 145)

DIMENSION_LABELS = ["move", "fire", "bomb", "aim x", "aim y"]
TICK_LABELS = [
    ["-", "up", "dn", "lf", "rt"],
    ["no", "yes"],
    ["no", "yes"],
    None,
    None,
]

ROW_H = 74
PAD = 14
LABEL_W = 62


class PolicyRender:
    def __init__(self, screen, clock, font=None):
        self.running = True
        self.screen = screen
        self.clock = clock
        self.font = font or pygame.font.SysFont("menlo,monospace", 13)
        self.small = pygame.font.SysFont("menlo,monospace", 10)
        self.status = ""

    def draw(self, probs, action, status=""):
        """probs: list of arrays, one per action dimension."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

        self.screen.fill(BG)
        width = self.screen.get_width()

        for dim, dist in enumerate(probs):
            top = PAD + dim * ROW_H
            self._label(DIMENSION_LABELS[dim], PAD, top + ROW_H // 3)

            picked = int(action[dim])
            n = len(dist)
            avail = width - LABEL_W - 2 * PAD
            slot = avail / n
            bar_w = max(6, slot * 0.7)

            for i, p in enumerate(dist):
                x = LABEL_W + PAD + i * slot
                h = int(p * (ROW_H - 34))
                colour = BAR_PICKED if i == picked else BAR
                pygame.draw.rect(
                    self.screen, colour,
                    pygame.Rect(x, top + (ROW_H - 34) - h, bar_w, h))
                # probability, and a tick label where the option has a name
                self._tiny(f"{p:.2f}", x, top + ROW_H - 32,
                           TEXT if i == picked else MUTED)
                ticks = TICK_LABELS[dim]
                name = ticks[i] if ticks else str(i)
                self._tiny(name, x, top + ROW_H - 20,
                           TEXT if i == picked else MUTED)

        if status:
            self._label(status, PAD, self.screen.get_height() - 20)

        pygame.display.flip()
        self.clock.tick(30)

    def _label(self, text, x, y, colour=TEXT):
        self.screen.blit(self.font.render(text, True, colour), (x, y))

    def _tiny(self, text, x, y, colour=MUTED):
        self.screen.blit(self.small.render(text, True, colour), (x, y))


def action_probabilities(model, obs):
    """Per-dimension probabilities from an SB3 MultiDiscrete policy."""
    obs_tensor, _ = model.policy.obs_to_tensor(obs)
    distribution = model.policy.get_distribution(obs_tensor)
    return [d.probs.detach().cpu().numpy()[0]
            for d in distribution.distribution]
