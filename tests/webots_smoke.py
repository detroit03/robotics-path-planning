"""Optional real Webots check in a temporary copy; never writes real experiment data."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import runpy
import re

parser = argparse.ArgumentParser()
parser.add_argument('--density', choices=('low', 'medium', 'high'), default='low')
parser.add_argument('--speed', choices=('static', 'slow', 'medium', 'fast'), default='static')
parser.add_argument('--algorithm', choices=('A*', 'Dijkstra', 'RRT'), default='RRT')
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]
webots = Path(os.environ.get('WEBOTS_EXECUTABLE',
    str(Path.home() / 'AppData/Local/Programs/Webots/msys64/mingw64/bin/webots.exe')))
with tempfile.TemporaryDirectory(prefix='webots-check-') as temporary:
    project = Path(temporary) / 'robotics_project'
    shutil.copytree(root, project,
                    ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.jpg', '*.png', '*.wbproj', 'webots_results.json', 'run_config.json'))
    controller = project / 'controllers/main_controller/main_controller.py'
    source = controller.read_text(encoding='utf-8')
    source = re.sub(r'^ALGORITHM\s*=\s*"[^"]+"', f'ALGORITHM = "{args.algorithm}"', source, flags=re.M)
    controller.write_text(source.replace(
        '    saved = True', '    saved = True\n    robot.simulationQuit(0)'), encoding='utf-8')
    world = runpy.run_path(str(project / 'worlds_config.py'))['select_world'](args.density, args.speed)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    process = subprocess.Popen([str(webots), '--batch', '--minimize', '--mode=fast', '--no-rendering',
                                '--stdout', '--stderr', str(world)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace', env=env,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        output, _ = process.communicate(timeout=45)
    except subprocess.TimeoutExpired as exc:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        else:
            process.kill()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            output = exc.output or b''
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='replace')
        print(output[-12000:])
        raise SystemExit('Webots check timed out; simulation not verified.')
    print(output[-12000:])
    results = project / 'results/webots_results.json'
    if process.returncode != 0 or not results.exists():
        raise SystemExit(f'Webots did not produce a completed experiment (exit {process.returncode}).')
    print(json.dumps(json.loads(results.read_text())['results'][-1], indent=2))
