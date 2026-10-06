#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

def main():
    project_dir = Path(__file__).resolve().parent.parent
    script = project_dir / 'tools' / 'run_phase13_six_method.py'

    # Map friendly arguments to the original script arguments if needed,
    # or just pass them through. We know the original used:
    # --input artifacts/six_method_phase13_1000/selected_input_day.csv --n-ood 1000 --seed 42 --output-dir reproduced_results

    cmd = [
        sys.executable, str(script),
        '--input', str(project_dir / 'artifacts' / 'six_method_phase13_1000' / 'selected_input_day.csv'),
        '--n-ood', '1000',
        '--seed', '42',
        '--output-dir', 'reproduced_results'
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(project_dir))

if __name__ == '__main__':
    main()
