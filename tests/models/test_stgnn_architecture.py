"""Unit tests for Graph Convolution, SpatioTemporalGNN, and variable node counts."""
from __future__ import annotations

import numpy as np
import pytest
import torch

from app.models.st_gnn import GraphConvolution, SpatioTemporalGNN, STGNNPredictor
from data.graphs.adjacency import normalize_adjacency


def test_graph_convolution():
    """Verify vectorized GraphConvolution H' = A_hat H W."""
    N = 5
    F_in = 4
    F_out = 8
    gcn = GraphConvolution(in_features=F_in, out_features=F_out)

    # 4D input [B=2, T=3, N=5, F_in=4]
    x = torch.randn(2, 3, N, F_in)
    adj = torch.eye(N)  # identity adjacency

    out = gcn(x, adj)
    assert out.shape == (2, 3, N, F_out)
    assert not torch.isnan(out).any()


def test_variable_node_count():
    """Verify ST-GNN dynamically operates on different node counts without modification."""
    # Synthetic size (100)
    model = SpatioTemporalGNN(feature_count=4, hidden_size=16, gcn_hidden=16)
    x_100 = torch.randn(2, 12, 100, 4)
    out_100 = model(x_100)
    assert out_100.shape == (2, 100, 3)

    # METR-LA size (207)
    x_207 = torch.randn(2, 12, 207, 4)
    out_207 = model(x_207)
    assert out_207.shape == (2, 207, 3)

    # PEMS-BAY size (325)
    x_325 = torch.randn(2, 12, 325, 4)
    out_325 = model(x_325)
    assert out_325.shape == (2, 325, 3)


def test_stgnn_output_shape():
    """Verify output shape is strictly [B, N, 3] representing 5m, 15m, 30m forecasts."""
    B, T, N, F = 4, 12, 50, 9
    model = SpatioTemporalGNN(feature_count=F, hidden_size=32, gcn_hidden=32, num_horizons=3)
    x = torch.randn(B, T, N, F)
    out = model(x)
    assert out.shape == (B, N, 3)


def test_metr_la_forward_pass():
    """Verify forward pass with realistic METR-LA input dimensions and normalized adjacency."""
    N = 207
    F = 4
    # Create random sparse adjacency with self loops
    adj_raw = np.eye(N, dtype=np.float32)
    for i in range(N - 1):
        adj_raw[i, i + 1] = 1.0
        adj_raw[i + 1, i] = 1.0
    adj_hat = normalize_adjacency(adj_raw)

    model = SpatioTemporalGNN(feature_count=F, hidden_size=32, gcn_hidden=32, adj_mx=adj_hat)
    x = torch.randn(2, 12, N, F)
    out = model(x)
    assert out.shape == (2, 207, 3)
    assert torch.isfinite(out).all()


def test_pems_bay_forward_pass():
    """Verify forward pass with realistic PEMS-BAY input dimensions and normalized adjacency."""
    N = 325
    F = 4
    adj_raw = np.eye(N, dtype=np.float32)
    for i in range(N - 1):
        adj_raw[i, i + 1] = 1.0
        adj_raw[i + 1, i] = 1.0
    adj_hat = normalize_adjacency(adj_raw)

    model = SpatioTemporalGNN(feature_count=F, hidden_size=32, gcn_hidden=32, adj_mx=adj_hat)
    x = torch.randn(2, 12, N, F)
    out = model(x)
    assert out.shape == (2, 325, 3)
    assert torch.isfinite(out).all()
