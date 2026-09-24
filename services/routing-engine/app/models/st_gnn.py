"""Spatio-Temporal Graph Neural Network (ST-GNN) for multi-horizon traffic forecasting.

Combines spatial message passing via Graph Convolution (GCN) with recurrent
temporal modeling (GRU) to predict node-level traffic speeds across 5m, 15m, and 30m horizons.
"""
from __future__ import annotations

import math
from typing import Any
import numpy as np
import torch
from torch import nn


class GraphConvolution(nn.Module):
    """Spatial Graph Convolutional layer: H' = sigma(A_hat * H * W + b).

    Propagates information across graph edges using the normalized adjacency matrix.
    Supports dynamic node counts without parameter retraining.
    """

    def __init__(self, in_features: int, out_features: int, bias: bool = True) -> None:
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.weight = nn.Parameter(torch.FloatTensor(in_features, out_features))
        if bias:
            self.bias = nn.Parameter(torch.FloatTensor(out_features))
        else:
            self.register_parameter("bias", None)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        stdv = 1.0 / math.sqrt(self.weight.size(1))
        self.weight.data.uniform_(-stdv, stdv)
        if self.bias is not None:
            self.bias.data.uniform_(-stdv, stdv)

    def forward(self, x: torch.Tensor, adj_hat: torch.Tensor) -> torch.Tensor:
        """Forward pass for Graph Convolution.

        Args:
            x: Input tensor of shape [B, T, N, in_features] or [B, N, in_features].
            adj_hat: Normalized adjacency matrix of shape [N, N].

        Returns:
            Output tensor of shape [B, T, N, out_features] or [B, N, out_features].
        """
        # Linear transform: [..., in_features] @ [in_features, out_features] -> [..., out_features]
        support = torch.matmul(x, self.weight)

        # Graph spatial propagation along node axis (N):
        # adj_hat [N, N], support [B, T, N, out_features]
        if support.dim() == 4:
            # Broadcast adj across batch and time dimensions: [1, 1, N, N] @ [B, T, N, F_out]
            adj_4d = adj_hat.unsqueeze(0).unsqueeze(0)
            output = torch.matmul(adj_4d, support)
        elif support.dim() == 3:
            # support is [B, N, out_features]: [1, N, N] @ [B, N, F_out]
            adj_3d = adj_hat.unsqueeze(0)
            output = torch.matmul(adj_3d, support)
        else:
            raise ValueError(f"Expected 3D or 4D tensor for GCN, got shape {support.shape}")

        if self.bias is not None:
            output = output + self.bias
        return output


class SpatioTemporalGNN(nn.Module):
    """Architecture: Spatial Graph Convolution -> Temporal GRU -> Node-Level Prediction Head.

    Input shape:  [B, T=12, N, F]
    Output shape: [B, N, 3] (node-level speeds for 5m, 15m, 30m horizons)
    """

    def __init__(
        self,
        feature_count: int,
        hidden_size: int = 32,
        gcn_hidden: int = 32,
        num_horizons: int = 3,
        dropout: float = 0.1,
        adj_mx: torch.Tensor | np.ndarray | None = None,
        node_count: int | None = None,
        num_nodes: int | None = None,
    ) -> None:
        super().__init__()
        self.feature_count = feature_count
        self.hidden_size = hidden_size
        self.gcn_hidden = gcn_hidden
        self.num_horizons = num_horizons
        self.node_count = node_count or num_nodes

        # 1. Spatial GCN Layers
        self.gcn1 = GraphConvolution(feature_count, gcn_hidden)
        self.gcn2 = GraphConvolution(gcn_hidden, gcn_hidden)
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

        # 2. Temporal Recurrent Layer
        # Processes sequences of spatial node states [B*N, T, gcn_hidden]
        self.temporal = nn.GRU(
            input_size=gcn_hidden,
            hidden_size=hidden_size,
            num_layers=1,
            batch_first=True,
        )

        # 3. Node-Level Multi-Horizon Output Head
        self.head = nn.Linear(hidden_size, num_horizons)

        # Normalized adjacency matrix buffer
        if adj_mx is not None:
            if isinstance(adj_mx, np.ndarray):
                adj_tensor = torch.from_numpy(adj_mx).float()
            else:
                adj_tensor = adj_mx.float()
        else:
            adj_tensor = torch.eye(node_count or 100, dtype=torch.float32)
        self.register_buffer("adj_hat", adj_tensor)

    def _get_adj(self, x: torch.Tensor, custom_adj: torch.Tensor | None = None) -> torch.Tensor:
        """Resolve normalized adjacency matrix matching current input node count."""
        if custom_adj is not None:
            return custom_adj
        if self.adj_hat is not None and self.adj_hat.shape[0] == x.shape[2]:
            return self.adj_hat
        # Fallback: identity with self-loops matching current node count
        N = x.shape[2]
        return torch.eye(N, dtype=torch.float32, device=x.device)

    def forward(
        self,
        values: torch.Tensor,
        adj_mx: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Forward pass.

        Args:
            values: Input tensor of shape [B, T=12, N, F].
            adj_mx: Optional normalized adjacency matrix of shape [N, N].

        Returns:
            predictions: Tensor of shape [B, N, 3] (5m, 15m, 30m speeds).
        """
        B, T, N, F = values.shape
        adj = self._get_adj(values, adj_mx)

        # 1. Spatial Graph Convolution over all timesteps
        h1 = self.dropout(self.activation(self.gcn1(values, adj)))  # [B, T, N, gcn_hidden]
        h_spatial = self.activation(self.gcn2(h1, adj))             # [B, T, N, gcn_hidden]

        # 2. Temporal Processing
        # Reshape to [B * N, T, gcn_hidden]
        # permute(0, 2, 1, 3) gives [B, N, T, gcn_hidden]
        temporal_input = h_spatial.permute(0, 2, 1, 3).contiguous().view(B * N, T, self.gcn_hidden)
        _, h_n = self.temporal(temporal_input)  # h_n[-1] is [B * N, hidden_size]

        # 3. Node-Level Multi-Horizon Prediction Head
        node_predictions = self.head(h_n[-1])  # [B * N, num_horizons]

        # Reshape back to [B, N, num_horizons]
        output = node_predictions.view(B, N, self.num_horizons)
        return output


class STGNNPredictor:
    """Production predictor wrapper providing node-level and segment-specific forecasts."""

    def __init__(
        self,
        *,
        feature_count: int,
        node_count: int = 100,
        hidden_size: int = 32,
        adj_mx: np.ndarray | torch.Tensor | None = None,
        dropout: float = 0.1,
    ) -> None:
        self.feature_count = feature_count
        self.node_count = node_count
        self.hidden_size = hidden_size

        if adj_mx is not None:
            from data.graphs.adjacency import calculate_gcn_normalized_adjacency
            if isinstance(adj_mx, np.ndarray):
                adj_hat = calculate_gcn_normalized_adjacency(adj_mx)
                self._adj_tensor = torch.from_numpy(adj_hat).float()
            else:
                self._adj_tensor = adj_mx.float()
        else:
            self._adj_tensor = None

        self._model = SpatioTemporalGNN(
            feature_count=feature_count,
            hidden_size=hidden_size,
            gcn_hidden=hidden_size,
            num_horizons=3,
            dropout=dropout,
            adj_mx=self._adj_tensor,
        )

    def predict(
        self,
        values: torch.Tensor | np.ndarray,
        node_index: int = 0,
    ) -> dict[str, float]:
        """Predict 5m, 15m, 30m speeds for a specific node (defaults to node 0).

        Maintains full backward compatibility with REST API endpoints and existing tests.
        """
        if not isinstance(values, torch.Tensor):
            values = torch.from_numpy(values).float()

        if values.ndim != 4 or values.shape[1] != 12:
            raise ValueError(
                f"STGNNPredictor expects input of shape [batch, 12, nodes, features], got {values.shape}"
            )

        self._model.eval()
        with torch.no_grad():
            output = self._model(values, self._adj_tensor)  # [B, N, 3]
            node_out = output[0, node_index].detach().cpu().numpy()

        return {
            "predicted_speed_5m": float(node_out[0]),
            "predicted_speed_15m": float(node_out[1]),
            "predicted_speed_30m": float(node_out[2]),
        }

    def predict_all_nodes(
        self,
        values: torch.Tensor | np.ndarray,
    ) -> np.ndarray:
        """Predict 5m, 15m, 30m speeds for ALL nodes in the network.

        Returns array of shape [B, N, 3].
        """
        if not isinstance(values, torch.Tensor):
            values = torch.from_numpy(values).float()

        if values.ndim != 4 or values.shape[1] != 12:
            raise ValueError(
                f"STGNNPredictor expects input of shape [batch, 12, nodes, features], got {values.shape}"
            )

        self._model.eval()
        with torch.no_grad():
            output = self._model(values, self._adj_tensor)  # [B, N, 3]
            return output.detach().cpu().numpy()
