# Carbon-Aware Cloud Scheduling Architecture

## Overview
This repository evaluates six carbon-aware cloud scheduling policies on a common WattTime/CAISO-derived experiment over 1,000 out-of-distribution scenarios. The purpose of this project is to investigate how cloud workloads can be assigned across time and location to reduce carbon emissions and exposure to extreme grid conditions, while controlling electricity cost and meeting deadlines.

## Data Provenance
- **CAISO North Carbon Rate:** Measured (Authentic WattTime marginal operating emission rates).
- **CAISO North Nodal Prices:** Measured (Day-ahead nodal wholesale electricity pricing).
- **Additional Cloud Sites:** Modeled (Transformed multi-site carbon and price signals).
- **Renewable Availability Proxy:** Modeled (Regional solar and wind profile generation function).
- **60 Batch Workload Traces:** Generated (Synthetic job execution windows, resource demands, and deadlines).
- **1,000 OOD Scenarios:** Generated (Extreme weather, thermal shifts, and transmission stress conditions).
- **Carbon CVaR₀.₉:** Derived (Expected carbon emissions conditional on the worst 10% tail outcomes. It is an evaluation metric, not a scheduler).

## Exact Experiment Configuration
- Evaluation Date: 2025-08-05
- Scheduling Slots: 24 Hourly Intervals
- Compute Jobs: 60 Synthetic Workloads
- Internal Uncertainty: 20 In-Sample Realizations
- Deterministic Seed: 42
- OOD Cases: 1000

## Interpretation of Findings
- **CM (Cost-Minimizing):** Lowest cost.
- **RF (Renewable-First):** Lowest expected carbon.
- **RO (Robust Optimization):** Lowest carbon CVaR₀.₉ tail risk.
- **DRO (Distributionally Robust):** Offers a strong combined trade-off, hedging distributional shifts, but does not win every individual metric.
- All schedulers successfully met 100% of execution deadlines with zero observed SLA violations.
- Non-cost-only schedulers reduced expected carbon by approximately 12–13% relative to CM.
- *Note: Directional comparison only to paper results. The project and paper use different data, system scales, and implementation details.*

## Reproducibility

### Environment Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Benchmark Execution
To run the evaluation:
```bash
python tools/run_benchmark.py --ood-cases 1000 --seed 42
```

### Focused Tests
To run the verification suite:
```bash
pytest tests/ -v
```

### Website Server
To view the results dashboard locally:
```bash
python -m http.server -d website 8000
```
Then navigate to `http://localhost:8000` in your web browser.

### Output Artifacts
Experiment telemetry and visual metrics are generated into the `website/data` directory and `website/index.html` dashboard, reading source artifacts originally exported by the pipeline.
