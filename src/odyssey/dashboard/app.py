"""MARS-09 Odyssey dashboard (spec 04).

Run from the repo root:
    streamlit run src/odyssey/dashboard/app.py
Set ODYSSEY_CONFIG to a pipeline config JSON to show a different run.

The page reads a saved PipelineResult. It only runs the pipeline when the viewer moves a
scenario control to a value that has not been saved yet.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

try:
    import odyssey  # noqa: F401
except ModuleNotFoundError:  # launched without PYTHONPATH, add src next to this package
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from odyssey.config import PipelineConfig
from odyssey.dashboard import charts, view

NOISE_OPTIONS = [round(0.25 * i, 2) for i in range(0, 13)]
LAYER_HELP = "Simulated layers carry the word SIMULATED."

st.set_page_config(page_title="MARS-09 Odyssey", layout="wide", initial_sidebar_state="expanded")
st.markdown("<style>.block-container{padding-top:2.2rem;padding-bottom:1rem}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------- loading


def _base_config() -> PipelineConfig:
    path = os.environ.get("ODYSSEY_CONFIG")
    return PipelineConfig.from_json(path) if path else PipelineConfig()


@st.cache_resource(show_spinner="Loading saved result")
def _load(cfg_json: str, noise: float, missing: bool):
    cfg = PipelineConfig.from_dict(json.loads(cfg_json))
    return view.run_scenario(cfg, view.Scenario(noise=noise, missing_data=missing))


@st.cache_resource(show_spinner=False)
def _ranking(cfg_json: str, noise: float, missing: bool, mode: str):
    res = _load(cfg_json, noise, missing)
    return view.targets_for_mode(res, mode)


try:
    base_cfg = _base_config()
except Exception as e:  # a bad config file must not give a blank page
    st.error(f"Could not read the config file in ODYSSEY_CONFIG: {type(e).__name__}: {e}")
    st.stop()
cfg_json = json.dumps(base_cfg.to_dict(), default=list)


# ---------------------------------------------------------------- callbacks (set widget state before rerun)


def _on_map_select() -> None:
    ev = st.session_state.get("map_chart")
    points = getattr(getattr(ev, "selection", None), "points", None) or []
    for p in points:
        cd = p.get("customdata")
        cd = cd[0] if isinstance(cd, (list, tuple)) and cd else cd
        if isinstance(cd, str) and cd.startswith("seg:"):
            st.session_state["segment"] = int(cd[4:])
            return
        if isinstance(cd, str):
            st.session_state["target"] = cd
            st.session_state["segment"] = 0
            return


def _on_table_select() -> None:
    ev = st.session_state.get("targets_table")
    rows = getattr(getattr(ev, "selection", None), "rows", None) or []
    ids = st.session_state.get("_table_ids", [])
    if rows and rows[0] < len(ids):
        st.session_state["target"] = ids[rows[0]]
        st.session_state["segment"] = 0


# ---------------------------------------------------------------- controls

with st.sidebar:
    st.header("Controls")
    default_noise = min(NOISE_OPTIONS, key=lambda v: abs(v - base_cfg.noise_level))
    noise = st.select_slider("Sensor noise level", options=NOISE_OPTIONS, value=default_noise, key="noise",
                             help="Scales the noise added to the DEM and carried into slope uncertainty.")
    missing = st.checkbox("Missing data patch (SIMULATED)", value=False, key="missing",
                          help="Cuts a block of lost data out of the map across the default route.")
    mode = st.radio("Rover mode", ["cautious", "bold"], key="mode", horizontal=True,
                    help="Cautious penalises uncertain cells (CVaR 0.95). Bold uses the mean cost only.")
    planner = st.radio("Planner", ["astar", "dijkstra"], key="planner", horizontal=True,
                       format_func=lambda p: "A*" if p == "astar" else "Dijkstra")
    st.divider()

res = _load(cfg_json, float(noise), bool(missing))

st.markdown("### MARS-09 Odyssey: where is it safe, how do we get there, what is worth seeing")

# ---------------------------------------------------------------- error panel

if not res.complete:
    st.error(f"The pipeline stopped at stage '{res.error.stage}'. Reason: {res.error.reason}")
    st.caption("Nothing is drawn from a failed run. Change a control in the sidebar or fix the stage named above.")
    if res.timings_s:
        st.caption("Stage timings (s): " + ", ".join(f"{k} {v:.2f}" for k, v in res.timings_s.items()))
    st.stop()

# ---------------------------------------------------------------- state for this view

targets, rank_note = _ranking(cfg_json, float(noise), bool(missing), mode)
rows = view.ranked_rows(targets)
ids = [t.id for t in targets]
st.session_state["_table_ids"] = ids
top = view.default_target(res, targets, mode)
if st.session_state.get("target") not in ids:
    st.session_state["target"] = top or (ids[0] if ids else None)
with st.sidebar:
    if ids:
        st.selectbox("Target", ids, key="target",
                     format_func=lambda i: f"{i}  (rank {ids.index(i) + 1}" + ("" if rows[ids.index(i)]["reachable"] else ", NO SAFE PATH") + ")",
                     help="Defaults to the top ranked target with a safe path.")
    layer_opts = view.layer_options(res)
    layer = st.selectbox("Map layer", [k for k, _ in layer_opts], key="layer", help=LAYER_HELP,
                         format_func=dict(layer_opts).get)
    base_sel = st.multiselect("Baseline routes", ["b0", "b1"], key="baselines", default=[],
                              format_func=lambda n: charts.BASELINE_NAMES[n],
                              help="B1 is a reference reproduction of a published friction cost, not a tuned planner.")

selected = next((t for t in targets if t.id == st.session_state["target"]), None)
pr = view.select_path(res, selected.id, mode) if selected else None
n_seg = len(pr.segments) if pr is not None else 0
if st.session_state.get("segment", 0) >= max(n_seg, 1):
    st.session_state["segment"] = 0
segment = st.session_state.get("segment", 0) if n_seg else None

# ---------------------------------------------------------------- banners

for line in view.simulated_labels(res):
    st.caption(f":orange[SIMULATED] {line}" if line.startswith("Simulated") else line)
if res.default_target_id is None:
    st.warning("No safe path to any target in this scenario. Nothing is drawn as a route. "
               "Lower the noise or remove the missing data patch.")

# ---------------------------------------------------------------- first screen: map, path, ranked targets

left, right = st.columns([3, 2], gap="medium")

with left:
    st.markdown("#### Cost map and planned path")
    st.plotly_chart(
        charts.cost_map_figure(res, layer, pr, targets, st.session_state.get("target"),
                               tuple(base_sel), segment),
        key="map_chart", on_select=_on_map_select, selection_mode=("points",), width="stretch")

with right:
    badge = view.safety_badge(res, pr)
    {"pass": st.success, "fail": st.error, "none": st.warning}[badge.level](f"**{badge.text}.** {badge.detail}")
    st.markdown("#### Ranked science targets")
    table = pd.DataFrame([{
        "Rank": r["rank"], "Target": r["id"], "Type": r["kind"],
        "Score": r["score"], "Score 5%": r["score_low"], "Score 95%": r["score_high"],
        "Rank range": f"{r['rank_low']} to {r['rank_high']}", "P(top 3)": r["p_top3"],
        "Access cost": r["path_cost"] if r["reachable"] else None,
        "Status": "reachable" if r["reachable"] else "NO SAFE PATH",
    } for r in rows])
    st.dataframe(
        table, hide_index=True, width="stretch", height=min(60 + 35 * len(rows), 290),
        key="targets_table", on_select=_on_table_select, selection_mode="single-row",
        column_config={
            "Score": st.column_config.NumberColumn(format="%.3f"),
            "Score 5%": st.column_config.NumberColumn(format="%.3f"),
            "Score 95%": st.column_config.NumberColumn(format="%.3f"),
            "P(top 3)": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f"),
            "Access cost": st.column_config.NumberColumn(format="%.1f"),
        })
    if rank_note:
        st.caption(rank_note)
    if rows:
        st.plotly_chart(charts.target_bands_figure(rows), width="stretch", key="bands_chart")
    if pr is not None and pr.cells:
        ps = view.planner_stats(pr, planner)
        a, b, c = st.columns(3)
        a.metric(f"{ps['planner']} cost", "n/a" if ps["cost"] is None else f"{ps['cost']:.1f}")
        b.metric("Nodes expanded", "n/a" if ps["nodes_expanded"] is None else f"{ps['nodes_expanded']:,}")
        c.metric("Risk score", f"{pr.risk_score:.2f}")
        st.caption(ps["note"])

# ---------------------------------------------------------------- trace

st.divider()
st.markdown("#### Trace: why this target and this route")
tcol, scol = st.columns(2, gap="medium")
with tcol:
    if selected is not None:
        tr = view.target_trace(res, selected, pr)
        st.info(f"**{selected.id} evidence.** {tr['evidence']}")
        st.write(f"Value {selected.value_mean:.3f} (95% band {selected.value_ci[0]:.3f} to {selected.value_ci[1]:.3f}). "
                 f"Score {selected.score:.3f}, rank range {selected.rank_interval[0]} to {selected.rank_interval[1]}, "
                 f"P(top 3) {selected.p_top3:.2f}.")
        if pr is not None and pr.cells:
            st.write(f"Route: {tr['cost']['segments']} segments, total cost {tr['cost']['total']:.2f}, "
                     f"max slope {tr['cost']['max_slope_deg']:.1f} deg, mode {pr.mode} (alpha {pr.alpha:g}).")
        elif pr is not None:
            st.warning(f"No route: {pr.no_safe_path_reason}")
        with st.expander("Raw inputs"):
            st.json(tr["inputs"], expanded=False)
with scol:
    if n_seg:
        seg_i = st.slider("Path segment (or click the path on the map)", 0, n_seg - 1, key="segment")
        st_ = view.segment_trace(res, pr, seg_i)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Base", f"{st_['base']:.3f}")
        m2.metric("Mean cost", f"{st_['mean']:.3f}")
        m3.metric("Risk term", f"{st_['risk_term']:.3f}")
        m4.metric("Edge cost", f"{st_['edge_cost']:.3f}")
        cell = st_["cell"]
        st.caption(f"Step {st_['from_cell']} to {st_['to_cell']}. Slope {cell['slope_deg']:.1f} deg, "
                   f"hazard probability {cell['hazard_prob']:.2f}. Rule: {cell['evidence']}")
    with st.expander("Inspect any cell"):
        h, w = res.terrain.shape
        r_in = st.number_input("Row", 0, h - 1, value=int(res.start[0]), key="cell_row")
        c_in = st.number_input("Col", 0, w - 1, value=int(res.start[1]), key="cell_col")
        st.json(view.cell_trace(res, (int(r_in), int(c_in))), expanded=True)

# ---------------------------------------------------------------- below the fold

st.divider()
v3, vr = st.columns([3, 2], gap="medium")
with v3:
    st.markdown("#### 3D terrain" + (" (SIMULATED elevation)" if "dem" in res.terrain.simulated_layers else ""))
    st.plotly_chart(charts.terrain_3d_figure(res, layer, pr, selected), width="stretch", key="terrain_3d")
with vr:
    st.markdown("#### Risk versus path length")
    fig = charts.risk_curve_figure(res)
    if fig is None:
        st.caption("No risk curve for this run (no reachable default target).")
    else:
        st.plotly_chart(fig, width="stretch", key="risk_curve")
        st.caption("Each point is a CVaR level alpha. Higher alpha takes longer routes with fewer hazardous cells.")
    if res.baseline_paths:
        st.markdown("**Baselines on the default goal**")
        brow = []
        for name, bp in res.baseline_paths.items():
            brow.append({"Route": charts.BASELINE_NAMES[name], "Cells": len(bp.cells),
                         "Risk score": None if not bp.cells else bp.risk_score,
                         "Max slope": None if not bp.cells else bp.max_slope_on_path,
                         "Passes hard-block check": bp.safe})
        st.dataframe(pd.DataFrame(brow), hide_index=True, width="stretch")

with st.expander("Run notes and timings"):
    for n in res.notes:
        st.write("- " + n)
    st.write("Stage timings (s): " + ", ".join(f"{k} {v:.2f}" for k, v in res.timings_s.items()))
