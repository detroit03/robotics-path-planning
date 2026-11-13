"""Sequential, resumable Webots benchmark with one isolated project per run."""
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import re
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiment_config import ALGORITHMS, DENSITIES, SPEEDS, save_config
from main import find_webots
from results_io import append_result, load_results


def source_digest():
    digest = hashlib.sha256()
    files = list((ROOT / 'controllers').rglob('*.py')) + list((ROOT / 'worlds').glob('inf330*.wbt'))
    files += [ROOT / name for name in ('results_io.py', 'experiment_config.py', 'worlds_config.py')]
    files.append(Path(__file__).resolve())
    for path in sorted(files):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_one(algorithm, density, speed, seed, executable, timeout, identifier, log_dir):
    with tempfile.TemporaryDirectory(prefix='inf330-batch-') as directory:
        project = Path(directory) / 'project'
        project.mkdir()
        for name in ('controllers', 'worlds'):
            shutil.copytree(ROOT / name, project / name,
                            ignore=shutil.ignore_patterns('__pycache__', 'generated_*', '.*.jpg', '.*.wbproj'))
        for name in ('results_io.py', 'worlds_config.py', 'experiment_config.py'):
            shutil.copy2(ROOT / name, project / name)
        save_config({'algorithm': algorithm, 'seed': seed, 'batch': True, 'run_id': identifier}, project / 'run_config.json')
        # A subprocess loads world generation with its own __file__ rooted in this isolated copy.
        subprocess.run([sys.executable, '-B', '-c',
                        'from worlds_config import select_world; select_world(*__import__("sys").argv[1:])',
                        density, speed], cwd=project, check=True, capture_output=True)
        world = project / 'worlds' / f'generated_{density}_{speed}.wbt'
        text = world.read_text(encoding='utf-8')
        text = re.sub(r'WorldInfo\s*\{', f'WorldInfo {{\n  randomSeed {seed}', text, count=1)
        world.write_text(text, encoding='utf-8')
        log_path = log_dir / f'{identifier}.log'
        started = time.perf_counter()
        with log_path.open('w', encoding='utf-8') as log:
            command = [executable, '--batch', '--minimize', '--mode=fast', '--no-rendering',
                       '--stdout', '--stderr', str(world)]
            log.write(json.dumps({'run_id': identifier, 'algorithm': algorithm, 'density': density,
                                  'speed': speed, 'seed': seed, 'started_at': datetime.now(timezone.utc).isoformat()}) + '\n')
            log.flush()
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.kill()
                process.wait(timeout=10)
                log.write(f'\nSTATUS: infrastructure timeout after {timeout}s\n')
                log.flush()
                raise RuntimeError(f'Infrastructure timeout after {timeout}s; see {log_path}')
            log.write(f'\nSTATUS: Webots process exit {status}\n')
        if status:
            raise RuntimeError(f'Webots exit {status}; see {log_path}')
        records = load_results(project / 'results/webots_results.json')
        if len(records) != 1 or records[0].get('run_id') != identifier:
            raise RuntimeError(f'Expected exactly one matching experiment record; see {log_path}')
        row = records[0]
        row['wall_time_s'] = time.perf_counter() - started
        return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--algorithms', nargs='+', choices=ALGORITHMS, default=list(ALGORITHMS))
    parser.add_argument('--densities', nargs='+', choices=DENSITIES, default=list(DENSITIES))
    parser.add_argument('--speeds', nargs='+', choices=SPEEDS, default=list(SPEEDS))
    parser.add_argument('--seeds', nargs='+', type=int, default=[7, 8, 9])
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/benchmark.json')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not 0 < args.timeout < float('inf') or any(not 0 <= seed <= 2147483647 for seed in args.seeds):
        parser.error('Timeout must be finite and positive; seeds must be between 0 and 2147483647.')
    combinations = list(dict.fromkeys(itertools.product(args.algorithms, args.densities, args.speeds, args.seeds)))
    fingerprint = source_digest()
    print(f'{len(combinations)} runs; source {fingerprint[:12]}', flush=True)
    if args.dry_run:
        for case in combinations: print(case)
        return
    executable = find_webots()
    if os.name == 'nt' and Path(executable).name.lower() == 'webotsw.exe':
        console = Path(executable).with_name('webots.exe')
        if console.is_file(): executable = str(console)
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logs = args.output.parent / (args.output.stem + '_logs')
    logs.mkdir(exist_ok=True)
    done = {row.get('run_id') for row in load_results(args.output)}
    failures = []
    for index, (algorithm, density, speed, seed) in enumerate(combinations, 1):
        identifier = f"{fingerprint[:12]}_{algorithm.replace('*', 'star')}_{density}_{speed}_{seed}"
        if identifier in done:
            print(f'[{index}/{len(combinations)}] SKIP {identifier}', flush=True)
            continue
        print(f'[{index}/{len(combinations)}] RUN {identifier}', flush=True)
        try:
            row = run_one(algorithm, density, speed, seed, executable, args.timeout, identifier, logs)
            row['source_sha256'] = fingerprint
            append_result(row, args.output)
            print(f"  {row['reason']}: {row['travel_time']:.3f}s", flush=True)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            failures.append({'run_id': identifier, 'error': str(exc)})
            print(f'  ERROR: {exc}', flush=True)
            if len(failures) >= 3:
                print('Stopping after three infrastructure errors; inspect the logs before resuming.', flush=True)
                break
    manifest = {'generated_at': datetime.now(timezone.utc).isoformat(), 'source_sha256': fingerprint,
                'requested_runs': len(combinations), 'completed_records': len(load_results(args.output)),
                'infrastructure_errors': failures}
    args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    if failures: raise SystemExit(1)


if __name__ == '__main__':
    main()
