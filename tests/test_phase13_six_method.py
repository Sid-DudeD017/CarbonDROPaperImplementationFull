import json
import os
import sys
import numpy as np
import pandas as pd
import pytest
import subprocess
import string

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
TOOLS_DIR = os.path.join(PROJECT_DIR, "tools")
RUNNER = os.path.join(TOOLS_DIR, "run_phase13_six_method.py")
DATA_FILE = "/Users/siddharthbhakta/phase13_real_data_worktree/data/phase13/processed/paper_day_2025-08-05.csv"

if not os.path.exists(DATA_FILE):
    DATA_FILE = "/Users/siddharthbhakta/phase13_real_data_worktree/data/phase13/processed/grid_normalized.csv"

ARTIFACTS_DIR = os.path.join(PROJECT_DIR, "artifacts", "six_method_phase13_test")

@pytest.fixture(scope="session")
def run_smoke_test():
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    cmd = [
        sys.executable, RUNNER,
        "--input", DATA_FILE,
        "--n-ood", "2",
        "--seed", "42",
        "--output-dir", ARTIFACTS_DIR
    ]
    subprocess.run(cmd, check=True)
    yield

def test_input_observations():
    df = pd.read_csv(DATA_FILE)
    assert len(df) == 24
    assert df["timestamp_utc"].is_monotonic_increasing

def test_arrays_and_values(run_smoke_test):
    df = pd.read_csv(DATA_FILE)
    site1_price = df["price_usd_per_kwh"].values
    site1_carbon = df["carbon_kg_per_kwh"].values

    assert np.all(np.isfinite(site1_price))
    assert np.all(np.isfinite(site1_carbon))

    site2_price = site1_price * 1.042
    site2_carbon = site1_carbon + 0.028

    site3_price = site1_price * 0.969
    site3_carbon = np.clip(site1_carbon - 0.018, 0.0, None)

    price_array = np.vstack([site1_price, site2_price, site3_price])
    carbon_array = np.vstack([site1_carbon, site2_carbon, site3_carbon])

    assert price_array.shape == (3, 24)
    assert carbon_array.shape == (3, 24)

    c_min = np.min(carbon_array)
    c_max = np.max(carbon_array)
    normalized = (carbon_array - c_min) / max(c_max - c_min, 1e-9)
    renew = np.clip(0.78 - normalized * 0.63, 0.15, 0.78)

    assert np.all(renew >= 0.15) and np.all(renew <= 0.78)

def test_smoke_run_outputs(run_smoke_test):
    agg_file = os.path.join(ARTIFACTS_DIR, "aggregate_results.csv")
    assert os.path.exists(agg_file)
    df = pd.read_csv(agg_file)
    assert len(df) == 6
    assert list(df["method"]) == ["CM", "CF", "RF", "SBS", "RO", "DRO"]

    assert len(df["input_checksum"].unique()) == 1
    checksum = df["input_checksum"].iloc[0]
    assert len(checksum) == 64
    assert all(c in string.hexdigits for c in checksum)

    assert df["n_ood"].iloc[0] == 2
    assert df["seed"].iloc[0] == 42

    cols = ["exp_cost", "exp_carbon", "sla_violation_rate", "std_cost", "std_carbon", "runtime_sec"]
    for c in cols:
        assert np.all(np.isfinite(df[c]))

    assert np.all(np.isfinite(df["cvar90_carbon"]))

def test_determinism():
    dir2 = os.path.join(PROJECT_DIR, "artifacts", "six_method_phase13_test2")
    os.makedirs(dir2, exist_ok=True)
    cmd = [
        sys.executable, RUNNER,
        "--input", DATA_FILE,
        "--n-ood", "2",
        "--seed", "42",
        "--output-dir", dir2
    ]
    subprocess.run(cmd, check=True)

    df1 = pd.read_csv(os.path.join(ARTIFACTS_DIR, "aggregate_results.csv"))
    df2 = pd.read_csv(os.path.join(dir2, "aggregate_results.csv"))

    df1 = df1.drop(columns=["runtime_sec"])
    df2 = df2.drop(columns=["runtime_sec"])

    pd.testing.assert_frame_equal(df1, df2)

def test_checksum_sensitivity():
    # Run again with a slightly modified input file
    modified_data = os.path.join(ARTIFACTS_DIR, "modified.csv")
    df = pd.read_csv(DATA_FILE)
    df.loc[0, "price_usd_per_kwh"] += 0.001
    df.to_csv(modified_data, index=False)

    dir3 = os.path.join(PROJECT_DIR, "artifacts", "six_method_phase13_test3")
    cmd = [
        sys.executable, RUNNER,
        "--input", modified_data,
        "--n-ood", "2",
        "--seed", "42",
        "--output-dir", dir3
    ]
    subprocess.run(cmd, check=True)

    df_orig = pd.read_csv(os.path.join(ARTIFACTS_DIR, "aggregate_results.csv"))
    df_mod = pd.read_csv(os.path.join(dir3, "aggregate_results.csv"))

    assert df_orig["input_checksum"].iloc[0] != df_mod["input_checksum"].iloc[0]

def test_configuration_and_credentials(run_smoke_test):
    config_path = os.path.join(ARTIFACTS_DIR, "configuration.json")
    with open(config_path) as f:
        config = json.load(f)

    assert config.get("input_data_classification") == "REAL_SITE1_WITH_MODELED_SITE2_SITE3_AND_RENEWABLE_PROXY"
    assert config.get("scheduler_implementation") == "ORIGINAL_REPOSITORY_OPERATIONAL_POLICIES"
    assert config.get("dro_path") == "GREEDY_RISK_ADJUSTED"
    assert config.get("input_checksum_algorithm") == "SHA256"
    assert config.get("common_inputs_for_all_methods") is True

    for root, dirs, files in os.walk(ARTIFACTS_DIR):
        for f in files:
            path = os.path.join(root, f)
            if f.endswith(".json") or f.endswith(".csv"):
                with open(path) as file_obj:
                    content = file_obj.read()
                    assert "/Users/" not in content

def test_git_diff_check():
    cmd = ["git", "diff", "--check"]
    res = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True)
    assert res.returncode == 0, f"Git diff check failed:\n{res.stdout}"
