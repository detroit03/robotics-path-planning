"""Scenario-aware descriptive statistics and exportable research artifacts."""
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import statistics
import re

from experiment_config import ALGORITHMS, DENSITIES, SPEEDS
from results_io import load_results, measurements

METRICS = {
    'plan_ms': False, 'initial_plan_ms': False, 'travel_time': True,
    'path_length_m': True, 'planned_path_length_m': True, 'path_efficiency': True,
    'replans': False, 'obstacle_events': False, 'collisions': False,
}


def statistics_for(values):
    if not values:
        return {'n': 0, 'mean': None, 'median': None, 'std': None, 'min': None, 'max': None}
    return {'n': len(values), 'mean': statistics.mean(values), 'median': statistics.median(values),
            'std': statistics.stdev(values) if len(values) > 1 else None,
            'min': min(values), 'max': max(values)}


def scenario_key(row):
    # Missing legacy speed remains unknown, never silently converted into static.
    return (row['algorithm'], row.get('obstacle_density', 'unknown'), row.get('obstacle_speed', 'unknown'))


def aggregate(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[scenario_key(row)].append(row)
    summaries = []
    for (algorithm, density, speed), group in sorted(grouped.items()):
        completed = sum(row['success'] for row in group)
        summary = {'algorithm': algorithm, 'density': density, 'speed': speed,
                   'runs': len(group), 'successes': completed, 'success_rate': completed / len(group),
                   'seeds': sorted({row['seed'] for row in group if row.get('seed') is not None}),
                   'failures': dict(Counter(row.get('reason', 'unknown') for row in group if not row['success']))}
        for key, successes_only in METRICS.items():
            summary[key] = statistics_for(measurements(group, key, successes_only))
        summary['failed_duration_s'] = statistics_for(measurements([r for r in group if not r['success']], 'travel_time'))
        summaries.append(summary)
    return summaries


def coverage(rows, expected_repeats):
    grouped = defaultdict(list)
    for row in rows:
        grouped[scenario_key(row)].append(row)
    matrix = []
    for algorithm in ALGORITHMS:
        for density in DENSITIES:
            for speed in SPEEDS:
                group = grouped[(algorithm, density, speed)]
                seeds = {row.get('seed') for row in group if row.get('seed') is not None}
                matrix.append({'algorithm': algorithm, 'density': density, 'speed': speed,
                               'runs': len(group), 'distinct_seeds': len(seeds),
                               'expected_repeats': expected_repeats,
                               'complete': len(seeds) >= expected_repeats,
                               'missing_repeats': max(0, expected_repeats - len(seeds))})
    return matrix


def write_csv(path, rows, fields):
    # Do not leave misleading files containing only a header.
    if not rows:
        path.unlink(missing_ok=True)
        return
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def number(value):
    return 'N/A' if value is None else f'{value:.3f}'


def export_payload(payload):
    """Keep the saved JSON readable without pages of unmeasured/null statistics."""
    exported = dict(payload)
    exported['groups'] = []
    for group in payload['groups']:
        compact = {}
        absent = []
        for key, value in group.items():
            if isinstance(value, dict) and 'n' in value:
                if value['n'] == 0:
                    absent.append(key)
                    continue
                compact[key] = {stat: measured for stat, measured in value.items() if measured is not None}
            else:
                compact[key] = value
        if absent:
            compact['unrecorded_metrics'] = absent
        exported['groups'].append(compact)
    return json.dumps(exported, indent=2, allow_nan=False)


def build_report(rows, output, expected_repeats=3, plots=True, infrastructure_errors=None):
    if expected_repeats < 1:
        raise ValueError('Expected repeats must be positive')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    previous_report = output / 'report.md'
    previous_images = set()
    if previous_report.is_file():
        previous_images = set(re.findall(r'!\[[^\]]*\]\(((?:comparison|trajectories)_[^/\\)]+\.png)\)',
                                         previous_report.read_text(encoding='utf-8')))
    summaries = aggregate(rows)
    matrix = coverage(rows, expected_repeats)
    warnings = []
    infrastructure_errors = infrastructure_errors or []
    if infrastructure_errors:
        warnings.append(f'{len(infrastructure_errors)} simulator/infrastructure errors were recorded separately; these are not robot failures.')
    if any(row.get('obstacle_speed') is None for row in rows):
        warnings.append('Legacy records without obstacle speed are grouped as unknown and do not fill the experiment matrix.')
    if any(row.get('seed') is None for row in rows):
        warnings.append('Some records have no seed; independent repeat coverage cannot be established for those records.')
    completed = sum(cell['complete'] for cell in matrix)
    if completed < len(matrix):
        warnings.append(f'Experiment matrix incomplete: {completed}/{len(matrix)} cells have {expected_repeats} distinct seeds.')
    if any(s['runs'] < 2 for s in summaries):
        warnings.append('Single-run groups have no sample standard deviation; no statistical significance is claimed.')
    signatures = {tuple(row.get(key) for key in ('max_speed', 'cell_size_m', 'max_run_seconds', 'max_replans', 'schema_version')) for row in rows}
    if len(signatures) > 1:
        warnings.append('Records have different or unknown measurement/configuration versions. Split input files before interpreting pooled means.')
    if len({row.get('source_sha256') for row in rows}) > 1:
        warnings.append('Input mixes source revisions or records with unknown source provenance.')
    if not rows:
        warnings.append('No completed experiment records found. No measurements have been fabricated.')
    payload = {'record_count': len(rows), 'expected_repeats': expected_repeats,
               'completed_cells': completed, 'total_cells': len(matrix),
               'warnings': warnings, 'groups': summaries, 'coverage': matrix}
    payload['infrastructure_errors'] = infrastructure_errors
    (output / 'summary.json').write_text(export_payload(payload), encoding='utf-8')
    flat = []
    for summary in summaries:
        base = {key: summary[key] for key in ('algorithm', 'density', 'speed', 'runs', 'successes', 'success_rate')}
        for metric in METRICS:
            for stat, value in summary[metric].items():
                base[f'{metric}_{stat}'] = value
        flat.append(base)
    base_fields = ['algorithm', 'density', 'speed', 'runs', 'successes', 'success_rate']
    fields = base_fields + [f'{m}_{s}' for m in METRICS for s in ('n', 'mean', 'median', 'std', 'min', 'max')
                           if any(summary[m]['n'] > 0 for summary in summaries)
                           and any(row.get(f'{m}_{s}') is not None for row in flat)]
    write_csv(output / 'summary.csv', [{key: row[key] for key in fields} for row in flat], fields)
    write_csv(output / 'coverage.csv', matrix, list(matrix[0]))
    failed = [{'algorithm': s['algorithm'], 'density': s['density'], 'speed': s['speed'],
               'reason': reason, 'count': count} for s in summaries for reason, count in s['failures'].items()]
    write_csv(output / 'failures.csv', failed, ['algorithm', 'density', 'speed', 'reason', 'count'])
    generated = []
    if plots and rows:
        try:
            generated = plot_report(rows, summaries, output)
        except ImportError:
            warnings.append('Matplotlib is unavailable; CSV and Markdown were generated without plots.')
    # Remove only figures explicitly linked by the previous generated report.
    # A later empty/different input must not retain stale experiment visualizations.
    for name in previous_images - set(generated):
        (output / name).unlink(missing_ok=True)
    lines = ['# Path planning experiment analysis', '',
             f'Records: {len(rows)}. Complete dynamic-scenario cells: {completed}/27; target: {expected_repeats} distinct seeds per cell.', '',
             '## Interpretation', '',
             '- Travel time, actual path length and efficiency include successful runs only.',
             '- Planning time, replans and proximity events include both successes and failures.',
             '- Failure counts remain in success-rate denominators. Failed-run durations are separately exported in JSON.',
             '- Missing values remain N/A; one observation does not define sample standard deviation.',
             '- Seed coverage is a reproducibility check, not proof of statistical independence.',
             '- Obstacle events are proximity-state entries, not measured physical collisions.',
             '- Collisions are rising edges of Webots contact above floor Z+0.01 m; persistent contact counts once. Ground contacts are excluded.',
             '- Descriptive means do not establish statistical significance or a universally best algorithm.', '',
             '## Warnings', ''] + [f'- {warning}' for warning in warnings or ['No coverage warning.']]
    lines += ['', '## Scenario summaries', '',
              '| Algorithm | Density | Speed | Runs | Success | Planning ms | Successful travel s | Successful path m | Replans |',
              '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for s in summaries:
        lines.append(f"| {s['algorithm']} | {s['density']} | {s['speed']} | {s['runs']} | {s['success_rate']:.1%} | {number(s['plan_ms']['mean'])} | {number(s['travel_time']['mean'])} | {number(s['path_length_m']['mean'])} | {number(s['replans']['mean'])} |")
    lines += ['', '## Failures', '']
    lines += [f"- {r['algorithm']} / {r['density']} / {r['speed']}: {r['reason']} = {r['count']}" for r in failed] or ['No failed simulation records.']
    lines += ['', '## Artifacts', '', '- [Coverage CSV](coverage.csv)', '- [Full statistics JSON](summary.json)']
    if flat: lines.append('- [Summary CSV](summary.csv)')
    else: lines.append('- No summary CSV: no completed simulation records.')
    if failed: lines.append('- [Failure CSV](failures.csv)')
    else: lines.append('- No failure CSV: no failed simulation records in this input.')
    missing_metrics = [metric for metric in METRICS if not any(summary[metric]['n'] > 0 for summary in summaries)]
    if missing_metrics:
        lines += ['', '## Unrecorded measurements', '', ', '.join(missing_metrics),
                  'These fields are omitted from the CSV, not filled with zeros.']
    lines.append('')
    lines += [f'![{name}]({name})' for name in generated]
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    # Include warnings added while plotting in the machine-readable report as well.
    (output / 'summary.json').write_text(export_payload(payload), encoding='utf-8')
    return payload


def plot_report(rows, summaries, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    artifacts = []
    # Separate each scenario before comparing algorithms; failed trials remain in success rates.
    scenario_pairs = sorted({(s['density'], s['speed']) for s in summaries})
    panels = [('success_rate', 'Success rate'), ('plan_ms', 'Total planning time (ms)'),
              ('travel_time', 'Successful travel time (s)'), ('path_length_m', 'Successful path (m)'),
              ('replans', 'Replans'), ('obstacle_events', 'Proximity events'),
              ('collisions', 'Above-floor contact episodes'), ('path_efficiency', 'Successful path efficiency')]
    for density, speed in scenario_pairs:
        selected = [s for s in summaries if (s['density'], s['speed']) == (density, speed)]
        available = [(metric, label) for metric, label in panels
                     if metric == 'success_rate' or any(s[metric]['n'] > 0 for s in selected)]
        columns = min(4, len(available))
        row_count = math.ceil(len(available) / columns)
        fig, axes = plt.subplots(row_count, columns, figsize=(4.2 * columns, 4 * row_count),
                                 squeeze=False, constrained_layout=True)
        fig.suptitle(f'Density: {density}; speed: {speed}')
        for ax in list(axes.flat)[len(available):]: ax.set_visible(False)
        for ax, (metric, label) in zip(axes.flat, available):
            for i, summary in enumerate(selected):
                value = summary[metric] if metric == 'success_rate' else summary[metric]['mean']
                if value is not None:
                    ax.bar(i, value, color=['#2563eb', '#16a34a', '#ea580c'][i % 3])
                    if metric != 'success_rate' and summary[metric]['std'] is not None:
                        ax.errorbar(i, value, yerr=summary[metric]['std'], color='black', capsize=4)
                else:
                    ax.text(i, .05, 'N/A', ha='center', transform=ax.get_xaxis_transform())
            ax.set_xticks(range(len(selected)))
            ax.set_xticklabels([s['algorithm'] for s in selected])
            ax.set_title(label)
            if metric == 'success_rate': ax.set_ylim(0, 1.05)
        name = f'comparison_{density}_{speed}.png'
        fig.savefig(output / name, dpi=140)
        plt.close(fig)
        artifacts.append(name)
    # One trajectory per algorithm in each scenario, labeled with its run/seed/outcome.
    traces = [row for row in rows if row.get('trajectory')]
    for density, speed in sorted({(r.get('obstacle_density', 'unknown'), r.get('obstacle_speed', 'unknown')) for r in traces}):
        fig, ax = plt.subplots(figsize=(7, 7), constrained_layout=True)
        seen = set()
        for row in traces:
            if (row.get('obstacle_density', 'unknown'), row.get('obstacle_speed', 'unknown')) != (density, speed) or row['algorithm'] in seen:
                continue
            seen.add(row['algorithm'])
            points = row['trajectory']
            ax.plot([p[1] for p in points], [p[2] for p in points], label=f"{row['algorithm']}, seed {row.get('seed')}, {'success' if row['success'] else row.get('reason', 'failed')}")
            if row.get('goal'): ax.scatter(*row['goal'], marker='*', color='black')
        ax.set(xlabel='X (m)', ylabel='Y (m)', title=f'Sampled trajectories: {density}/{speed}', xlim=(-1, 1), ylim=(-1, 1))
        ax.set_aspect('equal')
        ax.legend(fontsize=7)
        name = f'trajectories_{density}_{speed}.png'
        fig.savefig(output / name, dpi=140)
        plt.close(fig)
        artifacts.append(name)
    return artifacts
