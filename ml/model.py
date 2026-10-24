"""Small CNN for up-call classification.

3 conv blocks -> global average pooling -> linear head (single logit).
Intentionally small so it trains in a few epochs on CPU/MPS.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class UpCallCNN(nn.Module):
    def __init__(self, n_mels: int = 48) -> None:
        super().__init__()

        def block(cin: int, cout: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv2d(cin, cout, kernel_size=3, padding=1),
                nn.BatchNorm2d(cout),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
            )

        self.features = nn.Sequential(
            block(1, 16),
            block(16, 32),
            block(32, 64),
        )
        self.pool = nn.AdaptiveAvgPool2d(1)  # global pooling
        self.head = nn.Linear(64, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, 1, n_mels, frames)
        x = self.features(x)
        x = self.pool(x).flatten(1)
        return self.head(x).squeeze(1)  # (batch,) logits
