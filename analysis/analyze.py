"""Analyze legacy and new Webots results from any working directory."""
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from results_io import RESULTS_FILE, load_results, measurements


def load():
    return load_results()


def mean_text(values, precision=2):
    return f'{sum(values) / len(values):.{precision}f}' if values else 'N/A'


def summarize(data):
    by_alg = defaultdict(list)
    for row in data:
        by_alg[row['algorithm']].append(row)
    print(f"{'Algoritma':<12} {'Basari':>8} {'Plan(ms)':>10} {'Yol(m)':>10} {'Replan':>8}")
    for alg, rows in by_alg.items():
        success = sum(row['success'] for row in rows) / len(rows)
        print(f"{alg:<12} {success:>7.1%} "
              f"{mean_text(measurements(rows, 'plan_ms')):>10} "
              f"{mean_text(measurements(rows, 'path_length_m', True), 3):>10} "
              f"{mean_text(measurements(rows, 'replans'), 1):>8}")
    print('N/A: Bu olcum eski kayitlarda bulunmuyor.')
    return by_alg


def plot(by_alg, destination=None):
    from analysis.overview import create_overview
    rows = [row for experiments in by_alg.values() for row in experiments]
    out = destination or RESULTS_FILE.parent / 'webots_results.png'
    create_overview(rows, out)
    print(f'Grafik kaydedildi: {out}')


def main(argv=None):
    import argparse
    from analysis.report import build_report
    parser = argparse.ArgumentParser(description='Scenario statistics, coverage, CSV and plots')
    parser.add_argument('--input', type=Path, default=RESULTS_FILE)
    parser.add_argument('--output', type=Path, default=RESULTS_FILE.parent / 'analysis')
    parser.add_argument('--expected-repeats', type=int, default=3)
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--manifest', type=Path, help='Optional experiment infrastructure log')
    args = parser.parse_args(argv)
    try:
        data = load_results(args.input)
        import json
        manifest = args.manifest or args.input.with_suffix('.manifest.json')
        infrastructure = (json.loads(manifest.read_text(encoding='utf-8')).get('infrastructure_errors', [])
                          if manifest.exists() else [])
        result = build_report(data, args.output, args.expected_repeats, not args.no_plots, infrastructure)
        if data and not args.no_plots:
            from analysis.overview import create_overview
            try:
                overview = create_overview(data, args.output.parent / 'webots_results.png')
                print(f'Overview: {overview}')
            except ImportError:
                print('Matplotlib is required for the overview.')
    except (OSError, ValueError) as exc:
        print(f'Sonuclar okunamadi: {exc}')
        return 1
    print(f"Records: {result['record_count']}; complete cells: {result['completed_cells']}/27")
    print(f'Input: {args.input.resolve()}')
    if not data:
        print('No measured records: no PNG generated. Run experiments/run.py or specify --input with an existing result file.')
    for warning in result['warnings']: print(f'WARNING: {warning}')
    print(f"Report: {args.output / 'report.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
