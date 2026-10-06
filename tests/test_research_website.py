import re
import json
import csv
from pathlib import Path

def test_six_methods_and_metrics():
    project_dir = Path(__file__).resolve().parent.parent
    website_dir = project_dir / 'website'
    artifact_dir = project_dir / 'artifacts/six_method_phase13_1000'

    with open(website_dir / 'data' / 'results.json') as f:
        data = json.load(f)

    metrics = data['metrics']
    schedulers = set(metrics.keys())
    assert schedulers == {'CM', 'CF', 'RF', 'SBS', 'RO', 'DRO'}

    # Read raw CSV to compare
    raw_metrics = {}
    with open(artifact_dir / 'aggregate_results.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_metrics[row['method']] = row

    assert set(raw_metrics.keys()) == schedulers

    cm_carbon = float(raw_metrics['CM']['exp_carbon'])
    cm_cvar = float(raw_metrics['CM']['cvar90_carbon'])

    for method in schedulers:
        exp_carbon = float(raw_metrics[method]['exp_carbon'])
        cvar = float(raw_metrics[method]['cvar90_carbon'])

        # Verify metric equality
        assert metrics[method]['exp_carbon'] == exp_carbon
        assert metrics[method]['cvar90_carbon'] == cvar

        # Verify reductions
        expected_red_carbon = (cm_carbon - exp_carbon) / cm_carbon * 100 if method != 'CM' else 0.0
        expected_red_cvar = (cm_cvar - cvar) / cm_cvar * 100 if method != 'CM' else 0.0
        assert round(metrics[method]['reduction_carbon_vs_cm_pct'], 4) == round(expected_red_carbon, 4)
        assert round(metrics[method]['reduction_cvar_vs_cm_pct'], 4) == round(expected_red_cvar, 4)

def test_n_ood_consistency():
    project_dir = Path(__file__).resolve().parent.parent
    artifact_dir = project_dir / 'artifacts/six_method_phase13_1000'

    with open(artifact_dir / 'configuration.json') as f:
        config = json.load(f)
    expected_n_ood = int(config['n_ood'])

    with open(artifact_dir / 'aggregate_results.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert int(row['n_ood']) == expected_n_ood

def test_checksums_present():
    project_dir = Path(__file__).resolve().parent.parent
    website_dir = project_dir / 'website'
    with open(website_dir / 'data' / 'results.json') as f:
        data = json.load(f)
    assert 'source_artifact_checksums' in data
    assert 'aggregate_results.csv' in data['source_artifact_checksums']

def test_cf_paper_cvar_not_reported():
    project_dir = Path(__file__).resolve().parent.parent
    website_dir = project_dir / 'website'
    with open(website_dir / 'data' / 'results.json') as f:
        data = json.load(f)
    assert data['metrics']['CF']['paper_comparison']['paper_cvar90'] is None

    with open(website_dir / 'index.html') as f:
        html = f.read()
    assert "Not reported" in html

def test_no_external_runtime_dependency():
    project_dir = Path(__file__).resolve().parent.parent
    with open(project_dir / 'website/index.html') as f:
        html = f.read()
    assert "http:" not in html and "https:" not in html

def test_no_accessibility_zoom_restriction():
    project_dir = Path(__file__).resolve().parent.parent
    with open(project_dir / 'website/index.html') as f:
        html = f.read()
    assert "user-scalable=no" not in html
    assert "maximum-scale=1.0" not in html

def test_readme_and_website_commands_match():
    project_dir = Path(__file__).resolve().parent.parent
    with open(project_dir / 'README.md') as f:
        readme = f.read()
    with open(project_dir / 'website/index.html') as f:
        html = f.read()

    cmd = "tools/run_benchmark.py"
    assert cmd in readme
    assert cmd in html

def test_other_textual_constraints():
    project_dir = Path(__file__).resolve().parent.parent
    with open(project_dir / 'website/index.html') as f:
        html = f.read()
    assert "Renewable-First" in html
    assert "Random Forest" not in html
    assert "phase13" not in html.lower()
    assert "exact reproduction" not in html.lower()
    assert "CVaR₀.₉ estimates average emissions among the worst 10% of evaluated outcomes. It is an evaluation metric, not a scheduler." in html

def test_stylesheet_link():
    project_dir = Path(__file__).resolve().parent.parent
    with open(project_dir / 'website/index.html') as f:
        html = f.read()

    # Check link exists and is inside <head>
    head_match = re.search(r'<head>(.*?)</head>', html, re.DOTALL)
    assert head_match is not None, "Missing <head> tag"
    head_content = head_match.group(1)

    assert '<link rel="stylesheet" href="./assets/tailwind.css">' in head_content
    assert '<link rel="stylesheet" href="./assets/tailwind.css">' not in html.replace(head_content, "")

    css_path = project_dir / 'website/assets/tailwind.css'
    assert css_path.exists()
    assert css_path.stat().st_size > 0

    with open(css_path) as f:
        css = f.read()

    # Check representative rules
    assert 'bg-surface-container' in css or 'bg-primary' in css or 'text-on-surface' in css

    # No external stylesheets
    assert "cdn.tailwindcss.com" not in html
    assert "fonts.googleapis.com" not in html

def test_local_server_css_response():
    import urllib.request
    import threading
    import http.server
    import socketserver

    project_dir = Path(__file__).resolve().parent.parent

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(project_dir / 'website'), **kwargs)

    port = 8000
    with socketserver.TCPServer(("", port), Handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()

        req = urllib.request.Request(f'http://localhost:{port}/assets/tailwind.css')
        try:
            with urllib.request.urlopen(req) as response:
                assert response.status == 200
                assert 'text/css' in response.headers.get('Content-Type', '')
        finally:
            httpd.shutdown()
