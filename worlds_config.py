"""Generate optional moving-obstacle scenarios, keeping supplied worlds intact."""
from pathlib import Path

WORLDS = Path(__file__).resolve().parent / 'worlds'
BASE_WORLDS = {'low': 'inf330_world.wbt', 'medium': 'inf330_medium.wbt', 'high': 'inf330_high.wbt'}


def select_world(density='low', speed='static'):
    if density not in BASE_WORLDS or speed not in ('static', 'slow', 'medium', 'fast'):
        raise ValueError('Invalid scenario')
    base = WORLDS / BASE_WORLDS[density]
    if speed == 'static':
        return base
    count = {'low': 2, 'medium': 5, 'high': 10}[density]
    blocks = []
    for i in range(count):
        x = -.7 + (i % 5) * .3
        y = .55 - (i // 5) * .4
        blocks.append(f'''
Robot {{
  translation {x} {y} 0.05
  name "dynamic_obstacle_{i}"
  controller "obstacle_controller"
  supervisor TRUE
  customData "{speed}"
  children [
    Shape {{
      appearance PBRAppearance {{ baseColor 0.9 0.25 0.1 roughness 1 metalness 0 }}
      geometry Box {{ size 0.1 0.1 0.1 }}
    }}
  ]
  boundingObject Box {{ size 0.1 0.1 0.1 }}
}}
''')
    out = WORLDS / f'generated_{density}_{speed}.wbt'
    out.write_text(base.read_text(encoding='utf-8') + '\n'.join(blocks), encoding='utf-8')
    return out
