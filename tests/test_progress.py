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
