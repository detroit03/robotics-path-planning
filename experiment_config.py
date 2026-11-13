"""Local run settings shared by the launcher, robot, obstacles and batch runner."""
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / 'run_config.json'
ALGORITHMS = ('A*', 'Dijkstra', 'RRT')
DENSITIES = ('low', 'medium', 'high')
SPEEDS = ('slow', 'medium', 'fast')


def load_config(path=CONFIG_FILE):
    if not Path(path).exists():
        return {}
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return validate_config(config)


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError('Run configuration must be an object')
    if 'algorithm' in config and config['algorithm'] not in ALGORITHMS:
        raise ValueError('Unknown algorithm')
    if 'seed' in config and (type(config['seed']) is not int or not 0 <= config['seed'] <= 2147483647):
        raise ValueError('Seed must be an integer between 0 and 2147483647')
    if 'batch' in config and type(config['batch']) is not bool:
        raise ValueError('Batch must be a boolean')
    if 'run_id' in config and (not isinstance(config['run_id'], str) or not config['run_id'].strip()):
        raise ValueError('Run ID must be a nonempty string')
    return config


def save_config(config, path=CONFIG_FILE):
    validate_config(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(config, indent=2), encoding='utf-8')
    temporary.replace(path)
