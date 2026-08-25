# Technical Implementation Details

## 1. Synthetic data and storage

- Build a synthetic 10x10 grid road graph as the initial prototype.
- Generate segment speed, volume, weather, incident, and venue-event data with daily and weekly seasonality.
- Persist readings in Postgres and use TimescaleDB hypertables for time-series storage.
- Maintain a historical baseline view keyed by segment, weekday, and hour.

## 2. Prediction model

- Use a spatio-temporal model over 12 recent timesteps for 5/15/30-minute horizons.
- Keep fallback heuristic separate from ML implementation to support graceful degradation.

## 3. Routing and diversification

- Maintain a versioned weight schedule table where each new version is future-dated.
- Rank routes using a priority-weighted equilibrium formulation with diversification caps.
- Use Redis counters to prevent route herding within a rolling time window.

## 4. Explanation payload

- Emit the explanation payload directly inside the ranking function.
- Ensure route travel-time values in the payload are copied from the same local values used to rank alternatives.

## 5. Audit boundary

- The audit service reads from read-only replicas or independent connections.
- Version-pinned queries ensure the policy used for period X matches the schedule in effect during X.
- CI checks reject imports from the routing-engine package in audit-service.
