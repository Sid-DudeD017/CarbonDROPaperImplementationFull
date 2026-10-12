import os
import csv
import math
import pytest
import pandas as pd
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTHOR_DIR = os.path.join(PROJECT_DIR, "author_format_outputs")
REF_DIR = os.path.join(PROJECT_DIR, "reference_results_author")

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
