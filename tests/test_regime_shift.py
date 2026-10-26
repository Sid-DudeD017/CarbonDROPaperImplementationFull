import pytest
import pandas as pd
import numpy as np
import json
import os
from tools.regime_shift_partition import partition_data
from tools.regime_shift_generator import apply_abrupt_mean_shift, apply_variance_shift, apply_gradual_drift, apply_recurring_shift
from tools.regime_shift_detect import run_pelt, run_cusum, analyze_scenario

def test_partitioning_logic():
    dates = pd.date_range("2024-07-01T00:00:00Z", "2025-10-01T00:00:00Z", freq="1h")
    df = pd.DataFrame({
        "timestamp_utc": dates,
        "site_id": "test",
        "carbon_kg_per_kwh": 0.5,
        "price_usd_per_kwh": 0.1
    })
    cal, val, ho, manifest = partition_data(df)
    
    # Overlap check
    assert cal['timestamp_utc'].max() < val['timestamp_utc'].min()
    assert val['timestamp_utc'].max() < ho['timestamp_utc'].min()
    
def test_abrupt_mean():
    s = pd.Series([1.0, 1.0, 1.0, 1.0])
    out = apply_abrupt_mean_shift(s, 2, 0.1)
    assert out.iloc[0] == 1.0
    assert out.iloc[2] == 1.1

def test_variance():
    s = pd.Series([1.0, 2.0, 1.0, 2.0])
    out, clip = apply_variance_shift(s, 2, 1.5, pre_mean=1.5, non_negative=True)
    assert out.iloc[0] == 1.0
    assert out.iloc[1] == 2.0
    assert out.iloc[2] == 1.5 + 1.5*(1.0 - 1.5) # 0.75

def test_gradual_drift():
    s = pd.Series([1.0]*10)
    out = apply_gradual_drift(s, 5, 2, 0.1)
    assert out.iloc[4] == 1.0
    assert out.iloc[5] == 1.0
    assert out.iloc[6] == 1.1
    assert out.iloc[9] == 1.1
    
def test_recurring():
    s = pd.Series([1.0]*20)
    out, trans = apply_recurring_shift(s, 5, 0.1, period=5)
    assert out.iloc[4] == 1.0
    assert out.iloc[5] == 1.1
    assert out.iloc[9] == 1.1
    assert out.iloc[10] == 1.0
    assert 10 in trans
    
def test_detectors():
    s = np.array([0.0]*50 + [2.0]*50)
    idx_p = run_pelt(s, pen=10)
    idx_c = run_cusum(s, threshold=5)
    assert idx_p is not None and abs(idx_p - 50) < 5
    assert idx_c is not None and abs(idx_c - 50) < 5

def test_no_credentials_in_manifest():
    path = "artifacts/regime_shift/watttime_access_report.json"
    with open(path) as f:
        content = f.read()
    assert "password" not in content.lower()
    assert "token" not in content.lower()
