"""Standalone regression checks. Run from the repository: python -B tests/check.py."""
import ast
import contextlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'controllers/main_controller'))

def check_paths():
    from astar import astar
    from dijkstra import dijkstra
    from rrt import rrt, _line_free
    for fn in (astar, dijkstra, rrt):
        kwargs = {'seed': 7} if fn is rrt else {}
        for grid, start, goal in [([], (0, 0), (0, 0)), ([[1]], (0, 0), (0, 0)),
                                   ([[0]], (-1, 0), (0, 0)), ([[0, 1], [1, 0]], (0, 0), (1, 1))]:
            assert fn(grid, start, goal, **kwargs)[0] is None, fn.__name__
        assert fn([[0]], (0, 0), (0, 0), **kwargs)[0] == [(0, 0)]
        grid = [[0] * 10 for _ in range(10)]
        for y in range(9): grid[5][y] = 1
        path, _ = fn(grid, (0, 0), (9, 9), **kwargs)
        assert path and path[0] == (0, 0) and path[-1] == (9, 9)
        assert all(_line_free(grid, *a, *b) for a, b in zip(path, path[1:]))
    print('PASS: path validity, blocked corners, invalid endpoints, identical endpoints')

def check_results(tmp):
    from results_io import load_results, append_result, measurements
    from analysis.analyze import summarize
    path = tmp / 'results.json'
    path.write_text(json.dumps({'results': [{'algorithm': 'A*', 'success': True, 'plan_time_ms': .2}]}))
    rows = load_results(path)
    assert rows[0]['plan_ms'] == .2 and measurements(rows, 'path_length_m') == []
    with contextlib.redirect_stdout(io.StringIO()): assert 'A*' in summarize(rows)
    append_result({'algorithm': 'RRT', 'success': False, 'plan_ms': 1}, path)
    assert len(load_results(path)) == 2
    path.write_text('broken json')
    before = path.read_bytes()
    try: append_result({'algorithm': 'A*', 'success': True}, path)
    except ValueError: pass
    else: raise AssertionError('Corrupt result file must not be overwritten')
    assert path.read_bytes() == before
    print('PASS: legacy schema, append preservation, missing measurements, corrupt file protection')

def check_controller():
    import rrt
    import results_io
    import experiment_config
    saved_rrt, saved_append = rrt.rrt, results_io.append_result
    saved_config = experiment_config.load_config
    records = []
    class Motor:
        def setPosition(self, value): pass
        def setVelocity(self, value):
            if failed_replan and planner_calls > 1:
                assert value == 0, 'Robot drove along an invalid old path after failed replanning'
    class Sensor:
        def enable(self, step): pass
        def getValue(self): return 0
    class Node:
        def getTypeName(self): return 'Robot'
        def getPosition(self): return [*robot.position, 0]
        def getOrientation(self): return [1, 0, 0, 0, 1, 0, 0, 0, 1]
    class Children:
        def getCount(self): return 0
    class Supervisor:
        def __init__(self):
            self.time = 0
            self.position = (-.9, -.9)
        def getBasicTimeStep(self): return 32
        def getDevice(self, name): return Sensor() if name.startswith('ps') else Motor()
        def getSelf(self): return Node()
        def getRoot(self): return types.SimpleNamespace(getField=lambda name: Children())
        def getTime(self): return self.time
        def getWorldPath(self): return '/worlds/inf330_world.wbt'
        def step(self, step):
            self.time += step / 1000
            if moving:
                offset = min(self.time * .3, 1.725)
                self.position = (-.9 + offset, -.9 + offset)
            return -1 if self.time > 80 or records else 0
    previous = sys.modules.get('controller')
    try:
        experiment_config.load_config = lambda: {'algorithm': 'RRT'}
        results_io.append_result = lambda row: records.append(row)
        def planner(*args, **kwargs):
            nonlocal planner_calls
            planner_calls += 1
            return (None if failed_replan and planner_calls > 1 else [(2, 2), (36, 36)]), .1
        rrt.rrt = planner
        for moving, failed_replan in ((False, False), (True, False), (False, True)):
            planner_calls = 0
            records.clear()
            robot = Supervisor()
            sys.modules['controller'] = types.SimpleNamespace(Supervisor=lambda: robot)
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(ROOT / 'controllers/main_controller/main_controller.py'))
            assert len(records) == 1 and records[0]['success'] is moving, records
            if not moving: assert records[0]['replans'] == 20 and records[0]['reason'] == 'replan_limit'
    finally:
        experiment_config.load_config = saved_config
        rrt.rrt, results_io.append_result = saved_rrt, saved_append
        if previous is None: sys.modules.pop('controller', None)
        else: sys.modules['controller'] = previous
    print('PASS: frozen robot fails after bounded replanning; actual goal proximity succeeds; exactly one record')


def check_analysis(tmp):
    from analysis.report import aggregate, build_report, coverage
    from results_io import append_result, load_results
    rows = [
        {'algorithm': 'A*', 'success': True, 'obstacle_density': 'low', 'obstacle_speed': 'slow',
         'seed': 7, 'plan_ms': 2, 'travel_time': 10, 'path_length_m': 3},
        {'algorithm': 'A*', 'success': False, 'reason': 'timeout', 'obstacle_density': 'low',
         'obstacle_speed': 'slow', 'seed': 8, 'plan_ms': 4, 'travel_time': 180, 'path_length_m': 9},
        {'algorithm': 'Dijkstra', 'success': True, 'obstacle_density': 'low', 'plan_ms': 1},
    ]
    a = next(g for g in aggregate(rows) if g['algorithm'] == 'A*')
    assert a['success_rate'] == .5 and a['plan_ms']['mean'] == 3
    assert a['travel_time']['mean'] == 10 and a['path_length_m']['mean'] == 3
    assert a['failed_duration_s']['mean'] == 180 and a['failures'] == {'timeout': 1}
    matrix = coverage(rows, 3)
    assert len(matrix) == 27 and not any(cell['complete'] for cell in matrix)
    result = build_report(rows, tmp / 'report', 3, plots=False)
    assert result['record_count'] == 3 and result['warnings']
    assert (tmp / 'report/summary.csv').exists() and (tmp / 'report/report.md').exists()
    assert build_report([], tmp / 'empty', plots=False)['completed_cells'] == 0
    assert not (tmp / 'empty/summary.csv').exists()
    assert not (tmp / 'empty/failures.csv').exists()
    success_only = [rows[0]]
    build_report(success_only, tmp / 'one', plots=False)
    assert not (tmp / 'one/failures.csv').exists()
    csv_header = (tmp / 'one/summary.csv').read_text().splitlines()[0]
    assert 'collisions_' not in csv_header and '_std' not in csv_header
    saved_summary = json.loads((tmp / 'one/summary.json').read_text())['groups'][0]
    assert 'collisions' not in saved_summary
    assert 'collisions' in saved_summary['unrecorded_metrics']
    assert 'std' not in saved_summary['plan_ms']
    path = tmp / 'strict.json'
    append_result({'algorithm': 'A*', 'success': True, 'run_id': 'one', 'plan_ms': 2}, path)
    original = path.read_bytes()
    for row in ({'algorithm': 'A*', 'success': True, 'plan_ms': -1},
                {'algorithm': 'A*', 'success': True, 'run_id': 'one'},
                {'algorithm': 'A*', 'success': 'true'},
                {'algorithm': 'A*', 'success': True, 'obstacle_density': '../escape'},
                {'algorithm': 'A*', 'success': True, 'trajectory': [[1, 2]]},
                {'algorithm': 'A*', 'success': True, 'trajectory': [[2, 1, 1], [1, 1, 1]]},
                {'algorithm': 'A*', 'success': True, 'goal': [1]},
                {'algorithm': 'A*', 'success': True, 'reason': []}):
        try: append_result(row, path)
        except ValueError: pass
        else: raise AssertionError('Invalid experiment accepted')
        assert path.read_bytes() == original
    print('PASS: scenario statistics, failure denominators, success-only metrics, legacy coverage and invalid data protection')


def check_startup_log(tmp):
    from experiments import run as runner
    real = runner.subprocess
    class FailedProcess:
        def wait(self, timeout): return 9
    runner.subprocess = types.SimpleNamespace(run=real.run, Popen=lambda *args, **kwargs: FailedProcess(),
                                             STDOUT=real.STDOUT, CREATE_NO_WINDOW=getattr(real, 'CREATE_NO_WINDOW', 0),
                                             TimeoutExpired=real.TimeoutExpired)
    logs = tmp / 'logs'
    logs.mkdir()
    try:
        try:
            runner.run_one('A*', 'low', 'slow', 7, 'unused-test-executable', 1, 'failed-start', logs)
        except RuntimeError as exc:
            assert 'exit 9' in str(exc)
        else:
            raise AssertionError('Failed simulator start was accepted')
    finally:
        runner.subprocess = real
    content = (logs / 'failed-start.log').read_text()
    assert 'failed-start' in content and 'process exit 9' in content
    print('PASS: silent simulator startup failures retain nonempty run metadata and exit status')


def check_config_and_cli(tmp):
    from experiment_config import load_config, save_config
    from analysis.analyze import main as analyze
    config_path = tmp / 'settings/config.json'
    save_config({'algorithm': 'A*', 'seed': 7}, config_path)
    original = config_path.read_bytes()
    for invalid in ({'seed': 2147483648}, {'run_id': None}, {'batch': 1}):
        try: save_config(invalid, config_path)
        except ValueError: pass
        else: raise AssertionError('Invalid configuration was saved')
        assert config_path.read_bytes() == original
        assert not config_path.with_suffix('.json.tmp').exists()
    config_path.write_text('\ufeff' + original.decode(), encoding='utf-8')
    assert load_config(config_path)['algorithm'] == 'A*'
    invalid_input = tmp / 'invalid.json'
    invalid_input.write_text('not JSON')
    with contextlib.redirect_stdout(io.StringIO()):
        assert analyze(['--input', str(invalid_input), '--output', str(tmp / 'invalid-report')]) == 1
    print('PASS: local settings validation/preservation, BOM compatibility and analysis CLI error status')

if __name__ == '__main__':
    for path in ROOT.rglob('*.py'):
        if '.venv' not in path.parts: ast.parse(path.read_text(encoding='utf-8-sig'))
    check_paths()
    with tempfile.TemporaryDirectory() as directory:
        check_results(Path(directory))
        check_analysis(Path(directory))
        check_startup_log(Path(directory))
        check_config_and_cli(Path(directory))
    check_controller()
    print('All robotics checks passed.')
