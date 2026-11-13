"""
RRT Yol Planlama Algoritması
INF330 Robotik Projesi - Galatasaray Üniversitesi
"""

import math
import time
import random
from typing import List, Tuple, Optional


class Node:
    def __init__(self, x, y, parent=None):
        self.x = x
        self.y = y
        self.parent = parent


def _dist(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)


def _line_free(grid, x1, y1, x2, y2):
    rows, cols = len(grid), len(grid[0])
    dx, dy = abs(x2-x1), abs(y2-y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy
    x, y = x1, y1
    while True:
        if not (0 <= x < rows and 0 <= y < cols) or grid[x][y] == 1:
            return False
        if x == x2 and y == y2:
            return True
        e2 = 2 * err
        old_x, old_y = x, y
        if e2 > -dy: err -= dy; x += sx
        if e2 < dx: err += dx; y += sy
        if x != old_x and y != old_y and (grid[x][old_y] or grid[old_x][y]):
            return False


def rrt(grid, start: Tuple[int, int], goal: Tuple[int, int],
        max_iter=10000, step=2, goal_bias=0.15, threshold=2, seed=None):
    """
    grid: 2D liste, 0=serbest 1=engel
    Döndürür: (path, süre_ms)
    """
    t0 = time.perf_counter()
    if not grid or not grid[0]:
        return None, 0.0
    rows, cols = len(grid), len(grid[0])
    if any(len(row) != cols for row in grid):
        raise ValueError('Grid must be rectangular')
    if any(not (0 <= x < rows and 0 <= y < cols) or grid[x][y] for x, y in (start, goal)):
        return None, (time.perf_counter() - t0) * 1000
    if step <= 0 or max_iter < 0 or not 0 <= goal_bias <= 1 or threshold < 0:
        raise ValueError('Invalid RRT parameters')
    if start == goal:
        return [start], (time.perf_counter() - t0) * 1000
    rng = random.Random(seed)

    nodes = [Node(*start)]

    for _ in range(max_iter):
        sample = goal if rng.random() < goal_bias else (
            rng.randint(0, rows-1), rng.randint(0, cols-1))

        nearest = min(nodes, key=lambda n: _dist((n.x, n.y), sample))
        dx = sample[0] - nearest.x
        dy = sample[1] - nearest.y
        d = math.sqrt(dx*dx + dy*dy)
        if d == 0:
            continue
        r = min(step / d, 1.0)
        nx, ny = int(round(nearest.x + dx*r)), int(round(nearest.y + dy*r))

        if not (0 <= nx < rows and 0 <= ny < cols) or grid[nx][ny] == 1:
            continue
        if not _line_free(grid, nearest.x, nearest.y, nx, ny):
            continue

        new_node = Node(nx, ny, nearest)
        nodes.append(new_node)

        if _dist((nx, ny), goal) <= threshold and _line_free(grid, nx, ny, *goal):
            goal_node = Node(*goal, new_node)
            path = []
            n = goal_node
            while n:
                path.append((n.x, n.y))
                n = n.parent
            path.reverse()
            # _smooth kaldırıldı
            return path, (time.perf_counter() - t0) * 1000

    return None, (time.perf_counter() - t0) * 1000
