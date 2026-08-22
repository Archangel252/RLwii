"""Feature extractor for the grid observation.

SB3's default NatureCNN assumes Atari-sized frames (84x84) and its stride-4
convolutions collapse a 17x22 grid to nothing, so it needs replacing with
something that keeps the resolution.
"""

import torch as th
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from torch import nn


class SmallGridCNN(BaseFeaturesExtractor):
    def __init__(self, observation_space, features_dim=256):
        super().__init__(observation_space, features_dim)
        channels = observation_space.shape[0]
        # stride 1, padded: every cell keeps its own position, which matters
        # because a single cell is one whole tank/bullet.
        self.cnn = nn.Sequential(
            nn.Conv2d(channels, 32, kernel_size=3, padding=1), nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, padding=1), nn.ReLU(),
            nn.Conv2d(64, 64, kernel_size=3, padding=1), nn.ReLU(),
            nn.Flatten(),
        )
        with th.no_grad():
            n_flat = self.cnn(th.zeros(1, *observation_space.shape)).shape[1]
        self.linear = nn.Sequential(nn.Linear(n_flat, features_dim), nn.ReLU())

    def forward(self, observations: th.Tensor) -> th.Tensor:
        return self.linear(self.cnn(observations))


# Observations are already float32 in [0, 1], so SB3's uint8 /255 rescale
# must be disabled or everything gets divided into near-zero.
POLICY_KWARGS = dict(
    features_extractor_class=SmallGridCNN,
    features_extractor_kwargs=dict(features_dim=256),
    normalize_images=False,
)
