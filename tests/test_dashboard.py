"""Acceptance checks for specs/04-dashboard.md. Logic is tested without a browser, the page with AppTest."""

import copy
import dataclasses
import math
from pathlib import Path

import numpy as np
import pytest

from odyssey import pipeline
from odyssey.config import PipelineConfig
from odyssey.dashboard import view


@pytest.fixture(scope="module")
def res():
    r = pipeline.run_pipeline(PipelineConfig())
    assert r.complete, r.error
    return r


def _cfg(tmp_path, **kw):
    return dataclasses.replace(PipelineConfig(), output_dir=str(tmp_path), **kw)


# ---------------------------------------------------------------- ranked table


def test_ranked_rows_carry_confidence_bands_and_flag_unreachable(res):
    rows = view.ranked_rows(res.targets)
    assert [r["id"] for r in rows] == [t.id for t in res.targets]
    first = rows[0]
    for key in ("rank", "kind", "value", "value_low", "value_high", "score", "score_low", "score_high",
                "rank_low", "rank_high", "p_top3", "path_cost", "reachable", "evidence"):
        assert key in first
    assert first["rank"] == 1
    assert first["score_low"] <= first["score"] <= first["score_high"]
    unreachable = [r for r in rows if not r["reachable"]]
    assert unreachable and all(math.isinf(r["path_cost"]) for r in unreachable)


def test_default_target_is_top_ranked_with_a_safe_path_in_that_mode(res):
    assert view.default_target(res, res.targets, "cautious") == res.default_target_id
    # a target without a safe path is skipped
    blocked_first = copy.deepcopy(res)
    top = blocked_first.targets[0].id
    blocked_first.paths[top]["cautious"].safe = False
    assert view.default_target(blocked_first, blocked_first.targets, "cautious") != top


def test_default_target_is_none_when_nothing_is_reachable(res):
    r = copy.deepcopy(res)
    for by_mode in r.paths.values():
        for pr in by_mode.values():
            pr.safe = False
    assert view.default_target(r, r.targets, "cautious") is None


def test_bold_mode_reranks_with_bold_access_cost(res):
    targets, note = view.targets_for_mode(res, "bold")
    assert {t.id for t in targets} == {t.id for t in res.targets}
    for t in targets:
        assert t.path_cost == res.paths[t.id]["bold"].total_cost
    assert "bold" in note.lower()


def test_cautious_mode_returns_pipeline_ranking_untouched(res):
    targets, note = view.targets_for_mode(res, "cautious")
    assert targets is res.targets
    assert note == ""


# ---------------------------------------------------------------- paths and planner


def test_select_path_by_target_and_mode(res):
    cid = res.default_target_id
    assert view.select_path(res, cid, "cautious") is res.paths[cid]["cautious"]
    assert view.select_path(res, "nope", "cautious") is None


def test_planner_stats_astar_and_dijkstra_agree_on_cost(res):
    pr = res.paths[res.default_target_id]["cautious"]
    a = view.planner_stats(pr, "astar")
    d = view.planner_stats(pr, "dijkstra")
    assert a["cost"] == pytest.approx(d["cost"])
    assert a["nodes_expanded"] == pr.nodes_expanded
    assert d["nodes_expanded"] == pr.dijkstra_nodes_expanded
    assert "same route" in d["note"].lower()


# ---------------------------------------------------------------- safety badge


def test_safety_badge_passes_on_a_verified_path(res):
    pr = res.paths[res.default_target_id]["cautious"]
    b = view.safety_badge(res, pr)
    assert b.level == "pass"
    assert "PASS" in b.text
    assert str(len(pr.cells)) in b.detail


def test_safety_badge_fails_when_a_path_cell_is_blocked(res):
    r = copy.deepcopy(res)
    pr = r.paths[r.default_target_id]["cautious"]
    r.cost_map.blocked[pr.cells[len(pr.cells) // 2]] = True
    b = view.safety_badge(r, pr)
    assert b.level == "fail"
    assert "FAIL" in b.text


def test_safety_badge_reports_the_reason_when_there_is_no_path(res):
    unreachable = next(t.id for t in res.targets if not math.isfinite(t.path_cost))
    pr = res.paths[unreachable]["cautious"]
    b = view.safety_badge(res, pr)
    assert b.level == "none"
    assert pr.no_safe_path_reason in b.detail


# ---------------------------------------------------------------- traces


def test_target_trace_has_inputs_costs_and_evidence(res):
    t = next(t for t in res.targets if t.id == res.default_target_id)
    pr = res.paths[t.id]["cautious"]
    tr = view.target_trace(res, t, pr)
    assert tr["evidence"] == t.evidence
    assert tr["inputs"]["location"] == t.location
    assert tr["cost"]["total"] == pr.total_cost
    assert tr["cost"]["segments"] == len(pr.segments)
    assert tr["cost"]["sum_of_segment_costs"] == pytest.approx(pr.total_cost)


def test_segment_trace_breaks_down_the_cost(res):
    pr = res.paths[res.default_target_id]["cautious"]
    seg = pr.segments[3]
    tr = view.segment_trace(res, pr, 3)
    assert tr["edge_cost"] == seg.edge_cost
    assert tr["mean"] == seg.mean and tr["risk_term"] == seg.risk_term and tr["base"] == seg.base
    assert tr["to_cell"] == seg.to_cell
    assert tr["cell"]["slope_deg"] == pytest.approx(float(res.terrain.slope_deg[seg.to_cell]))


def test_segment_trace_rejects_a_bad_index(res):
    pr = res.paths[res.default_target_id]["cautious"]
    with pytest.raises(IndexError):
        view.segment_trace(res, pr, len(pr.segments))


def test_cell_trace_traces_every_layer_and_marks_simulated(res):
    cell = (10, 12)
    tr = view.cell_trace(res, cell)
    for key in ("cell", "dem_m", "slope_deg", "roughness", "hazard_prob", "epistemic_std", "slope_std_deg",
                "cost_mean", "cost_std", "blocked", "terrain_class", "evidence", "valid", "simulated_inputs"):
        assert key in tr
    assert tr["evidence"]
    assert "dem" in tr["simulated_inputs"]


def test_cell_trace_rejects_a_cell_outside_the_grid(res):
    with pytest.raises(IndexError):
        view.cell_trace(res, (10_000, 3))


# ---------------------------------------------------------------- simulated labels


def test_simulated_labels_list_layers_and_stub_stages(res):
    text = " ".join(view.simulated_labels(res))
    for layer in res.terrain.simulated_layers:
        assert layer in text
    for stage in res.stub_stages:
        assert stage in text


def test_layer_options_mark_simulated_layers(res):
    opts = view.layer_options(res)
    names = dict(opts)
    assert "cost_mean" in names
    sim = [label for key, label in opts if key.startswith("band:") and key.endswith("_simulated")]
    assert sim and all("SIMULATED" in label for label in sim)


def test_layer_grid_returns_a_grid_of_the_right_shape(res):
    for key, _ in view.layer_options(res):
        g = view.layer_grid(res, key)
        assert g.shape == res.terrain.shape


# ---------------------------------------------------------------- scenarios


def test_missing_patch_is_inside_the_grid_and_clear_of_the_start(res):
    patch = view.missing_patch(res)
    assert patch.shape == res.terrain.shape and patch.dtype == bool
    assert patch.any()
    assert not patch[tuple(res.start)]


def test_missing_patch_sits_on_the_default_route(res):
    patch = view.missing_patch(res)
    cells = res.paths[res.default_target_id]["cautious"].cells
    assert any(patch[c] for c in cells)


def test_scenario_with_missing_data_marks_cells_invalid_and_labels_them(tmp_path):
    base = view.run_scenario(_cfg(tmp_path), view.Scenario(noise=1.0, missing_data=False))
    hit = view.run_scenario(_cfg(tmp_path), view.Scenario(noise=1.0, missing_data=True))
    assert base.complete and hit.complete, hit.error
    assert (~hit.terrain.valid_mask).sum() > (~base.terrain.valid_mask).sum()
    assert hit.terrain.valid_mask[tuple(hit.start)]
    assert "missing_patch_simulated" in hit.terrain.simulated_layers
    assert "data" in hit.stub_stages  # still reported as a stub when it is one


def test_scenario_noise_changes_the_uncertainty(tmp_path):
    lo = view.run_scenario(_cfg(tmp_path), view.Scenario(noise=0.5, missing_data=False))
    hi = view.run_scenario(_cfg(tmp_path), view.Scenario(noise=2.5, missing_data=False))
    assert np.nanmean(hi.hazards.slope_std_deg) > np.nanmean(lo.hazards.slope_std_deg)


def test_scenario_reads_the_saved_result_instead_of_recomputing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    view.run_scenario(cfg, view.Scenario(noise=cfg.noise_level, missing_data=False))

    def boom(*a, **k):
        raise AssertionError("pipeline recomputed on load")

    monkeypatch.setattr(pipeline, "run_pipeline", boom)
    r = view.run_scenario(cfg, view.Scenario(noise=cfg.noise_level, missing_data=False))
    assert r.complete


def test_a_corrupt_saved_result_becomes_a_failure_with_a_reason(tmp_path):
    cfg = _cfg(tmp_path)
    p = pipeline.result_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"not a pickle")
    r = view.run_scenario(cfg, view.Scenario(noise=cfg.noise_level, missing_data=False))
    assert not r.complete
    assert r.error.stage == "dashboard_load"
    assert r.error.reason


# ---------------------------------------------------------------- the page


def _app(tmp_path, monkeypatch, **cfg_kw):
    from streamlit.testing.v1 import AppTest

    cfg_path = Path(tmp_path) / "cfg.json"
    _cfg(tmp_path, **cfg_kw).to_json(cfg_path)
    monkeypatch.setenv("ODYSSEY_CONFIG", str(cfg_path))
    app = Path(view.__file__).with_name("app.py")
    return AppTest.from_file(str(app), default_timeout=60)


def test_page_shows_the_three_showcase_items_and_labels(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch).run()
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in [*at.markdown, *at.caption])
    assert "SIMULATED" in text
    assert "Ranked science targets" in text
    assert "Cost map and planned path" in text
    assert len(at.dataframe) >= 1
    assert any("PASS" in x.value for x in at.success)


def test_page_controls_update_the_result_live(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch).run()
    at.sidebar.select_slider(key="noise").set_value(2.0).run()
    assert not at.exception, [e.value for e in at.exception]
    at.sidebar.radio(key="mode").set_value("bold").run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("bold access cost" in c.value for c in at.caption)
    at.sidebar.radio(key="planner").set_value("dijkstra").run()
    assert not at.exception, [e.value for e in at.exception]
    at.sidebar.checkbox(key="missing").set_value(True).run()
    assert not at.exception, [e.value for e in at.exception]


def test_page_shows_an_error_panel_with_the_reason(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, start=(9999, 9999)).run()
    assert not at.exception
    assert any("data" in e.value and "outside" in e.value for e in at.error)


def test_page_survives_every_noise_level_and_missing_data(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch).run()
    at.sidebar.checkbox(key="missing").set_value(True).run()
    for level in (0.0, 3.0):
        at.sidebar.select_slider(key="noise").set_value(level).run()
        assert not at.exception, (level, [e.value for e in at.exception])
        assert at.error or at.success or at.warning  # a badge, a warning or an error panel is always shown
