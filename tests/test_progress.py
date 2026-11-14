import numpy as np
import pytest

from odyssey.planning.progress import NoProgress, ProgressGuard, snap_to_safe


def test_snap_returns_same_cell_when_passable():
    ok = np.ones((5, 5), bool)
    assert snap_to_safe(ok, (2, 2), 3) == (2, 2)


def test_snap_is_deterministic_and_breaks_ties_by_row_col():
    ok = np.zeros((5, 5), bool)
    ok[1, 2] = ok[3, 2] = ok[2, 1] = ok[2, 3] = True  # all at distance 1 from (2, 2)
    for _ in range(3):
        assert snap_to_safe(ok, (2, 2), 3) == (1, 2)


def test_snap_returns_none_past_max_radius():
    ok = np.zeros((9, 9), bool)
    ok[0, 0] = True
    assert snap_to_safe(ok, (8, 8), 3) is None
    assert snap_to_safe(np.zeros((4, 4), bool), (1, 1), 10) is None


def test_two_cell_oscillation_raises():
    g = ProgressGuard(max_revisits=2)
    with pytest.raises(NoProgress):
        for i in range(20):
            g.visit((0, 0) if i % 2 == 0 else (0, 1))


def test_replan_cap():
    g = ProgressGuard(max_replans=3)
    for _ in range(3):
        g.replan()
    with pytest.raises(NoProgress):
        g.replan()


def test_near_equal_route_is_rejected_but_clear_gain_is_accepted():
    g = ProgressGuard(switch_margin=0.05)
    assert not g.allow_switch(100.0, 99.0)
    assert not g.allow_switch(100.0, 100.0)
    assert g.allow_switch(100.0, 90.0)
    assert g.allow_switch(float("inf"), 50.0)
    assert not g.allow_switch(float("inf"), float("inf"))


def _margin_scene():
    from test_planning import _scene
    terrain, haz = _scene(wall=False)
    haz.hard_block[10, 20] = True  # single block, margin r0 = 1 cell around it
    return terrain, haz


def test_goal_in_drift_margin_is_a_clear_failure_by_default():
    from odyssey.config import PipelineConfig
    from odyssey.planning import build_cost_map, plan_one
    terrain, haz = _margin_scene()
    cm = build_cost_map(terrain, haz, PipelineConfig())
    pr = plan_one(terrain, cm, (10, 2), (10, 21), "bold", PipelineConfig())
    assert not pr.cells and "drift margin" in pr.no_safe_path_reason


def test_goal_in_drift_margin_snaps_once_when_enabled():
    import dataclasses
    from odyssey.config import PipelineConfig
    from odyssey.planning import build_cost_map, plan_one
    terrain, haz = _margin_scene()
    base = PipelineConfig()
    cfg = dataclasses.replace(base, planning=dataclasses.replace(base.planning, snap_goal_radius_cells=3.0))
    cm = build_cost_map(terrain, haz, cfg)
    pr = plan_one(terrain, cm, (10, 2), (10, 21), "bold", cfg)
    assert pr.safe and pr.snapped_from == (10, 21)
    assert pr.cells[-1] != (10, 21) and not cm.blocked[pr.cells[-1]]
