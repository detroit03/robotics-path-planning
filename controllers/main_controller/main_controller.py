from controller import Supervisor
import math, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from results_io import append_result
from experiment_config import load_config
from datetime import datetime, timezone
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from astar    import astar
from dijkstra import dijkstra
from rrt      import rrt

GRID_SIZE   = 40
CELL_SIZE   = 0.05
ORIGIN_X    = -1.0
ORIGIN_Y    = -1.0
ALGORITHM = "RRT"
CONFIG = load_config()
ALGORITHM = CONFIG.get('algorithm', ALGORITHM)
SEED = CONFIG.get('seed', 7)
MAX_SPEED   = 4.0
MAX_RUN_SECONDS = 180.0
MAX_REPLANS = 20
GOAL_THRESH = 0.08

def world_to_grid(wx, wy):
    gx = int((wx - ORIGIN_X) / CELL_SIZE)
    gy = int((wy - ORIGIN_Y) / CELL_SIZE)
    return (max(0, min(GRID_SIZE-1, gx)), max(0, min(GRID_SIZE-1, gy)))

def grid_to_world(gx, gy):
    return (ORIGIN_X + (gx + 0.5) * CELL_SIZE,
            ORIGIN_Y + (gy + 0.5) * CELL_SIZE)

def make_grid(obstacles):
    g = [[0]*GRID_SIZE for _ in range(GRID_SIZE)]
    for (gx, gy) in obstacles:
        if 0 <= gx < GRID_SIZE and 0 <= gy < GRID_SIZE:
            g[gx][gy] = 1
    return g

robot     = Supervisor()
timestep  = int(robot.getBasicTimeStep())
left_motor  = robot.getDevice("left wheel motor")
right_motor = robot.getDevice("right wheel motor")
left_motor.setPosition(float('inf'));  left_motor.setVelocity(0)
right_motor.setPosition(float('inf')); right_motor.setVelocity(0)
self_node = robot.getSelf()
contact_tracking = hasattr(self_node, 'enableContactPointsTracking')
if contact_tracking:
    self_node.enableContactPointsTracking(timestep, True)
print(f"[NODE] type={self_node.getTypeName()}")

ps = []
for i in range(8):
    s = robot.getDevice(f'ps{i}')
    s.enable(timestep)
    ps.append(s)

def get_pos():
    p = self_node.getPosition()
    return p[0], p[1]

def get_heading():
    ori = self_node.getOrientation()
    return math.atan2(ori[3], ori[0])

def get_obstacles():
    obs = set()
    ch = robot.getRoot().getField("children")
    for i in range(ch.getCount()):
        nd = ch.getMFNode(i)
        nf = nd.getField("name")
        nm = nf.getSFString().lower() if nf else nd.getTypeName().lower()
        if "box" in nm or "wooden" in nm or "dynamic_obstacle" in nm:
            tf = nd.getField("translation")
            if tf:
                t = tf.getSFVec3f()
                gx, gy = world_to_grid(t[0], t[1])
                size_field = nd.getField('size')
                size = size_field.getSFVec3f() if size_field else [0.1, 0.1, 0.1]
                # Circumscribed radius also covers rotated boxes.
                radius = math.hypot(size[0], size[1]) / 2 + 0.04
                cells = math.ceil(radius / CELL_SIZE)
                for ddx in range(-cells, cells + 1):
                    for ddy in range(-cells, cells + 1):
                        nx, ny = gx+ddx, gy+ddy
                        if 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                            obs.add((nx, ny))
    return obs

robot.step(timestep)
sx, sy = get_pos()
print(f"[POS] x={sx:.3f} y={sy:.3f}")
print(f"[DEBUG] raw grid: ({(sx-ORIGIN_X)/CELL_SIZE:.2f}, {(sy-ORIGIN_Y)/CELL_SIZE:.2f})")

start_g = world_to_grid(sx, sy)
goal_g  = (36, 36)
goal_w  = grid_to_world(*goal_g)
obs     = get_obstacles()

print(f"[INF330] Algoritma: {ALGORITHM}")
print(f"[INF330] Baslangic: ({sx:.3f},{sy:.3f}) -> grid {start_g}")
print(f"[INF330] Hedef: grid {goal_g} -> world {goal_w}")
print(f"[INF330] Engel sayisi: {len(obs)}")

obs.discard(start_g)
grid = make_grid(obs)

def plan(start, obstacles):
    grid = make_grid(obstacles)
    if ALGORITHM == 'A*':
        return astar(grid, start, goal_g)
    if ALGORITHM == 'Dijkstra':
        return dijkstra(grid, start, goal_g)
    if ALGORITHM == 'RRT':
        return rrt(grid, start, goal_g, max_iter=10000, seed=SEED + replans)
    raise ValueError(f'Unknown algorithm: {ALGORITHM}')

start_time = robot.getTime()
replans = 0
obstacle_events = 0
collisions = 0 if contact_tracking else None
in_contact = False
path_length = 0.0
previous_pos = (sx, sy)
saved = False
trajectory = [[0.0, sx, sy]]
last_sample = 0.0
run_id = CONFIG.get('run_id', uuid.uuid4().hex)

def save_result(success, reason):
    global saved
    if saved:
        return
    final_sample = [robot.getTime() - start_time, previous_pos[0], previous_pos[1]]
    if trajectory[-1] != final_sample:
        trajectory.append(final_sample)
    world_name = Path(robot.getWorldPath()).stem
    generated = world_name.split('_') if world_name.startswith('generated_') else []
    append_result({
        'algorithm': ALGORITHM, 'world': world_name,
        'schema_version': 2, 'run_id': run_id, 'seed': SEED,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'obstacle_density': {'inf330_world': 'low', 'inf330_medium': 'medium',
                             'inf330_high': 'high'}.get(world_name, generated[1] if generated else 'custom'),
        'obstacle_speed': generated[2] if generated else 'static',
        'max_speed': MAX_SPEED, 'plan_ms': plan_ms,
        'travel_time': robot.getTime() - start_time,
        'path_length_m': path_length, 'replans': replans,
        'obstacle_events': obstacle_events, 'success': success, 'reason': reason,
        'collisions': collisions,
        'collision_definition': 'contact episode above floor z+0.01m, including robot descendants',
        'initial_plan_ms': initial_plan_ms,
        'planned_path_length_m': planned_path_length,
        'path_efficiency': (math.hypot(previous_pos[0] - sx, previous_pos[1] - sy) / path_length
                            if path_length > 0 else None),
        'start': [sx, sy], 'goal': list(goal_w), 'end': list(previous_pos),
        'trajectory': trajectory, 'grid_size': GRID_SIZE, 'cell_size_m': CELL_SIZE,
        'max_run_seconds': MAX_RUN_SECONDS, 'max_replans': MAX_REPLANS,
    })
    saved = True
    if CONFIG.get('batch', False):
        robot.simulationQuit(0)

path, plan_ms = plan(start_g, obs)
initial_plan_ms = plan_ms
planned_path_length = (sum(math.dist(a, b) * CELL_SIZE for a, b in zip(path, path[1:]))
                       if path else None)
if not path:
    print("[HATA] Yol bulunamadi!")
    save_result(False, "no_path")
    while robot.step(timestep) != -1:
        left_motor.setVelocity(0); right_motor.setVelocity(0)
    sys.exit(0)

waypoints = [grid_to_world(gx, gy) for gx, gy in path]
print(f"[INF330] Yol: {len(waypoints)} adim, {plan_ms:.2f} ms")
print(f"[INF330] Heading: {get_heading():.3f} rad")
print(f"[INF330] Ilk wp: {waypoints[0]}")

wp_idx     = 0
reached    = False
stuck_time = robot.getTime()
stuck_dist = 9999.0

STOP_ENTER = 120.0
STOP_EXIT  = 80.0
in_stop    = False
path_available = True

while robot.step(timestep) != -1:
    if reached:
        left_motor.setVelocity(0); right_motor.setVelocity(0)
        continue
    rx, ry = get_pos()
    path_length += math.hypot(rx - previous_pos[0], ry - previous_pos[1])
    previous_pos = (rx, ry)
    if contact_tracking:
        contact = any(point.point[2] > 0.01 for point in self_node.getContactPoints(True))
        if contact and not in_contact:
            collisions += 1
        in_contact = contact
    elapsed = robot.getTime() - start_time
    if elapsed - last_sample >= 0.2:
        trajectory.append([elapsed, rx, ry])
        last_sample = elapsed
    if robot.getTime() - start_time > MAX_RUN_SECONDS:
        save_result(False, 'timeout')
        break
    if wp_idx >= len(waypoints):
        left_motor.setVelocity(0); right_motor.setVelocity(0)
        if math.hypot(rx - goal_w[0], ry - goal_w[1]) < GOAL_THRESH:
            save_result(True, 'goal_reached')
            print(f"[INF330] HEDEFE ULASTI! Sure: {robot.getTime()-start_time:.2f}s")
            reached = True
        else:
            save_result(False, 'goal_not_reached')
            break
        continue

    rx, ry = get_pos()
    h = get_heading()
    wx, wy = waypoints[wp_idx]
    dx, dy = wx-rx, wy-ry
    dist = math.sqrt(dx*dx + dy*dy)

    if path_available and dist < GOAL_THRESH:
        wp_idx += 1
        stuck_time = robot.getTime()
        stuck_dist = 9999.0
        in_stop = False
        continue

    # Takılma tespiti
    if path_available and abs(dist - stuck_dist) > 0.005:
        stuck_dist = dist
        stuck_time = robot.getTime()
    elif robot.getTime() - stuck_time > 1.5:
        left_motor.setVelocity(0); right_motor.setVelocity(0)
        if replans >= MAX_REPLANS:
            save_result(False, 'replan_limit')
            break
        obs = get_obstacles()
        current_g = world_to_grid(rx, ry)
        obs.discard(current_g)
        new_path, elapsed = plan(current_g, obs)
        plan_ms += elapsed
        replans += 1
        stuck_time = robot.getTime()
        stuck_dist = 9999.0
        if new_path:
            path = new_path
            waypoints = [grid_to_world(*point) for point in path]
            wp_idx = 0
            in_stop = False
            path_available = True
        else:
            path_available = False
        continue

    if not path_available:
        # Do not resume an obsolete route while waiting for a new feasible plan.
        left_motor.setVelocity(0); right_motor.setVelocity(0)
        continue

    # Hedef açısı
    target = math.atan2(dy, dx)
    diff   = target - h
    while diff >  math.pi: diff -= 2*math.pi
    while diff < -math.pi: diff += 2*math.pi

    # Proximity sensörler
    ps_val     = [s.getValue() for s in ps]
    right_obs  = max(ps_val[0], ps_val[1], ps_val[2])
    left_obs   = max(ps_val[5], ps_val[6], ps_val[7])
    front_only = min(ps_val[0], ps_val[7])
    max_obs    = max(right_obs, left_obs, front_only)

    # Histerezis: giriş ve çıkış eşikleri farklı
    if max_obs > STOP_ENTER:
        if not in_stop:
            obstacle_events += 1
        in_stop = True
    elif max_obs < STOP_EXIT:
        in_stop = False

    if in_stop:
        both_sides  = right_obs > STOP_ENTER and left_obs > STOP_ENTER
        turn_speed  = min(3.0, 1.0 + max_obs / 300.0)

        if both_sides:
            left_motor.setVelocity(-turn_speed)
            right_motor.setVelocity(-turn_speed)
        elif front_only > STOP_ENTER:
            if right_obs <= left_obs:
                left_motor.setVelocity(turn_speed)
                right_motor.setVelocity(-turn_speed)
            else:
                left_motor.setVelocity(-turn_speed)
                right_motor.setVelocity(turn_speed)
        elif right_obs > left_obs:
            left_motor.setVelocity(-turn_speed)
            right_motor.setVelocity(turn_speed)
        else:
            left_motor.setVelocity(turn_speed)
            right_motor.setVelocity(-turn_speed)

        continue

    # Normal sürüş
    if abs(diff) > 0.5:
        angular_speed = math.copysign(min(MAX_SPEED, abs(diff) * 2), diff)
        left_motor.setVelocity(-angular_speed)
        right_motor.setVelocity(angular_speed)
        continue
    turn  = max(-1.0, min(1.0, diff / math.pi))
    speed = MAX_SPEED * max(0.3, 1.0 - abs(turn) * 0.6)
    lv = max(-MAX_SPEED, min(MAX_SPEED, speed - turn * MAX_SPEED * 0.7))
    rv = max(-MAX_SPEED, min(MAX_SPEED, speed + turn * MAX_SPEED * 0.7))
    left_motor.setVelocity(lv)
    right_motor.setVelocity(rv)


left_motor.setVelocity(0)
right_motor.setVelocity(0)
if not saved:
    save_result(False, 'simulation_stopped')
