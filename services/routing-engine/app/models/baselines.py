"""Research baseline models for traffic speed forecasting in CATRS.

Includes:
1. Historical Mean (profile baseline)
2. Persistence (last-step identity baseline)
3. Linear Regression (lookback-to-horizon linear mapping)
4. MLP (fully-connected multi-horizon mapping)
5. GRU (pure temporal recurrent model, no spatial graph convolution)
6. GCN (pure spatial graph convolution, no temporal recurrent dynamics)
7. SpatioTemporalGNN (proposed integrated architecture)
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np
import torch
import torch.nn as nn

from app.models.st_gnn import GraphConvolution, SpatioTemporalGNN


class HistoricalMeanModel:
    """Predicts historical baseline speed for all future horizons."""

    def __init__(self, baseline_channel_idx: int = 3) -> None:
        self.baseline_channel_idx = baseline_channel_idx

    def predict(self, x: np.ndarray | torch.Tensor) -> np.ndarray:
        """Args:
            x: Input array/tensor of shape [B, T, N, F].

        Returns:
            y_pred: Predictions of shape [B, N, 3].
        """
        if isinstance(x, torch.Tensor):
            x = x.detach().cpu().numpy()
        # Lookback last step baseline speed
        baseline = x[:, -1, :, self.baseline_channel_idx]  # [B, N]
        return np.repeat(baseline[:, :, np.newaxis], 3, axis=-1)


class PersistenceModel:
    """Predicts current observed speed for all future horizons (naive persistence)."""

    def __init__(self, speed_channel_idx: int = 0) -> None:
        self.speed_channel_idx = speed_channel_idx

    def predict(self, x: np.ndarray | torch.Tensor) -> np.ndarray:
        """Args:
            x: Input array/tensor of shape [B, T, N, F].

        Returns:
            y_pred: Predictions of shape [B, N, 3].
        """
        if isinstance(x, torch.Tensor):
            x = x.detach().cpu().numpy()
        last_speed = x[:, -1, :, self.speed_channel_idx]  # [B, N]
        return np.repeat(last_speed[:, :, np.newaxis], 3, axis=-1)


class LinearRegressionModel:
    """Ordinary least squares / Ridge mapping 12 historical speeds to 3 horizon speeds."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.weights: np.ndarray | None = None  # [13, 3] (12 lookback + 1 bias)

    def fit(self, x_train: np.ndarray, y_train: np.ndarray) -> LinearRegressionModel:
        """Args:
            x_train: [B, T, N, F]
            y_train: [B, N, 3]
        """
        B, T, N, F = x_train.shape
        # Flatten across batch and nodes: [B * N, T]
        x_flat = x_train[:, :, :, 0].transpose(0, 2, 1).reshape(-1, T)  # [B * N, 12]
        y_flat = y_train.reshape(-1, 3)                                 # [B * N, 3]

        # Add bias column
        bias = np.ones((x_flat.shape[0], 1), dtype=np.float32)
        X_design = np.hstack([x_flat, bias])  # [B * N, 13]

        # Closed-form Ridge: (X^T X + alpha * I)^-1 X^T Y
        reg = self.alpha * np.eye(X_design.shape[1], dtype=np.float32)
        reg[-1, -1] = 0.0  # do not penalize bias
        self.weights = np.linalg.solve(X_design.T @ X_design + reg, X_design.T @ y_flat)
        return self

    def predict(self, x: np.ndarray | torch.Tensor) -> np.ndarray:
        """Args:
            x: [B, T, N, F]

        Returns:
            [B, N, 3]
        """
        if isinstance(x, torch.Tensor):
            x = x.detach().cpu().numpy()
        B, T, N, F = x.shape
        if self.weights is None:
            # Fallback to persistence
            return np.repeat(x[:, -1, :, 0, np.newaxis], 3, axis=-1)
        x_flat = x[:, :, :, 0].transpose(0, 2, 1).reshape(-1, T)  # [B * N, 12]
        bias = np.ones((x_flat.shape[0], 1), dtype=np.float32)
        X_design = np.hstack([x_flat, bias])
        y_pred = X_design @ self.weights  # [B * N, 3]
        return y_pred.reshape(B, N, 3)


class GRUModel(nn.Module):
    """Pure temporal recurrent model without spatial graph convolution.

    Ablation: removes GCN spatial message passing.
    """

    def __init__(
        self,
        feature_count: int,
        hidden_size: int = 32,
        num_horizons: int = 3,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.num_horizons = num_horizons
        self.proj = nn.Linear(feature_count, hidden_size)
        self.temporal = nn.GRU(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True,
        )
        self.head = nn.Linear(hidden_size, num_horizons)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, adj_mx: torch.Tensor | None = None) -> torch.Tensor:
        """Args:
            x: [B, T, N, F]
        """
        B, T, N, F = x.shape
        # Flatten nodes into batch: [B * N, T, F]
        node_seqs = x.permute(0, 2, 1, 3).contiguous().view(B * N, T, F)
        h = self.dropout(torch.relu(self.proj(node_seqs)))
        _, h_n = self.temporal(h)  # [B * N, hidden_size]
        out = self.head(h_n[-1])   # [B * N, 3]
        return out.view(B, N, self.num_horizons)


class GCNModel(nn.Module):
    """Pure spatial Graph Convolutional Network without recurrent temporal modeling.

    Ablation: removes GRU temporal recurrence.
    """

    def __init__(
        self,
        feature_count: int,
        hidden_size: int = 32,
        num_horizons: int = 3,
        dropout: float = 0.1,
        adj_mx: torch.Tensor | np.ndarray | None = None,
    ) -> None:
        super().__init__()
        self.hidden_size = hidden_size
        self.num_horizons = num_horizons
        # Flattens T*F or projects last step
        self.gcn1 = GraphConvolution(feature_count, hidden_size)
        self.gcn2 = GraphConvolution(hidden_size, hidden_size)
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(hidden_size, num_horizons)

        if adj_mx is not None:
            if isinstance(adj_mx, np.ndarray):
                adj_tensor = torch.from_numpy(adj_mx).float()
            else:
                adj_tensor = adj_mx.float()
            self.register_buffer("adj_hat", adj_tensor)
        else:
            self.adj_hat = None

    def _get_adj(self, x: torch.Tensor, custom_adj: torch.Tensor | None = None) -> torch.Tensor:
        if custom_adj is not None:
            return custom_adj
        if self.adj_hat is not None and self.adj_hat.shape[0] == x.shape[2]:
            return self.adj_hat
        N = x.shape[2]
        return torch.eye(N, dtype=torch.float32, device=x.device)

    def forward(self, x: torch.Tensor, adj_mx: torch.Tensor | None = None) -> torch.Tensor:
        """Args:
            x: [B, T, N, F]
        """
        B, T, N, F = x.shape
        adj = self._get_adj(x, adj_mx)
        # Spatial convolution on the most recent frame: [B, 1, N, F]
        last_frame = x[:, -1:, :, :]
        h1 = self.dropout(self.activation(self.gcn1(last_frame, adj)))
        h2 = self.activation(self.gcn2(h1, adj))  # [B, 1, N, hidden_size]
        h2 = h2.squeeze(1)  # [B, N, hidden_size]
        out = self.head(h2)  # [B, N, 3]
        return out
