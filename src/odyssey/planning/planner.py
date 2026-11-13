"""Planning stages: cost map, one path per candidate and mode, extras for the default goal.

Rules this file enforces
- Planning runs on the inflated blocked mask. Verification runs on the true blocked mask.
- No safe path means an empty path with a reason. A risky path is never returned.
- A* is the planner. Dijkstra is the optimality check (cost and nodes expanded).
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from ..config import PipelineConfig
from ..contracts import (Candidate, Cell, CostMap, HazardMap, MODES, PathResult, PlanExtras,
                         RiskCurvePoint, SegmentCost, TerrainGrid)
from .coarse import CoarseGrid, factor as coarse_factor, make_coarse, upsample
from .costmap import build_cost_map, inflate_blocked
from .safety import SafetyViolation, verify_path
from .search import (SearchResult, astar, corridor, cvar_k, dijkstra, path_length_cells,
                     price_grid)

__all__ = ["build_cost_map", "plan_paths", "plan_extras", "plan_one"]


def _alpha(config: PipelineConfig, mode: str) -> float:
    if mode == "bold":
        return config.planning.alpha_bold
    if mode == "cautious":
        return config.planning.alpha_cautious
    raise ValueError(f"unknown mode {mode!r}")


def _segments(cells: list[Cell], price: np.ndarray, cost_map: CostMap, terrain: TerrainGrid,
              base: float, alpha: float) -> list[SegmentCost]:
    k = cvar_k(alpha)
    out = []
    for a, b in zip(cells, cells[1:]):
        ln = math.hypot(a[0] - b[0], a[1] - b[1])
        mean = 0.5 * (cost_map.cost_mean[a] + cost_map.cost_mean[b])
        risk = k * 0.5 * (cost_map.cost_std[a] + cost_map.cost_std[b])
        out.append(SegmentCost(
            from_cell=a, to_cell=b, length_cells=ln,
            base=ln * base, mean=ln * float(mean), risk_term=ln * float(risk),
            edge_cost=ln * 0.5 * float(price[a] + price[b]),
            slope_deg=float(terrain.slope_deg[b]), p_haz=float(cost_map.p_haz[b]),
        ))
    return out


def _no_path(mode: str, alpha: float, cid: Optional[str], reason: str,
             min_risk: Optional[float], baseline: Optional[str] = None, planner: str = "astar") -> PathResult:
    return PathResult(cells=[], total_cost=math.inf, risk_score=math.inf, max_slope_on_path=math.nan,
                      safe=False, planner=planner, mode=mode, alpha=alpha, corridor_mask=None,
                      min_feasible_risk=min_risk, baseline=baseline, candidate_id=cid,
                      no_safe_path_reason=reason)


def _min_feasible_risk(terrain: TerrainGrid, cost_map: CostMap, start: Cell, goal: Cell) -> Optional[float]:
    """Lowest total p_haz over any route that respects the true hard blocks (margin ignored).

    None when the goal cannot be reached even then. This is a diagnostic number, the route
    itself is never returned.
    """
    price = 1e-3 + cost_map.p_haz
    res = dijkstra(price, ~cost_map.blocked, start, goal)
    if not res.cells:
        return None
    return float(sum(cost_map.p_haz[c] for c in res.cells))


def plan_one(terrain: TerrainGrid, cost_map: CostMap, start: Cell, goal: Cell, mode: str,
             config: PipelineConfig, candidate_id: Optional[str] = None,
             inflated: Optional[np.ndarray] = None) -> PathResult:
    p = config.planning
    alpha = _alpha(config, mode)
    if inflated is None:
        inflated = inflate_blocked(cost_map.blocked, start, p.inflate_r0, p.inflate_growth)
    passable = ~inflated
    price = price_grid(cost_map.cost_mean, cost_map.cost_std, p.base_cost, alpha)

    res = astar(price, passable, start, goal, p.base_cost)
    if not res.cells:
        if cost_map.blocked[goal]:
            why = "goal cell is a hard block or has no valid data"
        elif cost_map.blocked[start]:
            why = "start cell is blocked"
        elif inflated[goal]:
            why = "goal lies inside the drift margin of a blocked cell"
        else:
            why = "no connected route avoids blocked cells and their drift margin"
        return _no_path(mode, alpha, candidate_id, why, _min_feasible_risk(terrain, cost_map, start, goal))

    dij_cost = dij_exp = None
    if p.cross_check_dijkstra:
        d = dijkstra(price, passable, start, goal)
        dij_cost, dij_exp = d.cost, d.expanded
        if not math.isclose(d.cost, res.cost, rel_tol=1e-9, abs_tol=1e-9):
            raise AssertionError(f"A* cost {res.cost} differs from Dijkstra cost {d.cost} for goal {goal}")

    # raises SafetyViolation, on the TRUE mask
    report = verify_path(res.cells, cost_map.blocked, terrain.slope_deg, cost_map.p_haz)
    return PathResult(
        cells=res.cells, total_cost=res.cost, risk_score=report.risk_score,
        max_slope_on_path=report.max_slope, safe=report.safe, planner="astar", mode=mode, alpha=alpha,
        corridor_mask=corridor(price, passable, start, goal, res.cost, p.corridor_tau),
        min_feasible_risk=None, baseline=None, candidate_id=candidate_id,
        segments=_segments(res.cells, price, cost_map, terrain, p.base_cost, alpha),
        nodes_expanded=res.expanded, dijkstra_cost=dij_cost, dijkstra_nodes_expanded=dij_exp,
    )


def _refine(cells: list[Cell], grid: CoarseGrid, price: np.ndarray, passable: np.ndarray,
            start: Cell, goal: Cell, base: float) -> tuple[SearchResult, np.ndarray]:
    """Turn a coarse route into a full resolution route.

    A* runs at full resolution, but only inside the blocks the coarse route crosses (then, if that
    fails, inside those blocks grown by one block), and only on `passable` full resolution cells.
    Returns the result and the mask it searched. Empty cells mean the refinement failed.
    """
    expanded = 0
    mask = np.zeros_like(passable)
    for dilate in (0, 1):
        mask = grid.union(cells, dilate) & passable
        res = astar(price, mask, start, goal, base)
        expanded += res.expanded
        if res.cells:
            return SearchResult(res.cells, res.cost, expanded), mask
    return SearchResult([], math.inf, expanded), mask


_REFINE_FAIL = ("route on the coarse planning grid could not be refined to full resolution "
                "without crossing a blocked cell or its drift margin")


def _plan_one_coarse(terrain: TerrainGrid, cost_map: CostMap, grid: CoarseGrid, start: Cell, goal: Cell,
                     mode: str, config: PipelineConfig, cid: Optional[str],
                     coarse_inflated: np.ndarray, full_inflated: np.ndarray) -> PathResult:
    p = config.planning
    alpha = _alpha(config, mode)
    if cost_map.blocked[goal] or cost_map.blocked[start]:
        # nothing to refine, the full resolution answer is immediate and exact
        return plan_one(terrain, cost_map, start, goal, mode, config, cid, full_inflated)
    sc, gc = grid.to_coarse(start), grid.to_coarse(goal)
    c_cost = grid.goal_cost_map(sc, gc)
    c_infl = coarse_inflated.copy()
    c_infl[gc] = False  # full resolution margin is enforced during refinement
    coarse = plan_one(grid.terrain, c_cost, sc, gc, mode, grid.config, cid, c_infl)
    if not coarse.cells:
        mfr = None if coarse.min_feasible_risk is None else coarse.min_feasible_risk * grid.f  # approximate
        return _no_path(mode, alpha, cid, coarse.no_safe_path_reason or "no safe path", mfr)

    price = price_grid(cost_map.cost_mean, cost_map.cost_std, p.base_cost, alpha)
    res, mask = _refine(coarse.cells, grid, price, ~full_inflated, start, goal, p.base_cost)
    if not res.cells:
        # rare, so the slow full resolution diagnostic is acceptable here
        return _no_path(mode, alpha, cid, _REFINE_FAIL, _min_feasible_risk(terrain, cost_map, start, goal))
    dij_cost = dij_exp = None
    dij_total = coarse.dijkstra_nodes_expanded or 0
    if p.cross_check_dijkstra:
        d = dijkstra(price, mask, start, goal)
        dij_cost, dij_exp = d.cost, d.expanded + dij_total
        if not math.isclose(d.cost, res.cost, rel_tol=1e-9, abs_tol=1e-9):
            raise AssertionError(f"A* cost {res.cost} differs from Dijkstra cost {d.cost} for goal {goal}")
    report = verify_path(res.cells, cost_map.blocked, terrain.slope_deg, cost_map.p_haz)  # TRUE full mask
    corridor_mask = None
    if coarse.corridor_mask is not None:
        corridor_mask = upsample(coarse.corridor_mask, grid.f, cost_map.blocked.shape)
    return PathResult(
        cells=res.cells, total_cost=res.cost, risk_score=report.risk_score,
        max_slope_on_path=report.max_slope, safe=report.safe, planner="astar", mode=mode, alpha=alpha,
        corridor_mask=corridor_mask, min_feasible_risk=None, baseline=None, candidate_id=cid,
        segments=_segments(res.cells, price, cost_map, terrain, p.base_cost, alpha),
        nodes_expanded=coarse.nodes_expanded + res.expanded,
        dijkstra_cost=dij_cost, dijkstra_nodes_expanded=dij_exp,
    )


def plan_paths(terrain: TerrainGrid, hazards: HazardMap, cost_map: CostMap,
               candidates: list[Candidate], config: PipelineConfig) -> dict[str, dict[str, PathResult]]:
    """Pipeline stage 6. One path per candidate in bold and cautious mode.

    If the grid is larger than `planning_grid_size`, A* runs on a block-reduced copy and each route
    is refined back to full resolution. Returned cells are always full resolution and are checked
    against the true full resolution blocked mask.
    """
    start = tuple(config.start)
    p = config.planning
    inflated = inflate_blocked(cost_map.blocked, start, p.inflate_r0, p.inflate_growth)
    f = coarse_factor(cost_map.blocked.shape, config)
    if f > 1:
        grid = make_coarse(terrain, hazards, cost_map, config, f)
        sc = grid.to_coarse(start)
        c_blocked = grid.cost_map.blocked.copy()
        c_blocked[sc] = False
        c_infl = inflate_blocked(c_blocked, sc, grid.config.planning.inflate_r0, p.inflate_growth)
        return {
            c.id: {m: _plan_one_coarse(terrain, cost_map, grid, start, tuple(c.location), m, config, c.id,
                                       c_infl, inflated) for m in MODES}
            for c in candidates
        }
    return {
        c.id: {m: plan_one(terrain, cost_map, start, c.location, m, config, c.id, inflated) for m in MODES}
        for c in candidates
    }


def _b1_friction(hazards: HazardMap, p) -> Optional[np.ndarray]:
    """Friction per cell from the terrain class label. Unknown labels use the fallback."""
    table = np.asarray(p.b1_friction_by_class, dtype=float)
    cls = getattr(hazards, "terrain_class", None)
    if cls is None or table.size == 0:
        return None
    known = (cls >= 0) & (cls < table.size)
    return np.where(known, table[np.clip(cls, 0, table.size - 1)], p.b1_friction_fallback)


def _baseline_inputs(name: str, terrain: TerrainGrid, hazards: HazardMap, p) -> tuple[np.ndarray, np.ndarray, float]:
    """(passable, price, heuristic base) of a baseline on the given grid."""
    slope = np.nan_to_num(terrain.slope_deg)
    if name == "b0":
        passable = (slope <= p.b0_slope_limit_deg) & terrain.valid_mask
        price = np.full(slope.shape, p.base_cost)  # shortest path under a slope threshold
        h_base = p.base_cost
    else:
        # B1 is a REFERENCE REPRODUCTION of Brad and Balog, Electronics 2025, 14(5), 921:
        # cost = z / (friction + eps), friction from the terrain class, plain A*. It has no slope
        # limit, no hazard_prob and no uncertainty on purpose. It is the baseline to beat, not a
        # competitive planner. Cost can drop below base_cost, so the heuristic is 0 (admissible).
        passable = terrain.valid_mask.copy()
        dem = np.nan_to_num(terrain.dem)
        z = dem - float(dem[terrain.valid_mask].min()) + p.b1_z_offset_m
        friction = _b1_friction(hazards, p)
        if friction is None:
            friction = np.full(slope.shape, p.b1_friction_fallback)
        price = z / (friction + p.b1_eps)
        h_base = 0.0
    return passable, price, h_base


def _baseline(name: str, terrain: TerrainGrid, hazards: HazardMap, cost_map: CostMap, start: Cell,
              goal: Cell, config: PipelineConfig, grid: Optional[CoarseGrid] = None) -> PathResult:
    p = config.planning
    slope = np.nan_to_num(terrain.slope_deg)
    passable, price, h_base = _baseline_inputs(name, terrain, hazards, p)
    if grid is None:
        res = astar(price, passable, start, goal, h_base)
    else:  # search coarse, refine at full resolution on the full resolution baseline rules
        c_pass, c_price, _ = _baseline_inputs(name, grid.terrain, grid.hazards, p)
        sc, gc = grid.to_coarse(start), grid.to_coarse(goal)
        c_pass[sc] = c_pass[gc] = True
        coarse = astar(c_price, c_pass, sc, gc, h_base)
        res, _ = _refine(coarse.cells, grid, price, passable, start, goal, h_base)
        res.expanded += coarse.expanded
    if not res.cells:
        return _no_path("bold", 0.0, None, f"baseline {name} found no route", None, baseline=name)
    # Baselines may cross true blocks. That is the comparison, so report instead of raising.
    rep = verify_path(res.cells, cost_map.blocked, terrain.slope_deg, cost_map.p_haz, raise_on_violation=False)
    return PathResult(
        cells=res.cells, total_cost=res.cost, risk_score=float(sum(cost_map.p_haz[c] for c in res.cells)),
        max_slope_on_path=float(max(slope[c] for c in res.cells)), safe=rep.safe, planner="astar",
        mode="bold", alpha=0.0, corridor_mask=None, min_feasible_risk=None, baseline=name,
        nodes_expanded=res.expanded,
        no_safe_path_reason=None if rep.safe else "baseline crosses blocked cells: " + "; ".join(rep.violations[:2]),
    )


def plan_extras(terrain: TerrainGrid, hazards: HazardMap, cost_map: CostMap, goal: Cell,
                config: PipelineConfig) -> PlanExtras:
    """Baselines B0 and B1 and the risk-versus-length curve, for the default goal."""
    start = tuple(config.start)
    p = config.planning
    inflated = inflate_blocked(cost_map.blocked, start, p.inflate_r0, p.inflate_growth)
    f = coarse_factor(cost_map.blocked.shape, config)
    grid = c_infl = None
    if f > 1:
        grid = make_coarse(terrain, hazards, cost_map, config, f)
        sc, gc = grid.to_coarse(start), grid.to_coarse(goal)
        c_blocked = grid.cost_map.blocked.copy()
        c_blocked[sc] = False
        c_infl = inflate_blocked(c_blocked, sc, grid.config.planning.inflate_r0, p.inflate_growth)
        c_infl[gc] = False
    curve = []
    for a in p.risk_curve_alphas:
        price = price_grid(cost_map.cost_mean, cost_map.cost_std, p.base_cost, a)
        if grid is None:
            res = astar(price, ~inflated, start, goal, p.base_cost)
        elif cost_map.blocked[goal] or cost_map.blocked[start]:
            res = SearchResult([], math.inf, 0)
        else:
            c_price = price_grid(grid.cost_map.cost_mean, grid.cost_map.cost_std, p.base_cost, a)
            coarse = astar(c_price, ~c_infl, sc, gc, p.base_cost)
            res, _ = _refine(coarse.cells, grid, price, ~inflated, start, goal, p.base_cost)
        if not res.cells:
            curve.append(RiskCurvePoint(a, math.inf, math.nan))
            continue
        verify_path(res.cells, cost_map.blocked, terrain.slope_deg, cost_map.p_haz)
        viol = float(np.mean([cost_map.p_haz[c] > p.violation_p_haz for c in res.cells]))
        curve.append(RiskCurvePoint(a, path_length_cells(res.cells), viol))
    return PlanExtras(
        risk_curve=curve,
        baseline_paths={n: _baseline(n, terrain, hazards, cost_map, start, goal, config, grid)
                        for n in ("b0", "b1")},
    )
