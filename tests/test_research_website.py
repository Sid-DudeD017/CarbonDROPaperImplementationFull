import json
import re
import subprocess
from pathlib import Path

def test_website():
    project_dir = Path(__file__).resolve().parent.parent
    website_dir = project_dir / 'website'

    with open(website_dir / 'data' / 'results.json') as f:
        data = json.load(f)

    with open(website_dir / 'index.html') as f:
        html = f.read()

    metrics = data['metrics']
    schedulers = set(metrics.keys())

    assert schedulers == {'CM', 'CF', 'RF', 'SBS', 'RO', 'DRO'}

    assert f"{metrics['CM']['exp_cost']:.6f}" in html
    assert f"{metrics['CM']['cvar90_carbon']:.2f}" in html
    assert f"{metrics['RF']['exp_carbon']:.2f}" in html

    cm_cvar = metrics['CM']['cvar90_carbon']
    ro_cvar = metrics['RO']['cvar90_carbon']
    assert round(metrics['RO']['reduction_cvar_vs_cm_pct'], 2) == round(((cm_cvar - ro_cvar) / cm_cvar) * 100, 2)

    assert "CVaR₀.₉ estimates average emissions among the worst 10% of evaluated outcomes. It is an evaluation metric, not a scheduler." in html
    assert "Renewable-First" in html
    assert "Random Forest" not in html

    assert "phase13" not in html.lower()

    assert "exact reproduction" not in html.lower()

    assert "Measured" in html
    assert "Modeled" in html
    assert "Generated" in html
    assert "Derived" in html

    # Missing paper CF-CVaR is rendered "Not reported"
    assert "Not reported" in html

    # Offline checks
    assert "http:" not in html and "https:" not in html
    assert "user-scalable=no" not in html

    with open(project_dir / 'README.md') as f:
        readme = f.read()
    assert "tools/run_benchmark.py" in readme
    assert "tools/run_benchmark.py" in html

    # CLI argument parsing check
    with open(project_dir / 'tools' / 'run_benchmark.py') as f:
        run_py = f.read()
    assert "argparse" in run_py
    assert "--ood-cases" in run_py
    assert "--seed" in run_py

    print("All website tests passed.")

if __name__ == '__main__':
    test_website()
