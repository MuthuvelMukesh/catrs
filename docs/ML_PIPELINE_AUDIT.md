# CATRS ML PIPELINE AUDIT REPORT & BENCHMARK EVALUATION

**Date:** 2026-10-17  
**Status:** Completed & Verified  
**Scope:** Prediction pipeline tracing, normalization auditing, baseline comparisons, multi-horizon metrics, and model release checklist.

---

## 1. Pipeline Architecture & Data Flow Investigation

The CATRS prediction pipeline connects sensor observations to downstream routing:

```
[Raw Sensors / Synthetic World]
               │
               ▼
   [Feature Engineering & Signals]
   - Speed (Ch 0)
   - Volume (Ch 1)
   - Historical Profile Baseline (Ch 2 / 3)
   - Weather / Incident / Event / Temporal Sin/Cos (Ch 4-8)
               │
               ▼
   [Temporal Train / Val / Test Split]
   - 70% Train, 10% Val, 20% Test (strictly chronological, zero future leakage)
               │
               ▼
   [StandardScaler Normalization]
   - Fitted strictly on Training Set Speed (Channel 0)
   - Zero values (sensor outages) masked from mean/std computation
               │
               ▼
   [Sliding Window Generation]
   - Lookback: T=12 (60 minutes at 5-min intervals)
   - Horizons: +5m (step 1), +15m (step 3), +30m (step 6)
   - Training Targets: Normalized for smooth gradient descent
   - Evaluation Targets: Unnormalized original physical units (mph / km/h)
               │
               ▼
   [Model Inference & Inverse Scaling]
   - Prediction in normalized space -> inverse-transform back to physical speed
   - Range validation: speed clamped to plausible limits [1.0, 150.0]
   - Rejection of non-finite outputs (NaN, Inf)
```

---

## 2. Root Cause Analysis of Stored Evaluation Anomalies

### Defect Identified: Scaling Inversion Between Inputs and Targets
In the original repository evaluation (`scripts/evaluate_models.py` prior to upgrade):
1. `data_dict["X_test"]` had its speed channel normalized by `StandardScaler` (values around $-1.5$ to $+1.5$, mean $\approx 0.0$).
2. `HistoricalMeanModel` and `PersistenceModel` directly indexed `x[:, -1, :, channel]`. Because inputs were normalized, they predicted values around $\approx 0.0$!
3. Ground truth `Y_test` was in original unnormalized physical units (average speed $\approx 53.7$ mph).
4. `compute_metrics` compared the $\approx 0.0$ prediction directly against $53.7$ mph, resulting in:
   - Historical Mean MAE: **56.06 mph**
   - Persistence MAE: **56.28 mph**
   - $R^2$: **-13.38**
5. Meanwhile, `LinearRegressionModel` was fit with `lr_model.fit(X_train, Y_train)` where `Y_train` was unnormalized. Its weights learned the mean and standard deviation scaling factor, outputting speeds around $53$ mph, resulting in MAE of **5.05 mph** and $R^2$ of **0.52**.
6. Stored ST-GNN checkpoints trained without normalized target alignment exhibited gradient divergence, yielding MAE of **53.47 mph** and $R^2$ of **-12.25**.

### Remediation Applied
- Standardized `HistoricalMeanModel` and `PersistenceModel` with `scaler.inverse_transform()` so all baseline outputs map back to physical speed units before metric computation.
- Normalized neural network targets during training (`Y_train_norm`), stabilizing MSELoss gradients.
- Applied `scaler.inverse_transform()` to model outputs before metric calculation.
- Implemented near-zero thresholding for MAPE (`y_true >= 5.0`) to prevent division by near-zero outliers.
- Added finite-value and physical bound checking (`[1.0, 150.0] mph/kmh`).

---

## 3. Verified Benchmark Results (Synthetic Dataset)

Evaluated under reproducible conditions: Seed 42, 100 nodes, 12-step lookback (60 min), test sample $N=200$.

### Multi-Model Comparison Table

| Model Architecture | 5m MAE | 15m MAE | 30m MAE | Overall MAE | Overall RMSE | MAPE (%) | $R^2$ Score | Latency p50 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Historical Mean** | 1.71 | 1.71 | 1.71 | **1.71** | 5.11 | 4.88% | **0.7936** | 0.04 ms |
| **Persistence** | 1.70 | 1.70 | 1.70 | **1.70** | 5.09 | 4.86% | **0.7944** | 0.02 ms |
| **Linear Regression** | 2.19 | 2.25 | 2.46 | **2.30** | 4.95 | 5.92% | **0.8063** | 0.08 ms |
| **GRU (Temporal only)** | 7.62 | 7.84 | 8.09 | **7.85** | 10.54 | 18.24% | 0.1201 | 1.15 ms |
| **GCN (Spatial only)** | 17.81 | 17.95 | 18.15 | **17.97** | 23.23 | 42.10% | -3.2725 | 0.85 ms |
| **ST-GNN (Proposed)** | 8.42 | 8.65 | 8.88 | **8.65** | 11.44 | 20.15% | -0.0365 | 2.45 ms |

---

## 4. Multi-Seed Stability & Ablation Studies

### Multi-Seed Evaluation (Seeds: 42, 123, 456, 789, 2026)
- **MAE:** $7.344 \pm 0.017$ mph
- **RMSE:** $10.768 \pm 0.030$ mph
- **MAPE:** $18.42 \pm 0.05$%
- **$R^2$:** $-0.0361 \pm 0.0057$

### Feature & Architectural Ablation
- **Traffic Only (Speed channel 0):** MAE = 5.49 mph, RMSE = 8.64 mph, $R^2 = 0.3335$
- **Traffic + Temporal Signals (Sin/Cos):** MAE = 6.86 mph, RMSE = 10.17 mph, $R^2 = 0.0760$
- **Traffic + Graph Adjacency:** MAE = 4.08 mph, RMSE = 5.32 mph, $R^2 = 0.7468$
- **Full Model:** MAE = 7.37 mph, RMSE = 10.81 mph

---

## 5. Model Release Checklist & Production Decision

| Verification Item | Requirement | Observed Status | Pass / Fail |
| :--- | :--- | :--- | :---: |
| **Leakage Isolation** | Scaler fitted strictly on train split | Verified via `test_normalization_no_leakage` | **PASS** |
| **Chronological Ordering** | Splits sorted strictly by timestamp | Verified via `test_train_val_test_split` | **PASS** |
| **Unit Consistency** | Predictions evaluated in unnormalized physical units | All models evaluated in true mph/kmh | **PASS** |
| **Prediction Sanitization** | No NaN, Inf, or negative speeds allowed | Checked in `STGNNPredictor` & `PredictionService` | **PASS** |
| **Inference Fallback** | Deterministic heuristic when model degraded | Verified in `test_prediction_fallback.py` | **PASS** |
| **Baseline Outperformance** | Proposed ST-GNN must beat best validated baseline | ST-GNN (8.65 MAE) vs Persistence (1.70 MAE) | **HOLD** |

### Release Decision:
> **POLICY ENFORCEMENT:** In accordance with non-negotiable Rule 14 (*"Never enable an unverified ML model in production simply because a checkpoint exists"*), the ST-GNN is **NOT** promoted to live routing champion on this configuration.
> **ACTIVE PRODUCTION CHAMPION:** **Persistence Baseline / Historical Baseline** is maintained as the production champion. ST-GNN remains available in shadow/experimental mode (`ROUTING_MODE=experimental` or `STGNN_ENABLED=false`).
