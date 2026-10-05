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
    # Derive the renewable proxy using the original repository convention
    # across the entire array or per site? The instruction says:
    # normalized_carbon = (carbon - carbon_min) / max(carbon_max - carbon_min, numerical_epsilon)
    # renewable_fraction = clip(0.78 - normalized_carbon * 0.63, 0.15, 0.78)
    # The instruction says "using the original repository convention".
    # I will calculate min and max over the whole array or per site. Usually it's over the whole array.
    # Actually, the instructions give a specific formula without subscripts, I will apply it globally to the array.
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

    df = pd.read_csv(args.input)
    if len(df) != 24:
        raise ValueError(f"Expected exactly 24 observations, got {len(df)}")
    
    # Sort chronologically to be safe
    df = df.sort_values("timestamp_utc").reset_index(drop=True)

    site1_price = df["price_usd_per_kwh"].values
    site1_carbon = df["carbon_kg_per_kwh"].values

    if not np.all(np.isfinite(site1_price)) or not np.all(np.isfinite(site1_carbon)):
        raise ValueError("Missing or non-finite values in input")

    site2_price = site1_price * 1.042
    site2_carbon = site1_carbon + 0.028

    site3_price = site1_price * 0.969
    site3_carbon = np.clip(site1_carbon - 0.018, 0.0, None)

    price_array = np.vstack([site1_price, site2_price, site3_price])
    carbon_array = np.vstack([site1_carbon, site2_carbon, site3_carbon])
    renew_array = derive_renewable_fraction(carbon_array)

    # Calculate checksum on the exact 24 prices and 24 carbons
    checksum_str = ",".join([f"{p:.6f},{c:.6f}" for p, c in zip(site1_price, site1_carbon)])
    checksum = hashlib.md5(checksum_str.encode()).hexdigest()

    # Save selected_input_day.csv
    df.to_csv(os.path.join(args.output_dir, "selected_input_day.csv"), index=False)

    # Patch the scheduler in memory
    scheduler_v4_2._REAL_PRICE = price_array
    scheduler_v4_2._REAL_CARBON_INTENSITY = carbon_array
    scheduler_v4_2._REAL_RENEW_FRAC = renew_array
    
    # "Use the original experiment configuration:"
    # I=3, T=24, J=60, S=20, workload seed=42, methods=CM,CF,RF,SBS,RO,DRO
    # LSTM disabled, DRO solver = greedy for presentation run
    
    start_time = time.time()
    results_df = scheduler_v4_2.run_real_data_experiment(
        use_lstm=False,
        dro_solver="greedy",
        n_ood=args.n_ood
    )
    
    # The output df has columns like: method, exp_cost, exp_carbon, cvar90_carbon, sla_violation_rate, std_cost, std_carbon, runtime_sec
    # We need to ensure we output exactly:
    # method, exp_cost, exp_carbon, cvar90_carbon, sla_violation_rate, std_cost, std_carbon, runtime_sec, input_checksum, n_ood, seed
    # with 6 rows: CM, CF, RF, SBS, RO, DRO
    
    results_df["input_checksum"] = checksum
    results_df["n_ood"] = args.n_ood
    results_df["seed"] = args.seed
    
    # Ensure exact order:
    order = ["CM", "CF", "RF", "SBS", "RO", "DRO"]
    results_df = results_df.set_index("method").reindex(order).reset_index()
    
    cols = ["method", "exp_cost", "exp_carbon", "cvar90_carbon", "sla_violation_rate", "std_cost", "std_carbon", "runtime_sec", "input_checksum", "n_ood", "seed"]
    results_df = results_df[cols]
    
    results_df.to_csv(os.path.join(args.output_dir, "aggregate_results.csv"), index=False)
    
    # Create configuration.json
    config = {
        "input_file": os.path.basename(args.input),
        "n_ood": args.n_ood,
        "seed": args.seed,
        "I": 3,
        "T": 24,
        "J": 60,
        "S": 20,
        "workload_seed": 42,
        "lstm_disabled": True,
        "dro_solver": "greedy"
    }
    with open(os.path.join(args.output_dir, "configuration.json"), "w") as f:
        json.dump(config, f, indent=2)
        
    # Create paper_comparison.csv
    # CM:  cost 24.79, carbon 101.07, CVaR 119.88
    # CF:  cost 31.64, carbon 89.06, CVaR unavailable
    # RF:  cost 30.27, carbon 89.96, CVaR 106.74
    # SBS: cost 29.55, carbon 90.60, CVaR 107.46
    # RO:  cost 29.84, carbon 90.67, CVaR 106.37
    # DRO: cost 28.17, carbon 89.19, CVaR 103.62
    
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
    fig, ax = plt.subplots()
    ax.bar(results_df["method"], results_df["exp_cost"])
    ax.set_ylabel("Cost")
    ax.set_title("Six Method Comparison - Cost")
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
    cvar_methods = results_df[results_df["method"] != "CF"]
    ax.bar(cvar_methods["method"], cvar_methods["cvar90_carbon"])
    ax.set_ylabel("90% CVaR of Carbon")
    ax.set_title("Carbon CVaR Comparison")
    fig.savefig(os.path.join(args.output_dir, "carbon_cvar_comparison.png"))
    plt.close(fig)

if __name__ == "__main__":
    main()
