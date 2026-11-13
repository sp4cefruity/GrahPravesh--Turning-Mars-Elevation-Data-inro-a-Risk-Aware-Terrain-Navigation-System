"""Acceptance checks from specs/03-uncertainty-science.md.

Only contracts and a synthetic test scene are used as inputs. Path costs are fabricated here, so the checks run
before the real planner is wired in.
"""

import dataclasses

import numpy as np
import pytest
from scipy.ndimage import distance_transform_edt

from odyssey import pipeline
from odyssey.config import PipelineConfig, Seeds
from odyssey.contracts import (
    Candidate, PathResult, validate_candidates, validate_targets,
)
from odyssey.perception import compute_hazards
from odyssey.science import find_candidates, rank_targets
from odyssey.uncertainty import fill_slope_uncertainty
from synthetic import synthetic_terrain


def _scene(**cfg_kw):
    cfg = dataclasses.replace(PipelineConfig(), **cfg_kw)
    terrain = synthetic_terrain(cfg)
    terrain, hazards = compute_hazards(terrain, cfg)
    hazards = fill_slope_uncertainty(terrain, hazards, cfg)
    return cfg, terrain, hazards


def _path(cost, safe=True, mode="cautious"):
    return PathResult(cells=[(0, 0)] if safe else [], total_cost=cost, risk_score=0.0, max_slope_on_path=0.0,
                      safe=safe, planner="astar", mode=mode, alpha=0.95, corridor_mask=None,
                      min_feasible_risk=None, baseline=None)


def _paths(cands, costs):
    return {c.id: {"cautious": _path(k, safe=np.isfinite(k)), "bold": _path(k, safe=np.isfinite(k), mode="bold")}
            for c, k in zip(cands, costs)}


def _cand(i, mean, sd, kind="ice", evidence="x"):
    z = 1.645
    return Candidate(id=f"T{i}", location=(10 + i, 10), kind=kind, value_mean=mean,
                     value_ci=(mean - z * sd, mean + z * sd), evidence=evidence)


# ---------------------------------------------------------------- step 1


def test_candidates_follow_the_contract_and_carry_evidence():
    cfg, terrain, hazards = _scene()
    cands = find_candidates(terrain, hazards, cfg)
    assert cands
    validate_candidates(cands, terrain.shape)
    for c in cands:
        assert c.evidence.strip()
        assert c.value_ci[0] <= c.value_mean <= c.value_ci[1]


def test_candidates_keep_clear_of_hard_blocks_by_the_drift_margin():
    cfg, terrain, hazards = _scene()
    margin = cfg.drift_margin_cells(terrain.shape)
    dist = distance_transform_edt(~(hazards.hard_block | ~terrain.valid_mask))
    for c in find_candidates(terrain, hazards, cfg):
        if "NO DATA" in c.evidence:
            continue
        assert dist[c.location] >= margin


def test_missing_region_is_listed_with_low_confidence_not_dropped():
    cfg, terrain, hazards = _scene()
    cands = find_candidates(terrain, hazards, cfg)
    missing = [c for c in cands if not terrain.valid_mask[c.location]]
    assert missing, "the synthetic scene has a missing patch, a target must be listed there"
    normal = [c for c in cands if terrain.valid_mask[c.location]]
    w_missing = min(c.value_ci[1] - c.value_ci[0] for c in missing)
    w_normal = max(c.value_ci[1] - c.value_ci[0] for c in normal)
    assert w_missing > w_normal
    assert all("NO DATA" in c.evidence for c in missing)


def test_more_noise_gives_wider_value_intervals():
    def widths(noise):
        cfg, terrain, hazards = _scene(noise_level=noise)
        return {c.location: c.value_ci[1] - c.value_ci[0] for c in find_candidates(terrain, hazards, cfg)
                if terrain.valid_mask[c.location]}
    lo, hi = widths(0.5), widths(3.0)
    common = lo.keys() & hi.keys()
    assert common
    assert all(hi[k] > lo[k] for k in common)


def test_conflicting_ice_and_thermal_bands_widen_the_interval_and_say_so():
    cfg, terrain, hazards = _scene()
    ice = terrain.bands["ice_simulated"]
    calm = dataclasses.replace(terrain, bands={**terrain.bands, "thermal_simulated": ice.copy()})  # agrees
    clash = dataclasses.replace(terrain, bands={**terrain.bands, "thermal_simulated": 1.0 - ice})  # disagrees
    a = {c.location: c for c in find_candidates(calm, hazards, cfg) if c.kind == "ice"}
    b = {c.location: c for c in find_candidates(clash, hazards, cfg) if c.kind == "ice"}
    assert b, "an ice candidate must exist in the conflicting scene"
    assert any("CONFLICT" in c.evidence for c in b.values())
    assert not any("CONFLICT" in c.evidence for c in a.values())
    wb = max(c.value_ci[1] - c.value_ci[0] for c in b.values())
    wa = max(c.value_ci[1] - c.value_ci[0] for c in a.values())
    assert wb > wa


def test_candidates_are_repeatable():
    cfg, terrain, hazards = _scene()
    a = find_candidates(terrain, hazards, cfg)
    b = find_candidates(terrain, hazards, cfg)
    assert a == b


# ---------------------------------------------------------------- step 2


def test_ranking_works_with_fabricated_path_costs_and_every_target_has_evidence():
    cands = [_cand(1, 0.9, 0.05), _cand(2, 0.6, 0.05, "geology"), _cand(3, 0.5, 0.05)]
    cfg, terrain, hazards = _scene()
    targets = rank_targets(cands, _paths(cands, [10.0, 12.0, np.inf]), terrain, hazards, cfg)
    validate_targets(targets, {c.id for c in cands})
    assert len(targets) == 3
    assert all(t.evidence.strip() for t in targets)
    assert targets[0].id == "T1"
    assert targets[-1].id == "T3"  # unreachable stays listed, last
    assert targets[-1].path_cost == np.inf and targets[-1].score == 0.0
    assert "no safe path" in targets[-1].evidence.lower()


def test_score_is_value_over_access_cost():
    cands = [_cand(1, 0.8, 0.0001)]
    cfg, terrain, hazards = _scene()
    t = rank_targets(cands, _paths(cands, [20.0]), terrain, hazards, cfg)[0]
    assert t.score == pytest.approx(0.8 / 20.0, rel=0.1)


def test_same_seed_gives_same_ranking_and_other_seed_differs():
    cands = [_cand(i, 0.5 + 0.01 * i, 0.2) for i in range(1, 6)]
    paths = _paths(cands, [10.0] * 5)
    cfg, terrain, hazards = _scene()
    run = lambda c: [(t.id, t.score, t.score_ci, t.rank_interval, t.p_top3)
                     for t in rank_targets(cands, paths, terrain, hazards, c)]
    assert run(cfg) == run(cfg)
    other = dataclasses.replace(cfg, seeds=Seeds(ranking=99))
    assert run(other) != run(cfg)


def test_high_uncertainty_makes_rank_order_uncertain_and_bands_overlap():
    cfg, terrain, hazards = _scene()
    close = [_cand(1, 0.60, 0.25), _cand(2, 0.55, 0.25), _cand(3, 0.50, 0.25)]
    sure = [_cand(1, 0.90, 0.001), _cand(2, 0.50, 0.001), _cand(3, 0.20, 0.001)]
    noisy = {t.id: t for t in rank_targets(close, _paths(close, [10.0] * 3), terrain, hazards, cfg)}
    firm = {t.id: t for t in rank_targets(sure, _paths(sure, [10.0] * 3), terrain, hazards, cfg)}
    assert all(t.rank_interval[1] > t.rank_interval[0] for t in noisy.values())
    assert all(t.rank_interval[0] == t.rank_interval[1] for t in firm.values())
    a, b = noisy["T1"], noisy["T2"]
    assert a.score_ci[0] < b.score_ci[1] and b.score_ci[0] < a.score_ci[1]  # overlapping bands


def test_more_noise_gives_wider_score_intervals():
    cfg, terrain, hazards = _scene()
    def width(sd):
        cands = [_cand(1, 0.7, sd), _cand(2, 0.6, sd)]
        t = rank_targets(cands, _paths(cands, [10.0, 10.0]), terrain, hazards, cfg)[0]
        return t.score_ci[1] - t.score_ci[0]
    assert width(0.20) > width(0.05)


def test_p_top3_and_intervals_are_well_formed():
    cfg, terrain, hazards = _scene()
    cands = [_cand(i, 0.5, 0.15) for i in range(1, 7)]
    for t in rank_targets(cands, _paths(cands, [8.0] * 6), terrain, hazards, cfg):
        assert 0.0 <= t.p_top3 <= 1.0
        assert 1 <= t.rank_interval[0] <= t.rank_interval[1] <= 6
        assert t.score_ci[0] <= t.score <= t.score_ci[1]
        assert t.value_ci[0] <= t.value_mean <= t.value_ci[1]


def test_conflict_and_missing_flags_reach_the_target_evidence():
    cands = [_cand(1, 0.5, 0.3, evidence="NO DATA at this cell, scene prior used."),
             _cand(2, 0.6, 0.05, evidence="CONFLICT: ice high, thermal low.")]
    cfg, terrain, hazards = _scene()
    by_id = {t.id: t for t in rank_targets(cands, _paths(cands, [5.0, 5.0]), terrain, hazards, cfg)}
    assert "NO DATA" in by_id["T1"].evidence and "low confidence" in by_id["T1"].evidence.lower()
    assert "CONFLICT" in by_id["T2"].evidence


# ---------------------------------------------------------------- pipeline


def test_real_science_stages_run_in_the_pipeline_and_repeat():
    res = pipeline.run_pipeline(PipelineConfig())
    assert res.complete, res.error
    assert res.targets and all(t.evidence.strip() for t in res.targets)
    res2 = pipeline.run_pipeline(PipelineConfig())
    assert [(t.id, t.score, t.rank_interval) for t in res.targets] == \
           [(t.id, t.score, t.rank_interval) for t in res2.targets]
