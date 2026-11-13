"""Planning acceptance checks from specs/02-planning.md, on small grids."""

import dataclasses
import math

import numpy as np

from odyssey.config import PipelineConfig, PlanningConfig
from odyssey.contracts import HazardMap, TerrainGrid
from odyssey.planning import SafetyViolation, build_cost_map, plan_extras, plan_one, verify_path
from odyssey.planning.search import astar, cvar_k, dijkstra


def _scene(n=30, wall=False, gap=True):
    dem = np.zeros((n, n))
    terrain = TerrainGrid(dem=dem, valid_mask=np.ones((n, n), bool), cell_size_m=1.0,
                          slope_deg=np.full((n, n), 3.0), roughness=np.full((n, n), 0.1),
                          aspect=np.zeros((n, n)))
    block = np.zeros((n, n), bool)
    if wall:
        block[:, n // 2] = True
        if gap:
            block[n // 2, n // 2] = False
    haz = HazardMap(hazard_prob=np.full((n, n), 0.1), terrain_class=np.zeros((n, n), int),
                    class_probs=np.ones((1, n, n)), epistemic_std=np.full((n, n), 0.05),
                    hard_block=block, slope_std_deg=np.full((n, n), 1.0))
    return terrain, haz


def test_astar_and_dijkstra_agree_on_random_grid():
    rng = np.random.default_rng(0)
    for _ in range(10):
        price = 1.0 + rng.random((25, 25)) * 3
        passable = rng.random((25, 25)) > 0.2
        passable[0, 0] = passable[24, 24] = True
        a = astar(price, passable, (0, 0), (24, 24), 1.0)
        d = dijkstra(price, passable, (0, 0), (24, 24))
        assert math.isclose(a.cost, d.cost, rel_tol=1e-9) or (math.isinf(a.cost) and math.isinf(d.cost))
        assert a.expanded <= d.expanded


def test_forced_bad_path_is_rejected():
    terrain, haz = _scene(wall=True, gap=False)
    cells = [(5, c) for c in range(0, 20)]  # walks straight through the wall at column 15
    try:
        verify_path(cells, haz.hard_block, terrain.slope_deg, haz.hazard_prob)
    except SafetyViolation:
        return
    raise AssertionError("bad path was accepted")


def test_weights_never_unblock():
    terrain, haz = _scene(wall=True)
    base = PipelineConfig()
    blocked_ref = build_cost_map(terrain, haz, base).blocked
    for w in [(0, 0, 0), (1, 1, 1), (100, 0, 0), (0, 0, 100)]:
        cfg = dataclasses.replace(base, planning=dataclasses.replace(
            base.planning, w_slope=w[0], w_roughness=w[1], w_hazard=w[2]))
        assert (build_cost_map(terrain, haz, cfg).blocked == blocked_ref).all()


def test_invalid_cells_are_blocked():
    terrain, haz = _scene()
    terrain.valid_mask[3:6, 3:6] = False
    assert build_cost_map(terrain, haz, PipelineConfig()).blocked[4, 4]


def test_no_safe_path_returns_reason_and_never_a_path():
    terrain, haz = _scene(wall=True, gap=False)
    cm = build_cost_map(terrain, haz, PipelineConfig())
    for mode in ("bold", "cautious"):
        pr = plan_one(terrain, cm, (5, 2), (5, 25), mode, PipelineConfig())
        assert pr.cells == [] and not pr.safe
        assert pr.no_safe_path_reason
        assert pr.min_feasible_risk is None  # even without margin the wall seals the map


def test_gap_in_wall_is_reachable_and_safe():
    terrain, haz = _scene(wall=True, gap=True)
    cm = build_cost_map(terrain, haz, PipelineConfig())
    cfg = PipelineConfig(planning=PlanningConfig(inflate_r0=0.0, inflate_growth=0.0))
    pr = plan_one(terrain, cm, (5, 2), (5, 25), "bold", cfg)
    assert pr.safe and pr.cells[0] == (5, 2) and pr.cells[-1] == (5, 25)
    assert not any(cm.blocked[c] for c in pr.cells)
    assert pr.corridor_mask is not None and pr.corridor_mask[pr.cells[len(pr.cells) // 2]]


def test_margin_closed_gap_reports_min_feasible_risk():
    terrain, haz = _scene(wall=True, gap=True)  # one cell gap, margin of 2 cells closes it
    cm = build_cost_map(terrain, haz, PipelineConfig())
    cfg = PipelineConfig(planning=PlanningConfig(inflate_r0=2.0))
    pr = plan_one(terrain, cm, (5, 2), (5, 25), "bold", cfg)
    assert pr.cells == [] and not pr.safe
    assert pr.min_feasible_risk is not None and pr.min_feasible_risk > 0


def test_cautious_avoids_uncertain_ground():
    n = 30
    terrain, haz = _scene(n)
    std = np.full((n, n), 0.1)
    std[:, 10:20] = 0.0
    std[10:20, 10:20] = 0.0  # the direct line is certain, the detour rows are noisy
    std[0:10, 10:20] = 0.0
    std[12:18, 10:20] = 40.0  # an uncertain band across the middle of the direct line
    haz.slope_std_deg = std * 0
    haz.epistemic_std = std / 10
    cm = build_cost_map(terrain, haz, PipelineConfig())
    cfg = PipelineConfig(planning=PlanningConfig(inflate_r0=0.0, inflate_growth=0.0))
    bold = plan_one(terrain, cm, (15, 2), (15, 27), "bold", cfg)
    caut = plan_one(terrain, cm, (15, 2), (15, 27), "cautious", cfg)
    assert bold.cells != caut.cells
    assert sum(cm.cost_std[c] for c in caut.cells) < sum(cm.cost_std[c] for c in bold.cells)


def test_cvar_k():
    assert cvar_k(0.0) == 0.0
    assert math.isclose(cvar_k(0.95), 2.0627, rel_tol=1e-3)


def test_b1_reference_cost_uses_friction_and_elevation():
    # Two routes from left to right. The top 3 rows are low friction (class 2), the rest
    # high friction (class 0). Equal elevation, so B1 must pick the high friction rows.
    n = 20
    terrain, haz = _scene(n)
    cls = np.zeros((n, n), int)
    cls[:3, :] = 2
    haz.terrain_class = cls
    cm = build_cost_map(terrain, haz, PipelineConfig())
    cfg = PipelineConfig(start=(0, 0))
    ex = plan_extras(terrain, haz, cm, (0, n - 1), cfg)
    b1 = ex.baseline_paths["b1"]
    assert b1.baseline == "b1" and b1.cells
    assert max(r for r, _ in b1.cells) >= 3  # leaves the low friction rows although start and goal are in them


def test_b1_fallback_when_classes_are_unknown():
    n = 12
    terrain, haz = _scene(n)
    haz.terrain_class = np.full((n, n), 7, int)  # label outside the 3 entry table
    cm = build_cost_map(terrain, haz, PipelineConfig())
    cfg = PipelineConfig(start=(0, 0))
    b1 = plan_extras(terrain, haz, cm, (n - 1, n - 1), cfg).baseline_paths["b1"]
    assert b1.cells and b1.cells[0] == (0, 0) and b1.cells[-1] == (n - 1, n - 1)
    # flat terrain, one friction value everywhere, so the path is a straight diagonal
    assert len(b1.cells) == n


def test_drift_margin_is_exposed_and_matches_inflation():
    cfg = PipelineConfig()
    m = cfg.drift_margin_cells((64, 64))
    p = cfg.planning
    assert m >= p.inflate_r0
    assert math.isclose(m, p.inflate_r0 + p.inflate_growth * math.hypot(63 - 8, 63 - 8))
