# Phase 13 Six-Method Demo

This document describes the process of running the six-method benchmark using Phase 13 WattTime/CAISO paper-day data.

## Usage

```bash
python tools/run_phase13_six_method.py \
  --input /path/to/paper_day_2025-08-05.csv \
  --n-ood 100 \
  --seed 42 \
  --output-dir artifacts/six_method_phase13
```

## Data Transformations

The script takes the base prices and carbon intensities for Site 1 from the provided CSV file and builds three sites:

- **Site 1**: authentic Phase 13 price and carbon intensity.
- **Site 2**: modeled as Site 1 price * 1.042, and Site 1 carbon + 0.028 kg CO2/kWh.
- **Site 3**: modeled as Site 1 price * 0.969, and max(Site 1 carbon - 0.018, 0.0).

The renewable fraction is a modeled transformation derived globally using the formula:
`normalized_carbon = (carbon - carbon_min) / max(carbon_max - carbon_min, 1e-9)`
`renewable_fraction = clip(0.78 - normalized_carbon * 0.63, 0.15, 0.78)`

These are modeled proxy values and not independently observed data.
