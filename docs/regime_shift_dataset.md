# Regime-Shift Dataset

## Measured Source Period
The base dataset contains hourly `CAISO_NP15` data spanning from **2024-08-01 07:00:00Z** to **2025-09-01 06:00:00Z**. It integrates WattTime marginal emissions (MOER) and CAISO day-ahead prices.

## Partitions
To prevent data leakage, the data is split chronologically:
- **Calibration Partition:** Used to tune parameters. `2024-08-01 07:00:00Z` – `2025-04-30 23:59:59Z`.
- **Validation Partition:** Used for out-of-sample tuning validation. `2025-05-01 00:00:00Z` – `2025-06-30 23:59:59Z`.
- **Held-out Partition:** Exclusively used as the base for controlled shift injection. `2025-07-01 00:00:00Z` – `2025-09-01 06:00:00Z`.

## Controlled vs Natural Tracks
- **Track A (Natural):** Exploratory analysis applying detectors directly to the unmodified historical data to surface potential natural structural changes. These are **not confirmed events**; they are strictly statistical candidates.
- **Track B (Controlled):** Precise semi-synthetic regimes injected into the held-out partition at known times (`tau_exact`). Used to benchmark detection delay and accuracy.

## Transformations
1. **Abrupt Mean Shift:** Instantaneous proportional multiplier (e.g. +10%, -10%).
2. **Variance Shift:** Magnifies variation relative to the pre-shift calibration mean (e.g. 1.25x). Carbon is non-negative clipped.
3. **Gradual Drift:** Ramps up smoothly over 24 or 168 hours to a final proportional target.
4. **Recurring Regime:** Repeatedly alternates between a shifted state (+15%) and the baseline every 72 hours.
5. **Compound Shift:** Applies both mean and variance changes to both carbon and price signals.

## Exact Tau vs Estimated Tau-Hat
- **`tau_exact`:** The ground-truth timestamp at which a controlled transformation was injected. **Detectors never see this.**
- **`tau_hat`:** The timestamp estimated by a detection algorithm (PELT or CUSUM) operating sequentially on the observed data.
- **Consensus:** A merged candidate created only when PELT and CUSUM agree within a strict tolerance (24 hours for controlled, 7 days for natural).

## Detector Parameters
- **PELT:** `min_size=24`, `model=l2`, `pen=10.0`.
- **CUSUM:** `threshold=5.0`, `drift=0.0`.
These remain fixed across all tests.

## Limitations
- This dataset is scoped to a single region (`CAISO_NP15`) over slightly more than one year, limiting multi-regional and decadal analyses.
- Only a single node’s pricing (NP15) is used.
- Natural candidates lack independent documentary verification and cannot be treated as causal real-world events.

## WattTime Access Result
A diagnostic script tested the local `.env` credentials against the WattTime `/v3/my-access` endpoint.
- **Result:** The credentials are valid and access the `CAISO_NORTH` `co2_moer` signal.
- **Historical Bounds:** Authorized from `2020-01-01` to `2026-04-02` (depending on the specific model version).
- However, downloading the multi-year extension was intentionally skipped in this task scope as per instructions.

## Reproduction
To rebuild the dataset:
```bash
python tools/build_regime_shift_dataset.py \
  --input data/regime_shift/base/grid_normalized.csv \
  --output-dir data/regime_shift/scenarios \
  --artifacts-dir artifacts/regime_shift \
  --seed 42
```
All outputs are generated in the `artifacts/regime_shift/` and `data/regime_shift/scenarios/` directories.
