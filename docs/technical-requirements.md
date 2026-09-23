# CATRS Technical Requirements Specification

## 1. System Mission & Functional Goals

1. **Traffic Congestion Prediction**:
   - Ingest multi-modal signals including road segment speed, vehicle counts, weather severity, active incident flags, and venue-event proximity scores.
   - Deliver multi-horizon speed forecasts at 5-minute, 15-minute, and 30-minute intervals.
   - Maintain dual prediction engines: an advanced Spatio-Temporal Graph Neural Network (ST-GNN) and an autonomous deterministic heuristic fallback.

2. **Priority-Weighted Equilibrium Routing**:
   - Assign route alternatives dynamically based on caller trip categories (e.g., `emergency`, `transit`, `freight`, `commuter_general`).
   - Look up multipliers from append-only, versioned policy weight schedules.
   - Prevent corridor herding through configurable diversification capacity caps and atomic Redis rolling-window counters.

3. **In-Line Decision Transparency**:
   - Generate structured explanation payloads inside the ranking operation from the exact same local variables used to order routes.
   - Disclose recommended route, alternatives considered, diversification cap status, assignment pool percentages, applied weights, and whether priority affected ranking.

4. **Independent Compliance Auditing**:
   - Provide an isolated audit service that inspects route outcomes against published policy schedules without importing routing-engine internals.
   - Detect weight mismatches, obsolete versions, unknown schedules, missing categories, and inapplicable/un-effective policies.
   - Support high-throughput batch policy verification (>100,000 outcomes/second).

---

## 2. Non-Functional Constraints & System Properties

1. **Architectural Isolation**:
   - Zero shared code or direct package imports between `services/routing-engine` and `services/audit-service`.
   - Contract boundary codified exclusively via JSON Schemas in `/contracts`.

2. **Fault Tolerance & Graceful Degradation**:
   - In the event of external feed outages, the system automatically marks signals as degraded and falls back to deterministic synthetic generators.
   - If PostgreSQL/TimescaleDB or Redis is offline, services boot in memory-only degraded mode and report statuses via `/health?full=true`.
   - If PyTorch or model weights are missing or corrupt, predictions default seamlessly to the heuristic fallback.

3. **Data Integrity & Immutability**:
   - Weight schedules are strictly append-only. Historical policy versions must never be modified retroactively.
   - Time-series traffic readings are stored in TimescaleDB hypertables partitioned by observation timestamp.

4. **Latency & Throughput Requirements**:
   - Multi-candidate route ranking latency: < 50 ms.
   - Segment speed prediction latency: < 50 ms.
   - Batch audit verification throughput: > 5,000 outcomes in < 100 ms.
