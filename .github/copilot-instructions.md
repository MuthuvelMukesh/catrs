# Project context for Copilot

This repo implements a 3-layer traffic congestion prediction + routing system.
Full specs live in /docs — check the relevant section before implementing
anything, and match its schemas/field names exactly rather than inventing your own.

Layers (build + dependency order):
1. services/routing-engine — ST-GNN congestion prediction, priority-weighted +
   diversified equilibrium routing, and the Layer-2 explanation payload
   (generated inside the same function that ranks routes, never a separate step).
2. services/audit-service — independently verifies routing-engine's actual
   outcomes against its own published weight-schedule policy.

Hard rules — do not violate these even when it would be more convenient:
- services/audit-service must never import from services/routing-engine, or
  vice versa, except through the versioned JSON contracts in /contracts. This
  isolation is the entire point of Layer 3.
- The fallback heuristic in routing-engine has zero import dependency on the
  ML model code.
- Priority weights are versioned rows, never hardcoded constants, and are
  never edited retroactively — only new versions with a future effective_date.
- Explanation payload fields are assigned from the same variables the ranking
  function used internally — never recomputed separately.

Stack: Python 3.12, FastAPI, PyTorch, Postgres + TimescaleDB, Redis, pytest.
