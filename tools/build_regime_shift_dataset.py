import os
import argparse
import json
import hashlib
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tools.regime_shift_partition import partition_data
from tools.regime_shift_generator import generate_controlled_scenarios
from tools.regime_shift_detect import analyze_scenario, run_natural_candidates
from tools.regime_shift_validate import validate_all

def checksum_file(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.artifacts_dir, exist_ok=True)
    
    # 1. Base audit
    base_sha256 = checksum_file(args.input)
    df = pd.read_csv(args.input)
    
    with open(os.path.join(args.artifacts_dir, "base_data_audit.json"), "w") as f:
        json.dump({
            "checksum": base_sha256,
            "rows": len(df),
            "columns": list(df.columns)
        }, f, indent=2)
        
    # 2. Partitions
    cal_df, val_df, ho_df, part_manifest = partition_data(df)
    
    with open(os.path.join(args.artifacts_dir, "partition_manifest.json"), "w") as f:
        json.dump(part_manifest, f, indent=2)
        
    # 3. Controlled scenarios
    scenarios = generate_controlled_scenarios(ho_df, cal_df)
    
    # 4. Detect and build manifest rows
    manifest_rows = []
    
    for scen in scenarios:
        # detection
        metrics = analyze_scenario(scen, ho_df)
        
        # Save Parquet
        scen_df = pd.DataFrame({
            "scenario_id": scen["scenario_id"],
            "timestamp_utc": scen["timestamp_utc"],
            "site_id": scen["site_id"],
            "base_carbon_kg_per_kwh": scen["base_carbon_kg_per_kwh"],
            "shifted_carbon_kg_per_kwh": scen["shifted_carbon_kg_per_kwh"],
            "carbon_delta_kg_per_kwh": scen["shifted_carbon_kg_per_kwh"] - scen["base_carbon_kg_per_kwh"],
            "base_price_usd_per_kwh": scen["base_price_usd_per_kwh"],
            "shifted_price_usd_per_kwh": scen["shifted_price_usd_per_kwh"],
            "price_delta_usd_per_kwh": scen["shifted_price_usd_per_kwh"] - scen["base_price_usd_per_kwh"],
            "affected_carbon": scen["affected_carbon"],
            "affected_price": scen["affected_price"],
            "post_tau": scen["timestamp_utc"] >= scen["tau_exact"],
            "shift_type": scen["shift_type"],
            "tau_exact": scen["tau_exact"],
            "transition_index": 1,
            "seed": scen["seed"]
        })
        
        pq_path = os.path.join(args.output_dir, f"{scen['scenario_id']}.parquet")
        table = pa.Table.from_pandas(scen_df)
        pq.write_table(table, pq_path)
        scen_checksum = checksum_file(pq_path)
        
        manifest_row = {
            "scenario_id": scen["scenario_id"],
            "track": "controlled",
            "status": "generated",
            "region_ids": ["CAISO_NP15"],
            "metrics": ["carbon", "price"],
            "shift_type": scen["shift_type"],
            "tau_exact": scen["tau_exact"].isoformat(),
            "tau_source": "injected_exact",
            "transformation_parameters": scen.get("transformation_parameters", {}),
            "base_data_checksum_sha256": base_sha256,
            "scenario_checksum_sha256": scen_checksum,
            "base_data_path": args.input,
            "scenario_data_path": pq_path,
            "limitations": "One-region only."
        }
        manifest_row.update(metrics)
        manifest_rows.append(manifest_row)
        
    # Validation
    is_valid, val_results = validate_all(scenarios, ho_df)
    with open(os.path.join(args.artifacts_dir, "validation_report.json"), "w") as f:
        json.dump({"all_valid": is_valid, "results": val_results}, f, indent=2)
        
    # Write controlled manifest
    with open(os.path.join(args.artifacts_dir, "controlled_scenarios.jsonl"), "w") as f:
        for row in manifest_rows:
            f.write(json.dumps(row) + "\n")
            
    # Write scenario catalog (csv version)
    df_catalog = pd.DataFrame(manifest_rows)
    df_catalog.to_csv(os.path.join(args.artifacts_dir, "scenario_catalog.csv"), index=False)
    
    # Write detection results (csv version)
    df_catalog.to_csv(os.path.join(args.artifacts_dir, "detection_results.csv"), index=False)

    # 5. Natural candidates
    nat_cands = run_natural_candidates(df, cal_df)
    with open(os.path.join(args.artifacts_dir, "natural_shift_candidates.jsonl"), "w") as f:
        for row in nat_cands:
            f.write(json.dumps(row) + "\n")
            
    # 6. Checksums
    checksums = []
    for root, _, files in os.walk(args.artifacts_dir):
        for file in files:
            if file != "checksums.sha256":
                path = os.path.join(root, file)
                checksums.append(f"{checksum_file(path)}  {file}")
    with open(os.path.join(args.artifacts_dir, "checksums.sha256"), "w") as f:
        f.write("\n".join(checksums) + "\n")

if __name__ == "__main__":
    main()
