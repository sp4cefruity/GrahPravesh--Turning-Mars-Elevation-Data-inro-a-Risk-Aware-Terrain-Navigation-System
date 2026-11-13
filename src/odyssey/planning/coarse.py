"""Planning grid reduction. Plan on at most `planning_grid_size` cells per side.

The full resolution grids stay the source of truth. This module builds a coarse copy
(block-reduce by an integer factor), maps cells between the two grids, and builds the
block-union masks that the planner uses to refine a coarse route back to full resolution.

Reduction rules (per block of f by f cells)
- continuous fields (dem, slope, roughness, hazard_prob, stds, cost_mean, cost_std, p_haz): mean
- hard_block and blocked: any (one blocked cell blocks the whole block, conservative)
- valid_mask: all (a block is valid only if every cell is valid)
- terrain_class and evidence_code: most frequent label, ties go to the lowest label
- aspect: circular mean

Edges that do not fill a whole block are padded by repeating the edge cells, so a partial block
behaves like its real cells.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation

from ..config import PipelineConfig
from ..contracts import Cell, CostMap, HazardMap, TerrainGrid


def factor(shape: tuple[int, int], config: PipelineConfig) -> int:
    """Block size f so that the coarse grid is at most planning_grid_size per side. 1 means no change."""
    n = max(1, int(config.planning_grid_size))
    m = max(shape)
    return 1 if m <= n else math.ceil(m / n)


def _blocks(a: np.ndarray, f: int) -> np.ndarray:
    """(..., H, W) to (..., nh, nw, f*f)."""
    h, w = a.shape[-2:]
    ph, pw = (-h) % f, (-w) % f
    if ph or pw:
        a = np.pad(a, [(0, 0)] * (a.ndim - 2) + [(0, ph), (0, pw)], mode="edge")
    hh, ww = a.shape[-2:]
    lead = a.shape[:-2]
    a = a.reshape(*lead, hh // f, f, ww // f, f).swapaxes(-3, -2)
    return a.reshape(*lead, hh // f, ww // f, f * f)


def reduce_mean(a: np.ndarray, f: int) -> np.ndarray:
    b = _blocks(np.asarray(a, dtype=float), f)
    ok = np.isfinite(b)
    cnt = ok.sum(-1)
    tot = np.where(ok, b, 0.0).sum(-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)


def reduce_any(a: np.ndarray, f: int) -> np.ndarray:
    return _blocks(np.asarray(a, dtype=bool), f).any(-1)


def reduce_all(a: np.ndarray, f: int) -> np.ndarray:
    return _blocks(np.asarray(a, dtype=bool), f).all(-1)


def reduce_mode(a: np.ndarray, f: int) -> np.ndarray:
    b = _blocks(a, f)
    best = np.zeros(b.shape[:2], dtype=a.dtype)
    best_n = np.full(b.shape[:2], -1)
    for label in np.unique(b):  # ascending, so a tie keeps the lowest label
        n = (b == label).sum(-1)
        better = n > best_n
        best = np.where(better, label, best)
        best_n = np.where(better, n, best_n)
    return best.astype(a.dtype)


def reduce_aspect(a: np.ndarray, f: int) -> np.ndarray:
    rad = np.radians(np.asarray(a, dtype=float))
    s, c = reduce_mean(np.sin(rad), f), reduce_mean(np.cos(rad), f)
    return np.degrees(np.arctan2(s, c)) % 360.0


def upsample(a: np.ndarray, f: int, shape: tuple[int, int]) -> np.ndarray:
    """Repeat each coarse cell f by f times, then crop to `shape`."""
    return np.repeat(np.repeat(a, f, axis=0), f, axis=1)[: shape[0], : shape[1]]


@dataclass
class CoarseGrid:
    f: int
    shape: tuple[int, int]  # full resolution shape
    terrain: TerrainGrid
    hazards: HazardMap
    cost_map: CostMap
    config: PipelineConfig  # start mapped to the coarse grid, inflate_r0 scaled to coarse cells

    def to_coarse(self, cell: Cell) -> Cell:
        return (int(cell[0]) // self.f, int(cell[1]) // self.f)

    def union(self, coarse_cells: list[Cell], dilate: int = 0) -> np.ndarray:
        """Full resolution mask of every block a coarse route passes through (optionally grown by blocks)."""
        m = np.zeros(self.cost_map.blocked.shape, dtype=bool)
        for r, c in coarse_cells:
            m[r, c] = True
        for _ in range(dilate):
            m = binary_dilation(m, structure=np.ones((3, 3), dtype=bool))
        return upsample(m, self.f, self.shape)

    def goal_cost_map(self, start: Cell, goal: Cell) -> CostMap:
        """Coarse cost map with the start and goal blocks opened.

        A block holding the start or a candidate is blocked at coarse level if any one of its cells
        is. The real cells are checked at full resolution when the route is refined, so opening the
        block here cannot let an unsafe path through.
        """
        blocked = self.cost_map.blocked.copy()
        blocked[start] = False
        blocked[goal] = False
        return CostMap(self.cost_map.cost_mean, self.cost_map.cost_std, self.cost_map.p_haz, blocked)


def make_coarse(terrain: TerrainGrid, hazards: HazardMap, cost_map: CostMap,
                config: PipelineConfig, f: int) -> CoarseGrid:
    """Block-reduce terrain, hazards and cost map by f. The cost map is reduced, not rebuilt, so the
    roughness percentile scale and the weights stay identical to the full resolution cost map."""
    shape = terrain.dem.shape
    c_terrain = TerrainGrid(
        dem=reduce_mean(terrain.dem, f),
        valid_mask=reduce_all(terrain.valid_mask, f),
        cell_size_m=terrain.cell_size_m * f,
        bands={k: reduce_mean(v, f) for k, v in terrain.bands.items()},
        simulated_layers=list(terrain.simulated_layers),
        slope_deg=reduce_mean(terrain.slope_deg, f),
        roughness=reduce_mean(terrain.roughness, f),
        aspect=None if terrain.aspect is None else reduce_aspect(terrain.aspect, f),
        source=terrain.source,
    )
    c_hazards = HazardMap(
        hazard_prob=reduce_mean(hazards.hazard_prob, f),
        terrain_class=reduce_mode(hazards.terrain_class, f),
        class_probs=reduce_mean(hazards.class_probs, f),
        epistemic_std=reduce_mean(hazards.epistemic_std, f),
        hard_block=reduce_any(hazards.hard_block, f),
        evidence=dict(hazards.evidence),
        slope_std_deg=None if hazards.slope_std_deg is None else reduce_mean(hazards.slope_std_deg, f),
        evidence_code=None if hazards.evidence_code is None else reduce_mode(hazards.evidence_code, f),
    )
    c_cost = CostMap(
        cost_mean=reduce_mean(cost_map.cost_mean, f),
        cost_std=reduce_mean(cost_map.cost_std, f),
        p_haz=reduce_mean(cost_map.p_haz, f),
        blocked=reduce_any(cost_map.blocked, f),
    )
    p = config.planning
    # The drift margin is defined in full resolution cells. In coarse cells the fixed part shrinks by f
    # and the growth per cell of distance is unchanged, so the margin stays the same in metres.
    c_config = dataclasses.replace(
        config,
        start=(int(config.start[0]) // f, int(config.start[1]) // f),
        planning=dataclasses.replace(p, inflate_r0=p.inflate_r0 / f),
    )
    return CoarseGrid(f=f, shape=shape, terrain=c_terrain, hazards=c_hazards, cost_map=c_cost, config=c_config)
