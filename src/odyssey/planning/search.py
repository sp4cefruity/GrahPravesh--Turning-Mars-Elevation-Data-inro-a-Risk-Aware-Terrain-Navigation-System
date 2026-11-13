"""A*, Dijkstra and corridor distances on an 8-connected grid.

Pure Python with heapq for now. It is fine at 64 by 64 and slow on 512 by 512.
Swap `_search` for a numba version when the real grid lands (same signature).

Edge cost between neighbours a and b is length * (price[a] + price[b]) / 2, where
price = base + cost_mean + k_alpha * cost_std and k_alpha = phi(z_alpha) / (1 - alpha).
That is the Gaussian CVaR of the per-cell cost. alpha = 0 gives k = 0 (bold).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra as sp_dijkstra
from scipy.stats import norm

from ..contracts import Cell

OFFSETS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
           (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)), (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]


def cvar_k(alpha: float) -> float:
    """phi(z_alpha) / (1 - alpha). Zero for alpha <= 0."""
    if alpha <= 0.0:
        return 0.0
    if alpha >= 1.0:
        raise ValueError("alpha must be below 1")
    return float(norm.pdf(norm.ppf(alpha)) / (1.0 - alpha))


def price_grid(cost_mean: np.ndarray, cost_std: np.ndarray, base: float, alpha: float) -> np.ndarray:
    return base + cost_mean + cvar_k(alpha) * cost_std


@dataclass
class SearchResult:
    cells: list[Cell]  # empty if unreachable
    cost: float  # inf if unreachable
    expanded: int


def _search(price: np.ndarray, passable: np.ndarray, start: Cell, goal: Cell,
            base: float, use_heuristic: bool) -> SearchResult:
    h, w = price.shape
    if not (passable[start] and passable[goal]):
        return SearchResult([], math.inf, 0)
    p = price.ravel().tolist()
    ok = passable.ravel().tolist()
    s = start[0] * w + start[1]
    g = goal[0] * w + goal[1]
    gr, gc = goal

    def heur(i: int) -> float:
        if not use_heuristic:
            return 0.0
        dr, dc = abs(i // w - gr), abs(i % w - gc)
        return base * (max(dr, dc) + (math.sqrt(2) - 1.0) * min(dr, dc))  # octile, admissible

    dist = {s: 0.0}
    parent: dict[int, int] = {}
    heap = [(heur(s), 0.0, s)]
    closed: set[int] = set()
    expanded = 0
    while heap:
        _, d, i = heapq.heappop(heap)
        if i in closed:
            continue
        closed.add(i)
        expanded += 1
        if i == g:
            path = [i]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            path.reverse()
            return SearchResult([(j // w, j % w) for j in path], d, expanded)
        r, c = divmod(i, w)
        for dr, dc, ln in OFFSETS:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < h and 0 <= cc < w):
                continue
            j = rr * w + cc
            if not ok[j] or j in closed:
                continue
            nd = d + ln * 0.5 * (p[i] + p[j])
            if nd < dist.get(j, math.inf):
                dist[j] = nd
                parent[j] = i
                heapq.heappush(heap, (nd + heur(j), nd, j))
    return SearchResult([], math.inf, expanded)


def astar(price: np.ndarray, passable: np.ndarray, start: Cell, goal: Cell, base: float) -> SearchResult:
    return _search(price, passable, start, goal, base, True)


def dijkstra(price: np.ndarray, passable: np.ndarray, start: Cell, goal: Cell) -> SearchResult:
    return _search(price, passable, start, goal, 0.0, False)


def distance_field(price: np.ndarray, passable: np.ndarray, source: Cell) -> np.ndarray:
    """Cost-to-reach from `source` to every passable cell (inf elsewhere). Uses scipy csgraph."""
    h, w = price.shape
    idx = np.arange(h * w).reshape(h, w)
    rows, cols, vals = [], [], []
    for dr, dc, ln in OFFSETS:
        r0, r1 = max(0, -dr), min(h, h - dr)
        c0, c1 = max(0, -dc), min(w, w - dc)
        a = (slice(r0, r1), slice(c0, c1))
        b = (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))
        both = passable[a] & passable[b]
        rows.append(idx[a][both])
        cols.append(idx[b][both])
        vals.append(ln * 0.5 * (price[a][both] + price[b][both]))
    graph = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                       shape=(h * w, h * w)).tocsr()
    d = sp_dijkstra(graph, directed=True, indices=source[0] * w + source[1])
    return d.reshape(h, w)


def corridor(price: np.ndarray, passable: np.ndarray, start: Cell, goal: Cell,
             best_cost: float, tau: float) -> np.ndarray:
    """Cells where D_start + D_goal <= (1 + tau) * best_cost."""
    d_s = distance_field(price, passable, start)
    d_g = distance_field(price, passable, goal)
    with np.errstate(invalid="ignore"):
        return (d_s + d_g) <= (1.0 + tau) * best_cost


def path_length_cells(cells: list[Cell]) -> float:
    return float(sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(cells, cells[1:])))
