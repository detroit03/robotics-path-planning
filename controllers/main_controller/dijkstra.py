"""
Dijkstra Yol Planlama Algoritması
INF330 Robotik Projesi - Galatasaray Üniversitesi
"""

import heapq
import math
import time
from typing import List, Tuple, Optional


def dijkstra(grid, start: Tuple[int, int], goal: Tuple[int, int]):
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

    open_heap = [(0.0, start)]
    came_from = {start: None}
    dist = {start: 0.0}

    while open_heap:
        d, current = heapq.heappop(open_heap)

        if current == goal:
            path = []
            while current is not None:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path, (time.perf_counter() - t0) * 1000

        if d > dist.get(current, float('inf')):
            continue

        cx, cy = current
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]:
            nx, ny = cx+dx, cy+dy
            if 0 <= nx < rows and 0 <= ny < cols and grid[nx][ny] == 0:
                if dx and dy and (grid[cx + dx][cy] or grid[cx][cy + dy]):
                    continue
                cost = math.sqrt(2) if dx != 0 and dy != 0 else 1.0
                nd = d + cost
                if nd < dist.get((nx,ny), float('inf')):
                    dist[(nx,ny)] = nd
                    came_from[(nx,ny)] = current
                    heapq.heappush(open_heap, (nd, (nx,ny)))

    return None, (time.perf_counter() - t0) * 1000
