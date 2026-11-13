"""Planning grid reduction (spec 02, requirement 11)."""

import dataclasses

import numpy as np

from odyssey import pipeline, planning
from odyssey.config import PipelineConfig
from odyssey.planning import coarse
from odyssey.planning.costmap import build_cost_map


def _big(n=512, **kw):
    return dataclasses.replace(PipelineConfig(), stub_grid_size=n, **kw)


def test_factor_is_noop_at_or_below_the_limit():
    cfg = PipelineConfig()
    assert coarse.factor((256, 256), cfg) == 1
    assert coarse.factor((64, 200), cfg) == 1
    assert coarse.factor((512, 512), cfg) == 2
    assert coarse.factor((513, 100), cfg) == 3


def test_reduction_rules():
    f = 2
    a = np.arange(16, dtype=float).reshape(4, 4)
    assert coarse.reduce_mean(a, f)[0, 0] == np.mean([0, 1, 4, 5])
    m = np.zeros((4, 4), dtype=bool)
    m[1, 1] = True
    assert coarse.reduce_any(m, f).tolist() == [[True, False], [False, False]]
    assert coarse.reduce_all(~m, f).tolist() == [[False, True], [True, True]]
    lab = np.array([[1, 1, 2, 2], [1, 3, 2, 3], [0, 0, 5, 6], [7, 0, 5, 6]])
    assert coarse.reduce_mode(lab, f).tolist() == [[1, 2], [0, 5]]
    assert coarse.reduce_mode(lab, f).dtype == lab.dtype
    # odd shape is padded, not dropped
    assert coarse.reduce_mean(np.ones((5, 3)), 2).shape == (3, 2)


def test_noop_case_plans_at_full_resolution_and_leaves_no_note():
    res = pipeline.run_pipeline(PipelineConfig())  # 64 by 64
    assert res.complete, res.error
    assert not any("Planning searched" in n for n in res.notes)
    assert all(pr.dijkstra_cost == pr.total_cost for bm in res.paths.values() for pr in bm.values() if pr.cells)


def test_512_input_is_safe_and_full_resolution():
    res = pipeline.run_pipeline(_big(512))
    assert res.complete, res.error
    assert res.terrain.shape == (512, 512) and res.cost_map.blocked.shape == (512, 512)
    assert any("Planning searched a 256 by 256" in n for n in res.notes)
    found = 0
    for bm in res.paths.values():
        for pr in bm.values():
            if not pr.cells:
                assert not pr.safe and pr.no_safe_path_reason
                continue
            found += 1
            assert pr.safe and pr.cells[0] == res.start
            assert max(abs(a[0] - b[0]) for a, b in zip(pr.cells, pr.cells[1:])) <= 1
            rr, cc = zip(*pr.cells)
            assert not res.cost_map.blocked[rr, cc].any()  # true full resolution mask
            assert pr.corridor_mask.shape == (512, 512)
            assert np.isclose(pr.dijkstra_cost, pr.total_cost)
    assert found > 0
    for cand in res.candidates:
        for pr in res.paths[cand.id].values():
            if pr.cells:
                assert pr.cells[-1] == tuple(cand.location)
    assert res.risk_curve and set(res.baseline_paths) == {"b0", "b1"}
    assert any(pt.path_length < float("inf") for pt in res.risk_curve)


def test_512_is_deterministic():
    a = pipeline.run_pipeline(_big(512))
    b = pipeline.run_pipeline(_big(512))
    assert {c: {m: p.cells for m, p in bm.items()} for c, bm in a.paths.items()} == \
           {c: {m: p.cells for m, p in bm.items()} for c, bm in b.paths.items()}


def test_planner_never_returns_a_path_through_a_block_a_coarse_cell_hides():
    """A one cell wall gap that the block max would close, and a lone blocked cell inside a block."""
    cfg = _big(512)
    res = pipeline.run_pipeline(cfg)
    assert res.complete
    terrain, hazards = res.terrain, res.hazards
    hb = hazards.hard_block.copy()
    hb[::2, 256] = True  # leaky dotted wall down the middle, lone blocked cells in many blocks
    hazards = dataclasses.replace(hazards, hard_block=hb)
    cm = build_cost_map(terrain, hazards, cfg)
    paths = planning.plan_paths(terrain, hazards, cm, res.candidates, cfg)
    for bm in paths.values():
        for pr in bm.values():
            if pr.cells:
                rr, cc = zip(*pr.cells)
                assert not cm.blocked[rr, cc].any() and pr.safe
            else:
                assert not pr.safe and pr.no_safe_path_reason


def test_blocked_goal_gives_reason_not_path_at_512():
    res = pipeline.run_pipeline(_big(512))
    cfg = _big(512)
    cm = res.cost_map
    cand = dataclasses.replace(res.candidates[0])
    blocked = np.argwhere(cm.blocked)[0]
    cand.location = (int(blocked[0]), int(blocked[1]))
    out = planning.plan_paths(res.terrain, res.hazards, cm, [cand], cfg)
    for pr in out[cand.id].values():
        assert not pr.cells and not pr.safe and "hard block" in pr.no_safe_path_reason
