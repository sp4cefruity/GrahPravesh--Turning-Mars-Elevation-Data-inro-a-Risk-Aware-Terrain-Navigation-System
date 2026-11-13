"""System acceptance checks from specs/00-system.md."""

import dataclasses
import tempfile
from pathlib import Path

import numpy as np

from odyssey import pipeline
from odyssey.config import PipelineConfig, Seeds
from odyssey.contracts import MODES, PathResult


def test_runs_end_to_end_with_all_stubs():
    res = pipeline.run_pipeline(PipelineConfig())
    assert res.complete, res.error
    assert set(res.stub_stages) == {"data", "perception", "uncertainty", "science_candidates", "science_ranking"}
    assert res.default_target_id is not None
    assert res.targets and res.risk_curve and set(res.baseline_paths) == {"b0", "b1"}
    for by_mode in res.paths.values():
        assert set(by_mode) == set(MODES)


def _fingerprint(res):
    return ([(t.id, t.score, t.rank_interval) for t in res.targets],
            {cid: {m: (p.cells, p.total_cost) for m, p in bm.items()} for cid, bm in res.paths.items()},
            res.hazards.slope_std_deg.tobytes())


def test_same_seed_gives_identical_output():
    a = pipeline.run_pipeline(PipelineConfig())
    b = pipeline.run_pipeline(PipelineConfig())
    assert _fingerprint(a) == _fingerprint(b)


def test_different_seed_changes_output():
    a = pipeline.run_pipeline(PipelineConfig())
    b = pipeline.run_pipeline(PipelineConfig(seeds=Seeds(data=99)))
    assert _fingerprint(a) != _fingerprint(b)


def test_forced_bad_path_fails_loudly_at_safety_check():
    def bad_planning(terrain, hazards, cost_map, candidates, config):
        r, c = np.argwhere(cost_map.blocked)[0]
        bad = PathResult(cells=[(int(r), int(c))], total_cost=1.0, risk_score=0.0, max_slope_on_path=0.0,
                         safe=True, planner="astar", mode="bold", alpha=0.0, corridor_mask=None,
                         min_feasible_risk=None, baseline=None)
        return {cand.id: {"bold": bad, "cautious": bad} for cand in candidates}

    res = pipeline.run_pipeline(PipelineConfig(), overrides={"planning": bad_planning})
    assert not res.complete
    assert res.error.stage == "safety_check"
    assert "blocked" in res.error.reason


def test_stage_exception_is_recorded_and_stops_the_run():
    def boom(terrain, hazards, config):
        raise RuntimeError("model file missing")

    res = pipeline.run_pipeline(PipelineConfig(), overrides={"uncertainty": boom})
    assert not res.complete
    assert res.error.stage == "uncertainty" and "model file missing" in res.error.reason
    assert res.cost_map is None and not res.targets


def test_contract_violation_names_the_stage():
    def wrong_shape(config):
        t = pipeline.stubs.stub_load_terrain(config)
        t.valid_mask = t.valid_mask[:10]
        return t

    res = pipeline.run_pipeline(PipelineConfig(), overrides={"data": wrong_shape})
    assert not res.complete and res.error.stage == "data" and "valid_mask" in res.error.reason


def test_missing_slope_std_is_caught():
    res = pipeline.run_pipeline(PipelineConfig(), overrides={"uncertainty": lambda t, h, c: h})
    assert not res.complete and res.error.stage == "uncertainty"


def test_start_inside_a_block_stops_the_run():
    res = pipeline.run_pipeline(PipelineConfig(start=(32, 30)))  # on the stub ridge
    assert not res.complete and res.error.stage == "cost_map"


def test_real_stage_is_picked_up_without_editing_the_pipeline(monkeypatch=None):
    import odyssey.data as data_pkg
    called = []

    def fake(config):
        called.append(1)
        return pipeline.stubs.stub_load_terrain(config)

    data_pkg.load_terrain = fake
    try:
        res = pipeline.run_pipeline(PipelineConfig())
    finally:
        del data_pkg.load_terrain
    assert called and "data" not in res.stub_stages


def test_save_and_load_round_trip():
    with tempfile.TemporaryDirectory() as d:
        cfg = dataclasses.replace(PipelineConfig(), output_dir=d)
        a = pipeline.load_or_run(cfg)
        assert pipeline.result_path(cfg).exists()
        b = pipeline.load_or_run(cfg)  # loads, does not recompute
        assert _fingerprint(a) == _fingerprint(b)
        assert Path(d).exists()


def test_config_json_round_trip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.json"
        cfg = PipelineConfig(noise_level=2.5, seeds=Seeds(data=7))
        cfg.to_json(p)
        assert PipelineConfig.from_json(p) == cfg
