"""Graph adjacency transformation and normalization utilities for ST-GNN."""
from __future__ import annotations

import numpy as np
import torch


def calculate_gcn_normalized_adjacency(
    adj_mx: np.ndarray,
    add_self_loops: bool = True,
    epsilon: float = 1e-7,
) -> np.ndarray:
    """Calculate symmetric degree-normalized adjacency matrix for Graph Convolution (GCN).

    Formulation (Kipf & Welling, 2017):
        A_tilde = A + I_N  (if add_self_loops is True and self-loops not already present)
        D_tilde_ii = sum_j(A_tilde_ij)
        A_hat = D_tilde^(-1/2) * A_tilde * D_tilde^(-1/2)

    Args:
        adj_mx: 2D square adjacency matrix of shape [N, N].
        add_self_loops: If True and diagonal is zero, adds identity matrix.
        epsilon: Small constant for numerical stability to prevent division by zero.

    Returns:
        A_hat: Symmetric normalized adjacency matrix [N, N] (np.float32).
    """
    adj = np.copy(adj_mx).astype(np.float32)
    N = adj.shape[0]

    # Add self-loops if needed
    if add_self_loops:
        diag = np.diag(adj)
        if not np.all(diag > 0):
            adj = adj + np.eye(N, dtype=np.float32)

    # Degree matrix D_tilde
    row_sum = np.sum(adj, axis=1)
    d_inv_sqrt = np.power(np.maximum(row_sum, epsilon), -0.5)
    d_inv_sqrt[np.isinf(d_inv_sqrt)] = 0.0

    d_mat_inv_sqrt = np.diag(d_inv_sqrt)
    a_hat = np.dot(np.dot(d_mat_inv_sqrt, adj), d_mat_inv_sqrt)

    return a_hat.astype(np.float32)


# Convenient alias
normalize_adjacency = calculate_gcn_normalized_adjacency


def calculate_random_walk_normalized_adjacency(
    adj_mx: np.ndarray,
    epsilon: float = 1e-7,
) -> np.ndarray:
    """Calculate transition probability matrix for random-walk graph convolution.

    Formulation:
        P = D^(-1) * A
    """
    adj = np.copy(adj_mx).astype(np.float32)
    row_sum = np.sum(adj, axis=1)
    d_inv = np.power(np.maximum(row_sum, epsilon), -1.0)
    d_inv[np.isinf(d_inv)] = 0.0
    return (np.diag(d_inv) @ adj).astype(np.float32)


def to_torch_sparse_or_dense(
    matrix: np.ndarray,
    sparse: bool = False,
    device: str | torch.device = "cpu",
) -> torch.Tensor:
    """Convert numpy adjacency matrix to PyTorch Tensor."""
    if sparse:
        indices = np.nonzero(matrix)
        values = matrix[indices]
        i = torch.LongTensor(np.array(indices))
        v = torch.FloatTensor(values)
        shape = matrix.shape
        return torch.sparse_coo_tensor(i, v, torch.Size(shape), device=device)
    return torch.from_numpy(matrix).float().to(device)
