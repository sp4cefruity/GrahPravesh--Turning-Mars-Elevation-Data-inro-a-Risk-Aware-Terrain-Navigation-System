"""Checks for science/evaluate.py: known answers first, then the whole thing on a synthetic scene."""

import dataclasses
from types import SimpleNamespace

import numpy as np

from odyssey.config import PipelineConfig
from odyssey.contracts import Candidate, PathResult, ScienceTarget
from odyssey.data.scene import build_scene
from odyssey.perception import compute_hazards
from odyssey.science import find_candidates, rank_targets
from odyssey.science.evaluate import (METRICS, evaluate, rank_metrics, recall_metrics, run_one, summarize, to_markdown,
                                      truth_values, value_metrics, write_csv)
from odyssey.uncertainty import fill_slope_uncertainty
from synthetic import fake_tile


def _t(i, value=0.5, ci=(0.4, 0.6), cost=10.0, score=0.05, ranks=(1, 1), kind="ice", ev="x", loc=(0, 0)):
    return ScienceTarget(id=f"T{i}", location=loc, value_mean=value, value_ci=ci, path_cost=cost, score=score,
                         score_ci=(0.0, 1.0), rank_interval=ranks, p_top3=0.5, evidence=ev, kind=kind)


def _c(loc, kind="ice", ev="x"):
    return Candidate(id="C", location=loc, kind=kind, value_mean=0.5, value_ci=(0.4, 0.6), evidence=ev)


# ---------------------------------------------------------------- value


def test_value_metrics_known_answer():
    ts = [_t(0), _t(1), _t(2, ev="NO DATA here"), _t(3)]
    m = value_metrics(ts, [0.55, 0.9, 0.5, float("nan")])
    assert m["n_measured"] == 2                      # the no-data target and the NaN truth are left out
    assert np.isclose(m["value_mae"], (0.05 + 0.4) / 2)
    assert m["value_coverage"] == 0.5                # 0.55 is inside (0.4, 0.6), 0.9 is not


def test_value_metrics_with_nothing_to_measure_is_nan_not_an_error():
    m = value_metrics([], [])
    assert m["n_measured"] == 0 and np.isnan(m["value_mae"]) and np.isnan(m["value_coverage"])


# ---------------------------------------------------------------- rank


def _four(est, ranks):
    return [_t(i, score=e, ranks=r) for i, (e, r) in enumerate(zip(est, ranks))]


def test_rank_metrics_perfect_agreement():
    ts = _four([0.09, 0.07, 0.05, 0.03], [(1, 1), (2, 2), (3, 3), (4, 4)])
    m = rank_metrics(ts, [0.9, 0.7, 0.5, 0.3])
    assert m["n_reachable"] == 4 and np.isclose(m["rank_spearman"], 1.0)
    assert m["rank_interval_coverage"] == 1.0 and m["truth_best_in_top3"] == 1.0


def test_rank_metrics_reversed_order():
    ts = _four([0.09, 0.07, 0.05, 0.03], [(1, 1), (2, 2), (3, 3), (4, 4)])
    m = rank_metrics(ts, [0.3, 0.5, 0.7, 0.9])       # the truth is the opposite order
    assert np.isclose(m["rank_spearman"], -1.0)
    assert m["rank_interval_coverage"] == 0.0
    assert m["truth_best_in_top3"] == 0.0            # the truly best target was ranked 4th


def test_rank_metrics_leave_out_unreachable_targets():
    ts = _four([0.09, 0.07, 0.05, 0.0], [(1, 1), (2, 2), (3, 3), (4, 4)])
    ts[3].path_cost = float("inf")
    m = rank_metrics(ts, [0.9, 0.7, 0.5, 0.99])      # a great but unreachable target must not count
    assert m["n_reachable"] == 3 and np.isclose(m["rank_spearman"], 1.0)


def test_rank_metrics_small_and_degenerate_inputs():
    two = rank_metrics(_four([0.09, 0.07], [(1, 1), (2, 2)]), [0.9, 0.7])
    assert np.isnan(two["rank_spearman"]) and two["rank_interval_coverage"] == 1.0   # too few for a correlation
    tie = rank_metrics(_four([0.09, 0.07, 0.05], [(1, 1), (2, 2), (3, 3)]), [0.5, 0.5, 0.5])
    assert np.isnan(tie["rank_spearman"])                                            # all tie, no correlation
    assert np.isclose(tie["rank_interval_coverage"], 1.0 / 3.0)                      # all tie for rank 1
    none = rank_metrics([], [])
    assert none["n_reachable"] == 0 and np.isnan(none["rank_spearman"])


# ---------------------------------------------------------------- recall


def test_recall_metrics_known_answer():
    planted = [{"row": 10, "col": 10, "kind": "ice", "value": 0.8}, {"row": 50, "col": 50, "kind": "geology", "value": 0.6}]
    cands = [_c((12, 12)),                                   # ice, 2.8 cells from the ice target: a hit
             _c((50, 50), kind="ice"),                       # right place, wrong kind: not a hit
             _c((50, 50), kind="geology", ev="NO DATA")]     # a placeholder, not a detection
    m = recall_metrics(cands, planted, radius=8.0)
    assert m["planted_recall"] == 0.5 and m["candidate_precision"] == 0.5


def test_recall_metrics_empty_cases():
    p = [{"row": 1, "col": 1, "kind": "ice", "value": 0.5}]
    assert recall_metrics([], p)["planted_recall"] == 0.0 and np.isnan(recall_metrics([], p)["candidate_precision"])
    assert np.isnan(recall_metrics([_c((1, 1))], [])["planted_recall"])


# ---------------------------------------------------------------- whole thing on a synthetic scene


def _run(noise, n_candidates=5):
    cfg = dataclasses.replace(PipelineConfig(), noise_level=noise, n_candidates=n_candidates)
    grid, truth = build_scene(fake_tile(), seed=cfg.seeds.data, noise_level=noise)
    terrain, hazards = compute_hazards(grid, cfg)
    hazards = fill_slope_uncertainty(terrain, hazards, cfg)
    cands = find_candidates(terrain, hazards, cfg)
    paths = {c.id: {m: PathResult(cells=[(0, 0)], total_cost=40.0 + 15.0 * i, risk_score=0.0, max_slope_on_path=0.0,
                                  safe=True, planner="astar", mode=m, alpha=0.95, corridor_mask=None,
                                  min_feasible_risk=None, baseline=None) for m in ("bold", "cautious")}
             for i, c in enumerate(cands)}
    targets = rank_targets(cands, paths, terrain, hazards, cfg)
    res = SimpleNamespace(config=cfg, terrain=terrain, hazards=hazards, candidates=cands, targets=targets)
    return res, truth


def test_evaluate_runs_end_to_end_and_every_metric_is_in_range():
    m = evaluate(*_run(1.0))
    assert m["n_targets"] >= 3 and m["n_measured"] >= 1
    for k in ("value_coverage", "rank_interval_coverage", "truth_best_in_top3", "planted_recall", "candidate_precision"):
        assert 0.0 <= m[k] <= 1.0, (k, m[k])
    assert -1.0 <= m["rank_spearman"] <= 1.0 and m["value_mae"] >= 0.0


def test_truth_matches_the_scene_wherever_no_fault_was_injected():
    res, truth = _run(0.0)                                   # no sensor noise, so only gaps and the conflict can differ
    tv = truth_values(res, truth)
    clean = [(t, v) for t, v in zip(res.targets, tv)
             if "NO DATA" not in t.evidence and not truth.conflict_zone[t.location]]
    assert clean and all(abs(t.value_mean - v) < 0.1 for t, v in clean)


def test_truth_values_leave_missing_patches_undefined_not_zero():
    res, truth = _run(0.0)
    tv = truth_values(res, truth)
    assert all(np.isfinite(v) or "NO DATA" in t.evidence for t, v in zip(res.targets, tv))


def test_evaluate_is_repeatable():
    a, b = evaluate(*_run(1.0)), evaluate(*_run(1.0))
    assert all((np.isnan(a[k]) and np.isnan(b[k])) or a[k] == b[k] for k in a)


# ---------------------------------------------------------------- aggregation and the real pipeline


def test_summarize_ignores_nan_counts_failures_and_groups():
    nan = float("nan")
    base = {m: 0.0 for m in METRICS}
    rows = [{**base, "tile": "T1", "error": "", "value_mae": 0.2, "rank_spearman": nan},
            {**base, "tile": "T1", "error": "", "value_mae": 0.4, "rank_spearman": 0.5},
            {**base, "tile": "T1", "error": "planning: boom", "value_mae": 99.0, "rank_spearman": 99.0},
            {**base, "tile": "T2", "error": "", "value_mae": 0.1, "rank_spearman": nan}]
    t = {r["tile"]: r for r in summarize(rows)}
    assert t["T1"]["runs"] == 3 and t["T1"]["failed"] == 1
    assert np.isclose(t["T1"]["value_mae"], 0.3)         # the failed run's 99 is not averaged in
    assert np.isclose(t["T1"]["rank_spearman"], 0.5)     # the NaN is skipped, not turned into 0
    assert np.isnan(t["T2"]["rank_spearman"])            # nothing to average gives NaN, not an error


def test_to_markdown_shows_nan_as_na_and_handles_empty():
    text = to_markdown([{"tile": "T1", "value_mae": float("nan"), "runs": 2}])
    assert "n/a" in text and "| tile | value_mae | runs |" in text
    assert to_markdown([]) == "(no rows)"


def _in_range(row):
    for k in ("value_coverage", "rank_interval_coverage", "truth_best_in_top3", "planted_recall", "candidate_precision"):
        assert np.isnan(row[k]) or 0.0 <= row[k] <= 1.0, (k, row[k])
    assert np.isnan(row["rank_spearman"]) or -1.0 <= row["rank_spearman"] <= 1.0


def test_run_one_on_a_real_tile_is_complete_in_range_and_repeatable():
    a, b = run_one("T1", seed=0), run_one("T1", seed=0)
    assert a["error"] == "" and a["n_targets"] >= 3
    _in_range(a)
    assert all((np.isnan(a[k]) and np.isnan(b[k])) or a[k] == b[k] for k in METRICS)


def test_run_one_survives_the_cliff_tile_where_most_targets_are_unreachable():
    row = run_one("T4", seed=0)
    assert row["error"] == ""                  # no crash even when few or no targets have a safe path
    _in_range(row)
    assert row["n_reachable"] <= row["n_targets"]


def test_run_one_turns_a_loading_failure_into_an_error_row(monkeypatch):
    import odyssey.data.dem as dem
    def boom(tile_id):
        raise RuntimeError("tile file is broken")
    monkeypatch.setattr(dem, "load_tile", boom)
    row = run_one("T1")
    assert row["error"] == "RuntimeError: tile file is broken" and row["tile"] == "T1"


def test_csv_holds_failed_and_successful_runs_together(tmp_path):
    ok = {"tile": "T1", "seed": 0, "noise": 1.0, "n_candidates": 5, "error": "", **{m: 0.5 for m in METRICS}}
    bad = {"tile": "T2", "seed": 0, "noise": 1.0, "n_candidates": 5, "error": "KeyError: nope"}   # no metrics at all
    write_csv([bad, ok], tmp_path / "out.csv")                                                      # a failure comes first
    lines = (tmp_path / "out.csv").read_text().splitlines()
    assert len(lines) == 3 and lines[0].startswith("tile,seed,noise,n_candidates,error")
    assert "KeyError: nope" in lines[1] and lines[2].startswith("T1,0,1.0,5,,")


def test_a_seed_that_used_to_block_the_start_now_runs_through_the_whole_pipeline():
    assert run_one("T1", seed=196)["error"] == ""


def test_csv_takes_a_real_result_row_with_every_column_it_carries(tmp_path):
    real = run_one("T1", seed=0)
    bad = {"tile": "T2", "seed": 0, "noise": 1.0, "n_candidates": 5, "error": "KeyError: nope"}
    write_csv([bad, real], tmp_path / "out.csv")                        # the failure comes first, the real row has more columns
    header = (tmp_path / "out.csv").read_text().splitlines()[0].split(",")
    assert set(real) <= set(header) and "n_measured" in header          # nothing the harness reports is left out
