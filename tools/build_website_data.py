import json
import csv
import sys
import math
import hashlib
from pathlib import Path

def get_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def check_finite(val, name):
    if not math.isfinite(val):
        raise ValueError(f"Value for {name} is not a finite number: {val}")
    return val

def generate_website_data():
    project_dir = Path(__file__).resolve().parent.parent
    artifact_dir = project_dir / 'artifacts/six_method_phase13_1000'

    conf_path = artifact_dir / 'configuration.json'
    agg_path = artifact_dir / 'aggregate_results.csv'
    paper_path = artifact_dir / 'paper_comparison.csv'

    # Calculate checksums
    checksums = {
        'configuration.json': get_sha256(conf_path),
        'aggregate_results.csv': get_sha256(agg_path),
        'paper_comparison.csv': get_sha256(paper_path),
    }

    # Load configuration
    with open(conf_path) as f:
        config = json.load(f)
    expected_n_ood = int(config['n_ood'])

    # Load aggregate results
    aggregate = []
    with open(agg_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            aggregate.append(row)

    # Load paper comparison
    paper_comparison = []
    with open(paper_path) as f:
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
        if n_ood != expected_n_ood:
            raise ValueError(f"Inconsistent case counts: {n_ood} != {expected_n_ood}")

        sla = check_finite(float(row['sla_violation_rate']), "sla")
        if sla < 0:
            raise ValueError(f"Negative SLA counts: {sla}")

        exp_cost = check_finite(float(row['exp_cost']), "exp_cost")
        exp_carbon = check_finite(float(row['exp_carbon']), "exp_carbon")
        cvar = check_finite(float(row['cvar90_carbon']), "cvar90_carbon")
        std_cost = check_finite(float(row['std_cost']), "std_cost")
        std_carbon = check_finite(float(row['std_carbon']), "std_carbon")
        runtime_sec = check_finite(float(row['runtime_sec']), "runtime_sec")

        if row["input_checksum"] == "":
            raise ValueError("Missing input checksum")
        if "expected_checksum" not in locals():
            expected_checksum = row["input_checksum"]
        elif expected_checksum != row["input_checksum"]:
            raise ValueError("Inconsistent input checksums")

        reduction_carbon = (cm_carbon - exp_carbon) / cm_carbon * 100 if method != 'CM' else 0.0
        reduction_cvar = (cm_cvar - cvar) / cm_cvar * 100 if method != 'CM' else 0.0

        metrics[method] = {
            'exp_cost': exp_cost,
            'exp_carbon': exp_carbon,
            'cvar90_carbon': cvar,
            'sla_violation_rate': sla,
            'std_cost': std_cost,
            'std_carbon': std_carbon,
            'runtime_sec': runtime_sec,
            'reduction_carbon_vs_cm_pct': reduction_carbon,
            'reduction_cvar_vs_cm_pct': reduction_cvar,
            'input_checksum': row['input_checksum']
        }

    found_paper_schedulers = set()
    for row in paper_comparison:
        method = row['method']
        if method not in expected_schedulers:
            raise ValueError(f"Unknown scheduler in paper comp: {method}")
        if method in found_paper_schedulers:
            raise ValueError(f"Duplicate paper comparison row: {method}")
        found_paper_schedulers.add(method)

        paper_cost = check_finite(float(row['paper_cost']), "paper_cost") if row['paper_cost'] else None
        proj_cost = check_finite(float(row['project_cost']), "project_cost") if row['project_cost'] else None
        paper_carbon = check_finite(float(row['paper_carbon']), "paper_carbon") if row['paper_carbon'] else None
        proj_carbon = check_finite(float(row['project_carbon']), "project_carbon") if row['project_carbon'] else None
        paper_cvar90 = check_finite(float(row['paper_cvar90']), "paper_cvar90") if row['paper_cvar90'] else None
        proj_cvar90 = check_finite(float(row['project_cvar90']), "project_cvar90") if row['project_cvar90'] else None
        paper_carbon_red = check_finite(float(row['paper_carbon_reduction_vs_cm_pct']), "paper_carbon_red") if row['paper_carbon_reduction_vs_cm_pct'] else None
        paper_cvar_red = check_finite(float(row['paper_cvar_reduction_vs_cm_pct']), "paper_cvar_red") if row['paper_cvar_reduction_vs_cm_pct'] else None

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
        raise ValueError("Missing schedulers in aggregate")
    if found_paper_schedulers != expected_schedulers:
        raise ValueError("Missing schedulers in paper comparison")

    final_data = {
        'source_artifact_checksums': checksums,
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
