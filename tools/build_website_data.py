import json
import csv
import sys
import math
import subprocess
from pathlib import Path

def generate_website_data():
    project_dir = Path(__file__).resolve().parent.parent
    artifact_dir = project_dir / 'artifacts/six_method_phase13_1000'

    # Load configuration
    with open(artifact_dir / 'configuration.json') as f:
        config = json.load(f)

    # Load aggregate results
    aggregate = []
    with open(artifact_dir / 'aggregate_results.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            aggregate.append(row)

    # Load paper comparison
    paper_comparison = []
    with open(artifact_dir / 'paper_comparison.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            paper_comparison.append(row)

    expected_schedulers = {'CM', 'CF', 'RF', 'SBS', 'RO', 'DRO'}
    found_schedulers = set()

    cm_row = None
    for row in aggregate:
        if row['method'] == 'CM':
            cm_row = row

    if not cm_row:
        raise ValueError("Missing CM")

    cm_carbon = float(cm_row['exp_carbon'])
    cm_cvar = float(cm_row['cvar90_carbon'])

    metrics = {}
    for row in aggregate:
        method = row['method']
        if method not in expected_schedulers:
            raise ValueError(f"Unknown scheduler: {method}")
        if method in found_schedulers:
            raise ValueError(f"Duplicate scheduler: {method}")
        found_schedulers.add(method)

        n_ood = int(row['n_ood'])

        sla = float(row['sla_violation_rate'])
        if sla < 0:
            raise ValueError(f"Negative SLA counts: {sla}")

        exp_cost = float(row['exp_cost'])
        exp_carbon = float(row['exp_carbon'])
        cvar = float(row['cvar90_carbon'])

        reduction_carbon = (cm_carbon - exp_carbon) / cm_carbon * 100 if method != 'CM' else 0.0
        reduction_cvar = (cm_cvar - cvar) / cm_cvar * 100 if method != 'CM' else 0.0
        if row["input_checksum"] == "":
            raise ValueError("Missing input checksum")
        if "expected_checksum" not in locals():
            expected_checksum = row["input_checksum"]
        elif expected_checksum != row["input_checksum"]:
            raise ValueError("Inconsistent input checksums")

        metrics[method] = {
            'exp_cost': exp_cost,
            'exp_carbon': exp_carbon,
            'cvar90_carbon': cvar,
            'sla_violation_rate': sla,
            'std_cost': float(row['std_cost']),
            'std_carbon': float(row['std_carbon']),
            'runtime_sec': float(row['runtime_sec']),
            'reduction_carbon_vs_cm_pct': reduction_carbon,
            'reduction_cvar_vs_cm_pct': reduction_cvar,
            'input_checksum': row['input_checksum']
        }

    for row in paper_comparison:
        method = row['method']
        # the CSV might have empty strings for nulls
        paper_cost = float(row['paper_cost']) if row['paper_cost'] else None
        proj_cost = float(row['project_cost']) if row['project_cost'] else None
        paper_carbon = float(row['paper_carbon']) if row['paper_carbon'] else None
        proj_carbon = float(row['project_carbon']) if row['project_carbon'] else None
        paper_cvar90 = float(row['paper_cvar90']) if row['paper_cvar90'] else None
        proj_cvar90 = float(row['project_cvar90']) if row['project_cvar90'] else None
        paper_carbon_red = float(row['paper_carbon_reduction_vs_cm_pct']) if row['paper_carbon_reduction_vs_cm_pct'] else None
        paper_cvar_red = float(row['paper_cvar_reduction_vs_cm_pct']) if row['paper_cvar_reduction_vs_cm_pct'] else None

        metrics[method]['paper_comparison'] = {
            'paper_cost': paper_cost,
            'project_cost': proj_cost,
            'paper_carbon': paper_carbon,
            'project_carbon': proj_carbon,
            'paper_cvar90': paper_cvar90,
            'project_cvar90': proj_cvar90,
            'paper_carbon_reduction_vs_cm_pct': paper_carbon_red,
            'paper_cvar_reduction_vs_cm_pct': paper_cvar_red,
        }

    if found_schedulers != expected_schedulers:
        raise ValueError("Missing schedulers")

    git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=str(project_dir)).decode('utf-8').strip()

    final_data = {
        'source_commit': git_commit,
        'configuration': config,
        'provenance_classifications': {
            'caiso_north_carbon_rate': 'Measured',
            'caiso_north_nodal_prices': 'Measured',
            'additional_cloud_sites': 'Modeled',
            'renewable_availability_proxy': 'Modeled',
            'workload_traces': 'Generated',
            'ood_scenarios': 'Generated',
            'carbon_cvar09': 'Derived'
        },
        'metrics': metrics
    }

    out_path = project_dir / 'website/data/results.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(final_data, f, indent=2)

if __name__ == '__main__':
    generate_website_data()
