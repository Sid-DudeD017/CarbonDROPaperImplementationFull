import os
import csv
import json
import math
import tempfile
import pytest
import pandas as pd
import numpy as np

import scheduler_v4_2
from tools.input_loader import load_paper_day_csv, derive_renewable_fraction

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHOR_DIR = os.path.join(PROJECT_DIR, "author_format_outputs")
REF_DIR = os.path.join(PROJECT_DIR, "reference_results_author")
DEFAULT_CSV = os.path.join(PROJECT_DIR, "example_data", "paper_day_2025-08-05.csv")

REQUIRED_CSVS = [
    "metrics_comparative.csv",
    "metrics_real_data.csv",
    "metrics_battery.csv",
    "metrics_illustrative.csv",
    "metrics_pareto.csv",
    "metrics_scale_sweep.csv",
    "metrics_sensitivity.csv",
    "metrics_compute_cost.csv",
]

REQUIRED_PLOTS = [
    f"plot{i}_{name}.png"
    for i, name in [
        (1, "comparative_barplot"),
        (2, "cost_carbon_scatter"),
        (3, "pareto_frontier"),
        (4, "temporal_heatmap"),
        (5, "renewable_utilization"),
        (6, "battery_dynamics"),
        (7, "cvar_analysis"),
        (8, "sensitivity_heatmap"),
        (9, "uncertainty_quantification"),
        (10, "violin_distribution"),
        (11, "convergence_analysis"),
        (12, "job_scheduling_gantt"),
        (13, "real_data_comparison"),
        (14, "compute_cost"),
    ]
]


# ============================================================================
# Input Loader Unit Tests
# ============================================================================

def test_input_loader_shape_and_values():
    p, c, r, meta = load_paper_day_csv(DEFAULT_CSV)
    assert p.shape == (3, 24)
    assert c.shape == (3, 24)
    assert r.shape == (3, 24)

    assert meta["row_count"] == 24
    assert meta["site_count"] == 3
    assert len(meta["input_sha256"]) == 64
    assert np.all(np.isfinite(p))
    assert np.all(np.isfinite(c))
    assert np.all(np.isfinite(r))


def test_exact_site_transformations():
    p, c, r, meta = load_paper_day_csv(DEFAULT_CSV)
    df = pd.read_csv(DEFAULT_CSV).sort_values("timestamp_utc").reset_index(drop=True)
    p1 = df["price_usd_per_kwh"].to_numpy(dtype=float)
    c1 = df["carbon_kg_per_kwh"].to_numpy(dtype=float)

    # Site 1: exact CSV
    np.testing.assert_allclose(p[0], p1)
    np.testing.assert_allclose(c[0], c1)

    # Site 2: price = Site 1 * 1.042, carbon = Site 1 + 0.028
    np.testing.assert_allclose(p[1], p1 * 1.042)
    np.testing.assert_allclose(c[1], c1 + 0.028)

    # Site 3: price = Site 1 * 0.969, carbon = max(Site 1 - 0.018, 0)
    np.testing.assert_allclose(p[2], p1 * 0.969)
    np.testing.assert_allclose(c[2], np.clip(c1 - 0.018, 0.0, None))

    # Renewable proxy formula
    c_min = np.min(c)
    c_max = np.max(c)
    expected_renew = np.clip(0.78 - ((c - c_min) / (c_max - c_min)) * 0.63, 0.15, 0.78)
    np.testing.assert_allclose(r, expected_renew)


def test_chronological_validation():
    df = pd.read_csv(DEFAULT_CSV)
    # Reverse rows to test chronological order rejection
    df_reversed = df.iloc[::-1].reset_index(drop=True)
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as tf:
        df_reversed.to_csv(tf.name, index=False)
        temp_name = tf.name

    try:
        with pytest.raises(ValueError, match="chronological"):
            load_paper_day_csv(temp_name)
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def test_checksum_generation_and_sensitivity():
    p1, c1, r1, meta1 = load_paper_day_csv(DEFAULT_CSV)
    sha1 = meta1["input_sha256"]

    df = pd.read_csv(DEFAULT_CSV)
    df.loc[0, "price_usd_per_kwh"] += 0.0001
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as tf:
        df.to_csv(tf.name, index=False)
        temp_name = tf.name

    try:
        p2, c2, r2, meta2 = load_paper_day_csv(temp_name)
        sha2 = meta2["input_sha256"]
        assert sha1 != sha2
    finally:
        if os.path.exists(temp_name):
            os.remove(temp_name)


def test_embedded_arrays_not_used_unless_explicitly_populated():
    old_p = scheduler_v4_2._REAL_PRICE
    old_c = scheduler_v4_2._REAL_CARBON_INTENSITY
    old_r = scheduler_v4_2._REAL_RENEW_FRAC

    try:
        scheduler_v4_2._REAL_PRICE = None
        scheduler_v4_2._REAL_CARBON_INTENSITY = None
        scheduler_v4_2._REAL_RENEW_FRAC = None

        with pytest.raises(RuntimeError, match="are not populated"):
            scheduler_v4_2.gen_real_data_instance(J=60, S=20, seed=42)
    finally:
        scheduler_v4_2._REAL_PRICE = old_p
        scheduler_v4_2._REAL_CARBON_INTENSITY = old_c
        scheduler_v4_2._REAL_RENEW_FRAC = old_r


# ============================================================================
# Author-Format Outputs & Manifest Tests
# ============================================================================

def test_files_exist():
    assert os.path.isdir(AUTHOR_DIR)
    plot_dir = os.path.join(AUTHOR_DIR, "plots")
    assert os.path.isdir(plot_dir)

    for csv_file in REQUIRED_CSVS:
        path = os.path.join(AUTHOR_DIR, csv_file)
        assert os.path.exists(path), f"Missing required CSV: {csv_file}"

    for plot_file in REQUIRED_PLOTS:
        path = os.path.join(plot_dir, plot_file)
        assert os.path.exists(path), f"Missing required plot: {plot_file}"
        assert os.path.getsize(path) > 1000, f"Plot {plot_file} is empty or corrupted"

    manifest_path = os.path.join(AUTHOR_DIR, "run_manifest.json")
    assert os.path.exists(manifest_path), "Missing run_manifest.json in author_format_outputs/"


def test_run_manifest_content():
    manifest_path = os.path.join(AUTHOR_DIR, "run_manifest.json")
    assert os.path.exists(manifest_path)
    with open(manifest_path) as f:
        manifest = json.load(f)

    assert "input_path" in manifest
    assert "input_sha256" in manifest
    assert manifest["row_count"] == 24
    assert manifest["site_count"] == 3
    assert manifest["common_inputs_for_all_six_methods"] is True
    assert manifest["data_provenance"]["site2_site3_modeled"] is True
    assert manifest["data_provenance"]["renewable_values_derived"] is True
    assert manifest["methods_evaluated"] == ["CM", "CF", "RF", "SBS", "RO", "DRO"]


def test_csv_schemas_match_reference():
    for csv_file in REQUIRED_CSVS:
        gen_path = os.path.join(AUTHOR_DIR, csv_file)
        ref_path = os.path.join(REF_DIR, csv_file)
        with open(gen_path, "r") as fg, open(ref_path, "r") as fr:
            gen_cols = next(csv.reader(fg))
            ref_cols = next(csv.reader(fr))
            assert gen_cols == ref_cols, f"Schema mismatch for {csv_file}"


def test_finite_values_and_row_counts():
    expected_rows = {
        "metrics_comparative.csv": 6,
        "metrics_real_data.csv": 6,
        "metrics_battery.csv": 1,
        "metrics_illustrative.csv": 2,
        "metrics_scale_sweep.csv": 36,
        "metrics_sensitivity.csv": 24,
        "metrics_compute_cost.csv": 30,
    }

    for csv_file, exp_count in expected_rows.items():
        gen_path = os.path.join(AUTHOR_DIR, csv_file)
        with open(gen_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == exp_count, f"Row count mismatch for {csv_file}: got {len(rows)}, expected {exp_count}"

            for r in rows:
                for k, v in r.items():
                    if k in ["method", "exp", "config", "data_source", "regions", "dispatch_method", "note"]:
                        continue
                    val = float(v)
                    assert math.isfinite(val), f"Non-finite value {val} in {csv_file}:{k}"


def test_six_methods_present_in_comparative_and_real_data():
    methods = ["CM", "CF", "RF", "SBS", "RO", "DRO"]
    for csv_file in ["metrics_comparative.csv", "metrics_real_data.csv"]:
        path = os.path.join(AUTHOR_DIR, csv_file)
        df = pd.read_csv(path)
        assert list(df["method"]) == methods


def test_provenance_and_no_author_values_copied():
    # Ensure generated numerical values are NOT copied from author reference files
    for csv_file in REQUIRED_CSVS:
        gen_path = os.path.join(AUTHOR_DIR, csv_file)
        ref_path = os.path.join(REF_DIR, csv_file)
        with open(gen_path, "r") as fg, open(ref_path, "r") as fr:
            gen_text = fg.read()
            ref_text = fr.read()
            assert gen_text != ref_text, f"Generated file {csv_file} is identical to author reference!"
