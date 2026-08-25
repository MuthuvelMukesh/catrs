# Detailed Report

This repository implements a three-layer congestion-aware traffic routing system.

## Overview

- Layer 1: predicts congestion and ranks routes using priority-aware weighted routing.
- Layer 2: emits a transparency payload alongside route results from the same ranking variables.
- Layer 3: independently audits actual system behavior against the published weight schedule.

## Architecture goals

- Keep the routing engine and audit service isolated by contract, not shared code.
- Treat priority weights as append-only versioned records.
- Generate explanation payloads from the same variables used during ranking.
- Preserve a fallback heuristic that does not rely on ML model imports.
