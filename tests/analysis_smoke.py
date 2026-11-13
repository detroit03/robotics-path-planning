"""Render real PNGs from legacy/pilot data and check nonblank output."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from results_io import load_results
from analysis.overview import create_overview
from analysis.report import build_report

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    for name in ('results_legacy.json', 'pilot_run.json'):
        rows = load_results(ROOT / 'examples' / name)
        image_path = create_overview(rows, output / f'{name}.png')
        import matplotlib.image as mpimg
        pixels = mpimg.imread(image_path)
        nonwhite = (pixels[:, :, :3].min(axis=2) < .85).mean()
        assert nonwhite > .05, (name, nonwhite)
    report = build_report(load_results(ROOT / 'examples/pilot_run.json'), output / 'report')
    assert report['completed_cells'] == 0
    assert list((output / 'report').glob('comparison_*.png'))
    assert list((output / 'report').glob('trajectories_*.png'))
    build_report([], output / 'report', plots=False)
    assert not list((output / 'report').glob('comparison_*.png'))
    assert not list((output / 'report').glob('trajectories_*.png'))
    try:
        create_overview([], output / 'empty.png')
    except ValueError:
        pass
    else:
        raise AssertionError('Empty input must not create a PNG')
    assert not (output / 'empty.png').exists()
print('PASS: legacy/pilot overviews are nonblank; scenario/trajectory plots render; empty input creates no PNG')
