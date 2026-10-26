import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Import the original scheduler directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scheduler_v4_2

def derive_renewable_fraction(carbon_array):
    carbon_min = np.min(carbon_array)
    carbon_max = np.max(carbon_array)
    normalized = (carbon_array - carbon_min) / max(carbon_max - carbon_min, 1e-9)
    renew = np.clip(0.78 - normalized * 0.63, 0.15, 0.78)
    return renew

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input CSV path")
    parser.add_argument("--n-ood", type=int, required=True, help="Number of OOD scenarios")
    parser.add_argument("--seed", type=int, required=True, help="Random seed")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    from tools.input_loader import load_paper_day_csv

    price_array, carbon_array, renew_array, input_meta = load_paper_day_csv(args.input)
    df = pd.read_csv(args.input).sort_values("timestamp_utc").reset_index(drop=True)
    site1_price = df["price_usd_per_kwh"].values
    site1_carbon = df["carbon_kg_per_kwh"].values

    timestamps = df["timestamp_utc"].values.tolist()

    parts = []
    parts.extend(timestamps)
    for arr in [site1_price, site1_carbon, price_array.flatten(), carbon_array.flatten(), renew_array.flatten()]:
        parts.extend(arr.astype(str).tolist())

    I, T, J, S = 3, 24, 60, 20
    parts.extend([str(I), str(T), str(J), str(S), str(args.n_ood), str(args.seed)])

    raw_str = "|".join(parts)
    checksum = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    df.to_csv(os.path.join(args.output_dir, "selected_input_day.csv"), index=False)

    scheduler_v4_2._REAL_PRICE = price_array
    scheduler_v4_2._REAL_CARBON_INTENSITY = carbon_array
    scheduler_v4_2._REAL_RENEW_FRAC = renew_array

    start_time = time.time()
    results_df = scheduler_v4_2.run_real_data_experiment(
        use_lstm=False,
        dro_solver="greedy",
        n_ood=args.n_ood
    )

    results_df["input_checksum"] = checksum
    results_df["n_ood"] = args.n_ood
    results_df["seed"] = args.seed

    order = ["CM", "CF", "RF", "SBS", "RO", "DRO"]
    results_df = results_df.set_index("method").reindex(order).reset_index()

    cols = ["method", "exp_cost", "exp_carbon", "cvar90_carbon", "sla_violation_rate", "std_cost", "std_carbon", "runtime_sec", "input_checksum", "n_ood", "seed"]
    results_df = results_df[cols]

    results_df.to_csv(os.path.join(args.output_dir, "aggregate_results.csv"), index=False)

    config = {
        "input_file": os.path.basename(args.input),
        "n_ood": args.n_ood,
        "seed": args.seed,
        "I": I,
        "T": T,
        "J": J,
        "S": S,
        "workload_seed": 42,
        "lstm_disabled": True,
        "dro_solver": "greedy",
        "input_data_classification": "REAL_SITE1_WITH_MODELED_SITE2_SITE3_AND_RENEWABLE_PROXY",
        "scheduler_implementation": "ORIGINAL_REPOSITORY_OPERATIONAL_POLICIES",
        "dro_path": "GREEDY_RISK_ADJUSTED",
        "input_checksum_algorithm": "SHA256",
        "common_inputs_for_all_methods": True
    }
    with open(os.path.join(args.output_dir, "configuration.json"), "w") as f:
        json.dump(config, f, indent=2)

    paper_data = {
        "CM":  {"cost": 24.79, "carbon": 101.07, "cvar": 119.88},
        "CF":  {"cost": 31.64, "carbon": 89.06,  "cvar": np.nan},
        "RF":  {"cost": 30.27, "carbon": 89.96,  "cvar": 106.74},
        "SBS": {"cost": 29.55, "carbon": 90.60,  "cvar": 107.46},
        "RO":  {"cost": 29.84, "carbon": 90.67,  "cvar": 106.37},
        "DRO": {"cost": 28.17, "carbon": 89.19,  "cvar": 103.62},
    }

    paper_rows = []
    cm_proj_carbon = results_df.loc[results_df["method"]=="CM", "exp_carbon"].values[0]
    cm_proj_cvar = results_df.loc[results_df["method"]=="CM", "cvar90_carbon"].values[0]

    for m in order:
        p_c = paper_data[m]["cost"]
        p_car = paper_data[m]["carbon"]
        p_cvar = paper_data[m]["cvar"]

        proj_c = results_df.loc[results_df["method"]==m, "exp_cost"].values[0]
        proj_car = results_df.loc[results_df["method"]==m, "exp_carbon"].values[0]
        proj_cvar = results_df.loc[results_df["method"]==m, "cvar90_carbon"].values[0]

        p_car_red = ((paper_data["CM"]["carbon"] - p_car) / paper_data["CM"]["carbon"]) * 100
        proj_car_red = ((cm_proj_carbon - proj_car) / cm_proj_carbon) * 100

        if not np.isnan(p_cvar):
            p_cvar_red = ((paper_data["CM"]["cvar"] - p_cvar) / paper_data["CM"]["cvar"]) * 100
        else:
            p_cvar_red = np.nan

        proj_cvar_red = ((cm_proj_cvar - proj_cvar) / cm_proj_cvar) * 100

        paper_rows.append({
            "method": m,
            "paper_cost": p_c,
            "project_cost": proj_c,
            "paper_carbon": p_car,
            "project_carbon": proj_car,
            "paper_cvar90": p_cvar,
            "project_cvar90": proj_cvar,
            "paper_carbon_reduction_vs_cm_pct": p_car_red,
            "project_carbon_reduction_vs_cm_pct": proj_car_red,
            "paper_cvar_reduction_vs_cm_pct": p_cvar_red,
            "project_cvar_reduction_vs_cm_pct": proj_cvar_red
        })

    paper_df = pd.DataFrame(paper_rows)
    paper_df.to_csv(os.path.join(args.output_dir, "paper_comparison.csv"), index=False)

    # Plots
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    methods = results_df["method"]
    colors = ["C0", "C1", "C2", "C3", "C4", "C5"]

    axes[0].bar(methods, results_df["exp_cost"], color=colors)
    axes[0].set_ylabel("Expected Cost")
    axes[0].set_title("Expected Cost")

    axes[1].bar(methods, results_df["exp_carbon"], color=colors)
    axes[1].set_ylabel("Expected Carbon")
    axes[1].set_title("Expected Carbon")

    axes[2].bar(methods, results_df["cvar90_carbon"], color=colors)
    axes[2].set_ylabel("Carbon CVaR 0.9")
    axes[2].set_title("Carbon CVaR 0.9")

    plt.tight_layout()
    fig.savefig(os.path.join(args.output_dir, "six_method_comparison.png"))
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.scatter(results_df["exp_cost"], results_df["exp_carbon"])
    for i, txt in enumerate(results_df["method"]):
        ax.annotate(txt, (results_df["exp_cost"].values[i], results_df["exp_carbon"].values[i]))
    ax.set_xlabel("Expected Cost")
    ax.set_ylabel("Expected Carbon")
    ax.set_title("Cost vs Carbon Scatter")
    fig.savefig(os.path.join(args.output_dir, "cost_carbon_scatter.png"))
    plt.close(fig)

    fig, ax = plt.subplots()
    ax.bar(results_df["method"], results_df["cvar90_carbon"], color=colors)
    ax.set_ylabel("90% CVaR of Carbon")
    ax.set_title("Carbon CVaR Comparison")
    fig.savefig(os.path.join(args.output_dir, "carbon_cvar_comparison.png"))
    plt.close(fig)

if __name__ == "__main__":
    main()
