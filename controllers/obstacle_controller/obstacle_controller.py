"""
Dinamik Engel Controller — Webots Supervisor API
INF330 Robotik Projesi - Galatasaray Üniversitesi

Her hareketli engele bu controller atanır.
Engel yoğunluğu ve hızı Webots dünya dosyasından (customData) okunur.
"""

from controller import Supervisor
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiment_config import load_config

# ── Ayarlar ──────────────────────────────────────────────────────────────────
ARENA_MIN = -0.9
ARENA_MAX =  0.9

SPEED_MAP = {
    "slow":   0.2,
    "medium": 0.5,
    "fast":   1.0,
}

def run():
    robot = Supervisor()
    timestep = int(robot.getBasicTimeStep())

    # customData alanından hız oku: "slow" | "medium" | "fast"
    self_node = robot.getSelf()
    custom    = self_node.getField("customData").getSFString()
    speed_key = custom.strip() if custom.strip() in SPEED_MAP else "medium"
    speed     = SPEED_MAP[speed_key]

    # Rastgele başlangıç yönü
    name = self_node.getField('name').getSFString()
    seed = load_config().get('seed', 7)
    rng = random.Random(seed + sum((i + 1) * ord(char) for i, char in enumerate(name)))
    angle = rng.uniform(0, 2 * math.pi)
    vx    = speed * math.cos(angle)
    vy    = speed * math.sin(angle)

    trans_field = self_node.getField("translation")

    while robot.step(timestep) != -1:
        dt  = timestep / 1000.0
        pos = trans_field.getSFVec3f()
        x   = pos[0] + vx * dt
        y   = pos[1] + vy * dt

        # Duvardan sekme
        if x < ARENA_MIN or x > ARENA_MAX:
            vx *= -1
            x = max(ARENA_MIN, min(ARENA_MAX, x))
        if y < ARENA_MIN or y > ARENA_MAX:
            vy *= -1
            y = max(ARENA_MIN, min(ARENA_MAX, y))

        trans_field.setSFVec3f([x, y, pos[2]])


if __name__ == "__main__":
    run()
