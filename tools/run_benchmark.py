#!/usr/bin/env python3
import sys
import argparse
import subprocess
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Benchmark runner wrapper")
    parser.add_argument('--ood-cases', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output-dir', type=str, default='reproduced_results')
    parser.add_argument('--input', type=str, default='example_data/paper_day_2025-08-05.csv')
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent.parent
    script = project_dir / 'tools' / 'run_phase13_six_method.py'

    cmd = [
        sys.executable, str(script),
        '--input', args.input,
        '--n-ood', str(args.ood_cases),
        '--seed', str(args.seed),
        '--output-dir', args.output_dir
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(project_dir))

if __name__ == '__main__':
    main()
