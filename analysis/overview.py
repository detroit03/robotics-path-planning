"""Readable summary figure: skip unmeasured metrics; never invent missing values."""
from collections import defaultdict
import math
from pathlib import Path
import statistics


def create_overview(rows, destination):
    if not rows:
        raise ValueError('No experiment records: no figure generated.')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row.get('obstacle_density', 'unknown'), row.get('obstacle_speed', 'unknown'))].append(row)
    candidates = [('plan_ms', 'Planning time (ms)', False), ('travel_time', 'Successful travel time (s)', True),
                  ('path_length_m', 'Successful traveled path (m)', True), ('path_steps', 'Legacy waypoint count', True),
                  ('replans', 'Replans', False), ('collisions', 'Contact episodes', False)]

    def values(group, key, successful):
        return [r[key] for r in group if (not successful or r['success'])
                and type(r.get(key)) in (int, float) and math.isfinite(r[key])]

    # A figure contains only metrics actually recorded in this input.
    selected = [m for m in candidates if values(rows, m[0], m[2])][:3]
    selected.append(('success', 'Success rate (%)', False))
    fig, axes = plt.subplots(len(grouped), len(selected), figsize=(4.5 * len(selected), 3.7 * len(grouped)),
                             squeeze=False, constrained_layout=True)
    fig.suptitle('Webots experiment results — means; error bars = sample standard deviation', fontsize=12)
    for row_index, ((density, speed), group) in enumerate(sorted(grouped.items())):
        by_alg = defaultdict(list)
        for record in group: by_alg[record['algorithm']].append(record)
        for ax, (metric, label, successful) in zip(axes[row_index], selected):
            upper = 0.0
            for index, (algorithm, experiments) in enumerate(sorted(by_alg.items())):
                data = [100 * r['success'] for r in experiments] if metric == 'success' else values(experiments, metric, successful)
                if not data:
                    ax.text(index, .08, 'not recorded', ha='center', fontsize=8, transform=ax.get_xaxis_transform())
                    continue
                mean = statistics.mean(data)
                deviation = statistics.stdev(data) if metric != 'success' and len(data) > 1 else 0
                upper = max(upper, mean + deviation)
                ax.bar(index, mean, width=.55, color=['#2563eb', '#16a34a', '#ea580c'][index % 3])
                if metric != 'success' and len(data) > 1:
                    ax.errorbar(index, mean, yerr=statistics.stdev(data), color='black', capsize=4)
                ax.annotate(f'{mean:.2f}\nn={len(data)}', (index, mean), xytext=(0, 5),
                            textcoords='offset points', ha='center', fontsize=8)
            ax.set_xticks(range(len(by_alg)))
            ax.set_xticklabels(sorted(by_alg))
            ax.set_title(f'{density} / {speed}\n{label}', fontsize=10)
            ax.set_ylim(0, upper * 1.4 if upper > 0 else 1)
            if metric == 'success': ax.set_ylim(0, 125)
            ax.grid(axis='y', alpha=.2)
            ax.set_axisbelow(True)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=150)
    plt.close(fig)
    return destination
