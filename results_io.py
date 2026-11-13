"""Read old experiments without inventing missing measurements."""
import json
import math
from pathlib import Path

RESULTS_FILE = Path(__file__).resolve().parent / 'results' / 'webots_results.json'


def load_results(path=RESULTS_FILE):
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    rows = data.get('results') if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError('Sonuc dosyasi bir liste veya results listesi icermeli.')
    normalized = []
    run_ids = set()
    for row in rows:
        if not isinstance(row, dict) or 'algorithm' not in row or not isinstance(row.get('success'), bool):
            raise ValueError('Gecersiz deney kaydi: algorithm ve success gerekli.')
        row = dict(row)
        if 'plan_ms' not in row:
            row['plan_ms'] = row.get('plan_time_ms')
        if not isinstance(row['algorithm'], str) or not row['algorithm'].strip():
            raise ValueError('Algorithm must be a nonempty string')
        for field in ('obstacle_density', 'obstacle_speed'):
            if row.get(field) is None:
                row.pop(field, None)
            elif (not isinstance(row[field], str) or not row[field]
                  or not all(character.isascii() and (character.isalnum() or character in '_-') for character in row[field])):
                raise ValueError(f'Invalid scenario label: {field}')
        for field in ('reason', 'world', 'source_sha256'):
            if field in row and not isinstance(row[field], str):
                raise ValueError(f'{field} must be a string')
        for metric in ('plan_ms', 'initial_plan_ms', 'travel_time', 'path_length_m',
                       'planned_path_length_m', 'replans', 'obstacle_events', 'collisions', 'path_efficiency'):
            value = row.get(metric)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError(f'Invalid nonnegative measurement: {metric}')
        if row.get('path_efficiency') is not None and row['path_efficiency'] > 1.000001:
            raise ValueError('Path efficiency cannot exceed one')
        if 'seed' in row and (type(row['seed']) is not int or row['seed'] < 0):
            raise ValueError('Seed must be a nonnegative integer')
        for field in ('replans', 'obstacle_events', 'collisions', 'path_steps'):
            if row.get(field) is not None and (type(row[field]) is not int or row[field] < 0):
                raise ValueError(f'{field} must be a nonnegative integer')
        for field in ('start', 'goal', 'end'):
            if field in row and (not isinstance(row[field], list) or len(row[field]) != 2
                                 or any(type(v) not in (int, float) or not math.isfinite(v) for v in row[field])):
                raise ValueError(f'{field} must contain two finite coordinates')
        if 'trajectory' in row:
            if not isinstance(row['trajectory'], list):
                raise ValueError('Trajectory must be a list')
            last_time = -1.0
            for point in row['trajectory']:
                if (not isinstance(point, list) or len(point) != 3
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
                        or point[0] < 0 or point[0] < last_time):
                    raise ValueError('Trajectory points must be finite [time, x, y] with nondecreasing time')
                last_time = point[0]
        if 'run_id' in row:
            if not isinstance(row['run_id'], str) or not row['run_id'] or row['run_id'] in run_ids:
                raise ValueError('Duplicate or invalid run_id')
            run_ids.add(row['run_id'])
        normalized.append(row)
    return normalized


def append_result(row, path=RESULTS_FILE):
    if not isinstance(row, dict):
        raise ValueError('Experiment record must be an object')
    path = Path(path)
    rows = load_results(path)
    rows.append(row)
    # Validate the new record as well as the existing data before replacing the file.
    for metric in ('plan_ms', 'travel_time', 'path_length_m'):
        value = row.get(metric)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError(f'Invalid measurement: {metric}')
    if row.get('run_id') and any(old.get('run_id') == row['run_id'] for old in rows[:-1]):
        raise ValueError('Duplicate run_id')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps({'results': rows}, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    try:
        load_results(temporary)
    except (ValueError, OSError):
        temporary.unlink(missing_ok=True)
        raise
    temporary.replace(path)


def measurements(rows, key, successful_only=False):
    return [row[key] for row in rows
            if (not successful_only or row['success'])
            and isinstance(row.get(key), (int, float))
            and not isinstance(row[key], bool) and math.isfinite(row[key])]
