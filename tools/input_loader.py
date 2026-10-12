"""
Input data loader module for CarbonDRO experiments.

Provides explicit, validated loading of 24-hour real-data CSV inputs,
site array transformations (Site 1 unchanged, Site 2 modeled, Site 3 modeled),
renewable proxy derivation, and SHA-256 checksum computation.
"""

from __future__ import annotations

import hashlib
import os
from typing import Dict, Tuple

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "timestamp_utc",
    "site_id",
    "latitude",
    "longitude",
    "carbon_kg_per_kwh",
    "price_usd_per_kwh",
]


def derive_renewable_fraction(carbon_array: np.ndarray) -> np.ndarray:
    """
    Derives renewable availability proxy from carbon intensity array.
    Formula: renew[t] = 0.78 - (carbon[t] - min) / (max - min) * 0.63,
    clipped to [0.15, 0.78].
    """
    carbon_min = np.min(carbon_array)
    carbon_max = np.max(carbon_array)
    denom = max(float(carbon_max - carbon_min), 1e-9)
    normalized = (carbon_array - carbon_min) / denom
    renew = np.clip(0.78 - normalized * 0.63, 0.15, 0.78)
    return renew


def load_paper_day_csv(
    filepath: str,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, object]]:
    """
    Loads and validates the 24-hour paper day input CSV.

    Validations performed:
      - File exists and is non-empty.
      - Contains exactly 24 rows after sorting by timestamp_utc.
      - Contains all required columns.
      - timestamp_utc strings are strictly chronological (monotonic increasing).
      - No missing (NaN) or infinite values in price and carbon columns.
      - Rejects negative price or carbon values.

    Constructs 3 site arrays:
      - Site 1: CSV values unchanged
      - Site 2: price = Site 1 price * 1.042
                carbon = Site 1 carbon + 0.028
      - Site 3: price = Site 1 price * 0.969
                carbon = max(Site 1 carbon - 0.018, 0)
      - Renewable proxy: derived via derive_renewable_fraction

    Returns:
      Tuple of (price_array, carbon_array, renew_array, metadata)
      where arrays have shape (3, 24).
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Input file not found: {filepath}")

    with open(filepath, "rb") as f:
        file_bytes = f.read()
    input_sha256 = hashlib.sha256(file_bytes).hexdigest()

    df = pd.read_csv(filepath)

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Input CSV missing required columns: {missing_cols}")

    if len(df) != 24:
        raise ValueError(f"Expected exactly 24 rows, got {len(df)}")

    # Check chronological order
    df_sorted = df.sort_values("timestamp_utc").reset_index(drop=True)
    if not (df["timestamp_utc"] == df_sorted["timestamp_utc"]).all():
        raise ValueError("Input CSV timestamps are not strictly sorted in chronological order")

    # Check strict monotonicity (no duplicate timestamps)
    timestamps = df_sorted["timestamp_utc"].tolist()
    if any(timestamps[i] >= timestamps[i + 1] for i in range(len(timestamps) - 1)):
        raise ValueError("Input CSV timestamps are not strictly monotonically increasing")

    site1_price = df_sorted["price_usd_per_kwh"].to_numpy(dtype=float)
    site1_carbon = df_sorted["carbon_kg_per_kwh"].to_numpy(dtype=float)

    if not np.all(np.isfinite(site1_price)):
        raise ValueError("Missing or non-finite values in price_usd_per_kwh")
    if not np.all(np.isfinite(site1_carbon)):
        raise ValueError("Missing or non-finite values in carbon_kg_per_kwh")

    if np.any(site1_price < 0.0):
        raise ValueError("Negative value found in price_usd_per_kwh")
    if np.any(site1_carbon < 0.0):
        raise ValueError("Negative value found in carbon_kg_per_kwh")

    # Site transformations
    site2_price = site1_price * 1.042
    site2_carbon = site1_carbon + 0.028

    site3_price = site1_price * 0.969
    site3_carbon = np.clip(site1_carbon - 0.018, 0.0, None)

    price_array = np.vstack([site1_price, site2_price, site3_price])
    carbon_array = np.vstack([site1_carbon, site2_carbon, site3_carbon])
    renew_array = derive_renewable_fraction(carbon_array)

    if price_array.shape != (3, 24):
        raise ValueError(f"Expected price_array shape (3, 24), got {price_array.shape}")
    if carbon_array.shape != (3, 24):
        raise ValueError(f"Expected carbon_array shape (3, 24), got {carbon_array.shape}")
    if renew_array.shape != (3, 24):
        raise ValueError(f"Expected renew_array shape (3, 24), got {renew_array.shape}")

    metadata = {
        "input_path": os.path.abspath(filepath),
        "input_relpath": filepath,
        "input_sha256": input_sha256,
        "row_count": len(df_sorted),
        "timestamp_start": timestamps[0],
        "timestamp_end": timestamps[-1],
        "site_count": 3,
        "site1_source": "authentic_watttime_caiso",
        "site2_source": "modeled_transformation_p_1.042_c_plus_0.028",
        "site3_source": "modeled_transformation_p_0.969_c_minus_0.018",
        "renewable_source": "derived_proxy_formula",
    }

    return price_array, carbon_array, renew_array, metadata
