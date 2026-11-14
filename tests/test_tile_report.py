"""Checks for data/tile_report.py. Extraction first, on a small synthetic scene through the real pipeline."""

import copy
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from odyssey import pipeline
from odyssey.config import PipelineConfig
from odyssey.data.dem import _config
from odyssey.data.tile_report import TILE_COLUMNS, by_site, render_doc, run_all, run_tile, tile_row
from odyssey.tables import mean, to_markdown
from odyssey.contracts import StageFailure
from synthetic import fake_tile, synthetic_terrain

META = {"tile": "X", "site": "Nowhere", "role": "test"}


@pytest.fixture(scope="module")
def res():
    r = pipeline.run_pipeline(PipelineConfig(), overrides={"data": synthetic_terrain})
    assert r.complete, r.error
    return r


def test_row_matches_numbers_recomputed_from_the_same_run(res):
    row = tile_row(res, META)
    assert row["tile"] == "X" and row["site"] == "Nowhere" and row["error"] == ""
    assert np.isclose(row["valid_pct"], 100 * res.terrain.valid_mask.mean())
    assert np.isclose(row["blocked_pct"], 100 * res.cost_map.blocked.mean())
    assert row["candidates"] == len(res.candidates)
    assert row["reach_cautious"] == sum(by["cautious"].safe for by in res.paths.values())
    assert row["reach_bold"] == sum(by["bold"].safe for by in res.paths.values())
    s = res.terrain.slope_deg[res.terrain.valid_mask]
    assert np.isclose(row["slope_p95"], np.nanpercentile(s, 95)) and row["slope_p50"] <= row["slope_p95"]
    assert np.isclose(row["steep_pct"], 100 * np.mean(s[np.isfinite(s)] > res.config.hard_block_slope_deg))


def test_cautious_route_never_costs_less_than_bold_and_timings_add_up(res):
    row = tile_row(res, META)
    assert np.isnan(row["caut_over_bold_cost"]) or row["caut_over_bold_cost"] >= 1.0 - 1e-9
    assert 0.0 < row["plan_s"] <= row["total_s"]


def test_baseline_columns_are_binary_or_nan(res):
    row = tile_row(res, META)
    for k in ("b0_safe", "b1_safe"):
        assert np.isnan(row[k]) or row[k] in (0.0, 1.0)


def test_no_reachable_target_gives_nan_for_routes_and_zero_for_counts(res):
    dead = copy.deepcopy(res)
    dead.default_target_id, dead.baseline_paths = None, {}
    for by in dead.paths.values():
        for p in by.values():
            p.safe, p.cells = False, []
    row = tile_row(dead, META)
    assert row["reach_bold"] == 0 and row["reach_cautious"] == 0           # a real zero, not a gap
    for k in ("caut_over_bold_cost", "max_slope_cautious", "max_slope_b0", "max_slope_b1", "b0_safe", "b1_safe"):
        assert np.isnan(row[k]), k                                          # there is nothing to report
    assert row["blocked_pct"] == tile_row(res, META)["blocked_pct"]         # terrain columns are unaffected


def test_a_scene_with_no_valid_cells_does_not_crash_the_row(res):
    empty = copy.deepcopy(res)
    empty.terrain.valid_mask[:] = False
    row = tile_row(empty, META)
    assert row["valid_pct"] == 0.0 and np.isnan(row["slope_p50"]) and np.isnan(row["steep_pct"])


# ---------------------------------------------------------------- the real tiles


@pytest.fixture(scope="module")
def rows():
    return run_all()  # every tile in tiles.yaml, one real pipeline run each


def test_every_tile_in_tiles_yaml_gets_a_complete_row(rows):
    assert [r["tile"] for r in rows] == list(_config()["tiles"])
    assert all(r["error"] == "" for r in rows)
    assert all(set(r) == set(TILE_COLUMNS) for r in rows)


def test_the_two_sites_differ_in_the_way_the_terrain_does(rows):
    t = {r["tile"]: r for r in rows}
    assert t["T4"]["steep_pct"] > t["T1"]["steep_pct"] and t["T4"]["slope_p95"] > t["T1"]["slope_p95"]
    assert t["T4"]["blocked_pct"] > t["T1"]["blocked_pct"]          # the scarp blocks far more than the crater floor
    assert t["T4"]["reach_cautious"] < t["T1"]["reach_cautious"]    # and leaves fewer targets reachable
    assert t["T1"]["site"] == "Jezero" and t["T4"]["site"] == "Promethei Terra"


def test_by_site_groups_tiles_and_never_pools_the_sites(rows):
    sites = {r["site"]: r for r in by_site(rows)}
    assert set(sites) == {"Jezero", "Promethei Terra"}
    assert sites["Jezero"]["tiles"] == 3 and sites["Promethei Terra"]["tiles"] == 2
    assert sites["Jezero"]["failed"] == 0
    j = [r["blocked_pct"] for r in rows if r["site"] == "Jezero"]
    assert np.isclose(sites["Jezero"]["blocked_pct"], np.mean(j))


def test_a_row_is_repeatable(rows):
    again = run_tile("T1")
    first = next(r for r in rows if r["tile"] == "T1")
    for k in TILE_COLUMNS:
        a, b = first[k], again[k]
        assert (isinstance(a, float) and np.isnan(a) and np.isnan(b)) or (k in ("plan_s", "total_s")) or a == b, k


def test_an_unknown_tile_becomes_an_error_row_and_does_not_stop_the_table():
    out = run_all(["T1", "T9"])
    assert out[0]["error"] == "" and out[1]["error"].startswith("KeyError")
    assert set(out[1]) == set(TILE_COLUMNS) and np.isnan(out[1]["blocked_pct"])


def test_shared_table_helpers():
    assert np.isnan(mean([])) and mean([1.0, 3.0]) == 2.0
    assert "n/a" in to_markdown([{"a": float("nan"), "b": 1}]) and to_markdown([]) == "(no rows)"


# ---------------------------------------------------------------- awkward cases, one bad tile must never stop the table


def _patched_config(monkeypatch, tiles=None, products=None):
    import odyssey.data.dem as dem
    cfg = copy.deepcopy(dem._config())
    cfg["tiles"].update(tiles or {})
    cfg["products"].update(products or {})
    monkeypatch.setattr(dem, "_config", lambda: cfg)


def _all_columns_and_error(row, text):
    assert set(row) == set(TILE_COLUMNS) and text in row["error"] and np.isnan(row["blocked_pct"])


def test_a_tile_with_no_window_is_an_error_row(monkeypatch):
    _patched_config(monkeypatch, tiles={"TX": {"product": "A", "window": None, "role": "x"}})
    _all_columns_and_error(run_tile("TX"), "no window")


def test_a_tile_whose_product_is_not_defined_is_an_error_row(monkeypatch):
    _patched_config(monkeypatch, tiles={"TX": {"product": "Z", "window": [0, 0], "role": "x"}})
    row = run_tile("TX")
    _all_columns_and_error(row, "KeyError")
    assert row["site"] == "Z"            # falls back to the product key rather than crashing on a missing name


def test_a_failed_download_is_an_error_row(monkeypatch, tmp_path):
    import odyssey.data.dem as dem
    import requests
    monkeypatch.setattr(dem, "CACHE_DIR", tmp_path)                   # empty cache, so it must fetch
    def no_network(*a, **k):
        raise requests.ConnectionError("no network")
    monkeypatch.setattr(requests.Session, "get", no_network)
    _all_columns_and_error(run_tile("T1"), "ConnectionError")


def test_a_corrupt_cache_file_is_an_error_row(monkeypatch, tmp_path):
    import odyssey.data.dem as dem
    (tmp_path / "T1.npz").write_bytes(b"this is not a zip file")
    monkeypatch.setattr(dem, "CACHE_DIR", tmp_path)
    row = run_tile("T1")
    assert row["error"] != "" and set(row) == set(TILE_COLUMNS)


def test_a_failing_pipeline_stage_is_an_error_row_naming_the_stage(monkeypatch):
    failed = SimpleNamespace(complete=False, error=StageFailure("cost_map", "start cell (8, 8) is blocked"))
    monkeypatch.setattr(pipeline, "run_pipeline", lambda *a, **k: failed)
    _all_columns_and_error(run_tile("T1"), "cost_map: start cell (8, 8) is blocked")


def test_a_source_dem_with_real_holes_runs_end_to_end(monkeypatch):
    import odyssey.data.dem as dem
    monkeypatch.setattr(dem, "load_tile", lambda tile_id: fake_tile(nan_patch=True))
    row = run_tile("T1")
    assert row["error"] == "", row["error"]
    assert row["valid_pct"] < 100.0 and np.isfinite(row["slope_p95"])


def test_by_site_with_a_failed_tile_counts_it_and_leaves_it_out_of_the_means(rows):
    bad = run_tile("T9")
    bad["site"] = "Jezero"                                               # pretend the failed tile belongs to Jezero
    mixed = [r for r in rows if r["site"] == "Jezero"] + [bad]
    jez = by_site(mixed)[0]
    assert jez["tiles"] == 4 and jez["failed"] == 1
    assert np.isclose(jez["blocked_pct"], np.mean([r["blocked_pct"] for r in rows if r["site"] == "Jezero"]))


def test_the_page_has_every_section_both_tables_and_no_raw_nan(rows):
    text = render_doc(rows, 0, 1.0)
    for heading in ("## Per tile", "## By site", "## Columns", "## Read this carefully"):
        assert heading in text
    assert "scene seed 0" in text and re.search(r"nan", text) is None
    assert text == render_doc(rows, 0, 1.0)                              # the same rows always give the same page


def test_the_committed_page_lists_every_tile_in_tiles_yaml():
    page = (Path(__file__).parents[1] / "docs" / "TILE_RESULTS.md").read_text(encoding="utf-8")
    for tile in _config()["tiles"]:
        assert f"| {tile} |" in page, f"{tile} is missing from docs/TILE_RESULTS.md, regenerate it"
