# Author-Format Handoff Documentation

This document describes the structure, provenance, input datasets, experimental execution configurations, generated files, and unavailable experiments for the CarbonDRO author-format results handoff.

---

## 1. Overview and Scope

This repository provides an end-to-end implementation of the Carbon-Aware Distributionally Robust Optimization (CarbonDRO) scheduler and benchmark suites. The handoff format mirrors the reference directory structure, filenames, CSV schemas, and plot naming conventions of `reference_results_author/` without copying any numerical values from the reference files.

All results under `author_format_outputs/` are generated from this repository's own model pipelines, algorithms, and data structures.

> **Disclaimer**: Matching filenames and CSV schemas between `author_format_outputs/` and `reference_results_author/` does **not** imply identical numerical results. In particular:
> - The reference results were produced with earlier/different revisions and random seeds.
> - The experiments here reflect the actual implemented algorithms (`scheduler_v4_2.py`) under greedy integer projection with convex relaxation.

---

## 2. Input Datasets & Provenance

### 2.1 Demonstration Dataset
- **Tracked demonstration file**: `example_data/paper_day_2025-08-05.csv`
- **Rows**: Exactly 24 hourly observations corresponding to the California market day August 5, 2025 (2025-08-05T07:00:00Z through 2025-08-06T06:00:00Z UTC).
- **Columns**: `timestamp_utc`, `site_id`, `latitude`, `longitude`, `carbon_kg_per_kwh`, `price_usd_per_kwh`.
- **Source**: WattTime Marginal Operating Emissions Rate (MOER) for `CAISO_NORTH` and California ISO (CAISO) OASIS Day-Ahead Market (DAM) Locational Marginal Price (LMP) for node `TH_NP15_GEN-APND`.
- **Role**: Serves as a small, reproducible demonstration and verification dataset.

### 2.2 Live Data Acquisition Pipeline
- **Script**: `tools/acquire_phase13_data.py`
- **Authentication**: Requires `WATTTIME_USERNAME` and `WATTTIME_PASSWORD` set via environment variables.
- **Security**: Tokens are never hardcoded, written to disk, or logged.
- **Local outputs**: All raw and processed API caches are stored under `.gitignore` targets (`data/`, `raw_data/`, `api_cache/`, `local_outputs/`, `artifacts/`).

---

## 3. Experimental Configurations & Execution

The experiment runner executed the six methods (`CM`, `CF`, `RF`, `SBS`, `RO`, `DRO`) across all implemented experiment blocks:

```bash
export MPLCONFIGDIR=/tmp/matplotlib_cache
python scheduler_v4_2.py \
    --out author_format_outputs \
    --n-bench 1000 \
    --n-real 100 \
    --dro-solver greedy \
    --seed 7
```

### Methods Evaluated
1. **CM** (Cost Minimization)
2. **CF** (Carbon Footprint Minimization)
3. **RF** (Renewable Fraction Maximization)
4. **SBS** (Scenario-Based Stochastic Optimization)
5. **RO** (Robust Optimization)
6. **DRO** (Distributionally Robust Optimization)

---

## 4. Generated Author-Format Outputs

All outputs below are generated in `author_format_outputs/` matching the CSV schemas of `reference_results_author/`:

### 4.1 Metrics CSV Files
| File | Columns | Rows | Description |
|---|---|---|---|
| `metrics_comparative.csv` | 8 | 6 | Comparative benchmark across the 6 methods (1,000 OOD scenarios, I=4, T=24, J=100) |
| `metrics_real_data.csv` | 10 | 6 | Real-data validation across 6 methods (100 OOD scenarios, WattTime/CAISO signals) |
| `metrics_battery.csv` | 13 | 1 | Battery storage evaluation with heuristic dispatch |
| `metrics_illustrative.csv` | 10 | 2 | Small illustrative instance comparing baseline vs DRO (I=2, T=12, J=30, S=20) |
| `metrics_pareto.csv` | 14 | 2 | Non-dominated frontier points swept across price, carbon, and risk weights |
| `metrics_scale_sweep.csv` | 16 | 36 | Scale sweep across varying problem dimensions (I, T, J) and seeds |
| `metrics_sensitivity.csv` | 14 | 24 | Sensitivity analysis sweeping risk penalty weights `w_cvar` and thresholds `tau` |
| `metrics_compute_cost.csv` | 7 | 30 | Runtime compute cost comparison across problem scales and methods |

### 4.2 Visualization Plots (`author_format_outputs/plots/`)
All 14 reference plot filenames are generated:
- `plot1_comparative_barplot.png`: Barplot of cost, carbon, CVaR, and SLA rate across methods.
- `plot2_cost_carbon_scatter.png`: Expected cost vs. expected carbon scatter plot.
- `plot3_pareto_frontier.png`: Trade-off frontier curve.
- `plot4_temporal_heatmap.png`: Temporal grid energy scheduling heatmap.
- `plot5_renewable_utilization.png`: Renewable generation and utilization profile.
- `plot6_battery_dynamics.png`: Battery state of charge, charge, and discharge profiles.
- `plot7_cvar_analysis.png`: Tail risk scaling and CVaR analysis across problem scale.
- `plot8_sensitivity_heatmap.png`: Sensitivity heatmap over risk parameters.
- `plot9_uncertainty_quantification.png`: Uncertainty distribution across forecast models.
- `plot10_violin_distribution.png`: Violin plots of performance metrics across test scenarios.
- `plot11_convergence_analysis.png`: Ambiguity set Wasserstein radius convergence across epochs.
- `plot12_job_scheduling_gantt.png`: Gantt chart of job allocations across datacenters.
- `plot13_real_data_comparison.png`: Real-data performance comparison across all 6 methods.
- `plot14_compute_cost.png`: Compute runtime scaling across problem dimensions.

---

## 5. Output Manifest & Status

| Output File | Status | Provenance & Notes |
|---|---|---|
| `metrics_comparative.csv` | `GENERATED` | Produced by `run_comparative_benchmark` (1000 scenarios, seed 100) |
| `metrics_real_data.csv` | `GENERATED` | Produced by `run_real_data_experiment` (100 OOD scenarios, seed 42) |
| `metrics_battery.csv` | `GENERATED` | Produced by `run_battery_experiment` (heuristic dispatch, seed 30) |
| `metrics_illustrative.csv` | `GENERATED` | Produced by `run_illustrative` (seed 7, S=20) |
| `metrics_pareto.csv` | `GENERATED` | Produced by `compute_pareto_frontier` (non-dominated points retained) |
| `metrics_scale_sweep.csv` | `GENERATED` | Produced by `run_scale_sweep` (seeds 11, 12, 13) |
| `metrics_sensitivity.csv` | `GENERATED` | Produced by `run_sensitivity` (seeds 21, 22) |
| `metrics_compute_cost.csv` | `GENERATED` | Produced by `build_compute_cost_table` (5 scale configs × 6 methods) |
| `plots/plot1_comparative_barplot.png` through `plots/plot14_compute_cost.png` | `GENERATED` | 14 plots rendered and saved with dpi 150-250 |

### Unavailable Experiments / Metrics Manifest
No CSV files or plots were fabricated. All 8 metric files and 14 plot files correspond to fully implemented and executed experiments in `scheduler_v4_2.py`.

If future experiments requiring external APIs or alternate solvers are introduced without implementation:
- `FULL_MILP_EXACT_SOLVER`: `NOT_AVAILABLE` (The scheduler uses convex relaxation with greedy integer projection; exact branch-and-bound MILP is uncharacterised per Section 8.2).
- `ONLINE_LSTM_RETRAINING`: `NOT_AVAILABLE` (Static EWMA/mean forecasts used during greedy sweep; dynamic online retraining omitted for reproducibility and speed).
