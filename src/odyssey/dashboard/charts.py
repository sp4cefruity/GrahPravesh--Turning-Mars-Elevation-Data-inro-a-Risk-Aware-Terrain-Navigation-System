"""Plotly figures for the dashboard. They only draw what a PipelineResult already holds."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import plotly.graph_objects as go

from .. import contracts as C
from . import view

PATH_COLOR = "#ff7f0e"
START_COLOR = "#ffffff"
OK_COLOR = "#2ca02c"
BAD_COLOR = "#d62728"
BASELINE_COLORS = {"b0": "#9467bd", "b1": "#e377c2"}
BASELINE_NAMES = {"b0": "B0 slope threshold", "b1": "B1 friction cost (reference)"}


def _xy(cells: list[C.Cell]) -> tuple[list[int], list[int]]:
    return [c[1] for c in cells], [c[0] for c in cells]


def cost_map_figure(res: C.PipelineResult, layer: str, pr: Optional[C.PathResult],
                    targets: list[C.ScienceTarget], selected: Optional[str],
                    baselines: tuple[str, ...] = (), segment: Optional[int] = None) -> go.Figure:
    """2D map: chosen layer, blocked and missing cells, planned path, start and targets."""
    grid = view.layer_grid(res, layer)
    label = dict(view.layer_options(res)).get(layer, layer)
    fig = go.Figure()
    fig.add_trace(go.Heatmap(z=grid, colorscale="Cividis", colorbar=dict(title=dict(text=label, side="right"), len=0.8),
                             hovertemplate="row %{y}, col %{x}<br>%{z:.3f}<extra></extra>", name=label))
    if layer != "blocked":
        blocked = np.where(res.cost_map.blocked & res.terrain.valid_mask, 1.0, np.nan)
        fig.add_trace(go.Heatmap(z=blocked, colorscale=[[0, "#111111"], [1, "#111111"]], showscale=False,
                                 opacity=0.65, hoverinfo="skip", name="hard blocked"))
    missing = np.where(~res.terrain.valid_mask, 1.0, np.nan)
    if np.isfinite(missing).any():
        fig.add_trace(go.Heatmap(z=missing, colorscale=[[0, "#c71585"], [1, "#c71585"]], showscale=False,
                                 opacity=0.55, hoverinfo="skip", name="missing data"))

    for name in baselines:
        bp = res.baseline_paths.get(name)
        if bp is not None and bp.cells:
            x, y = _xy(bp.cells)
            tail = "" if bp.safe else ", CROSSES HARD BLOCKS"
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=BASELINE_COLORS[name], width=2, dash="dash"),
                                     name=BASELINE_NAMES[name] + tail, hoverinfo="skip"))

    if pr is not None and pr.cells:
        x, y = _xy(pr.cells)
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", line=dict(color=PATH_COLOR, width=3),
            marker=dict(size=5, color=PATH_COLOR), name=f"planned path ({pr.mode})",
            customdata=[f"seg:{max(i - 1, 0)}" for i in range(len(x))],
            hovertemplate="step %{pointNumber}, row %{y}, col %{x}<br>click to trace this segment<extra></extra>"))
        if segment is not None and 0 <= segment < len(pr.segments):
            s = pr.segments[segment]
            fig.add_trace(go.Scatter(x=[s.from_cell[1], s.to_cell[1]], y=[s.from_cell[0], s.to_cell[0]],
                                     mode="lines", line=dict(color="#ffff00", width=7), hoverinfo="skip",
                                     name="selected segment"))

    sr, sc = res.start
    fig.add_trace(go.Scatter(x=[sc], y=[sr], mode="markers", name="rover start",
                             marker=dict(symbol="star", size=16, color=START_COLOR, line=dict(color="black", width=1)),
                             hovertemplate="rover start<extra></extra>"))
    ok = [t for t in targets if math.isfinite(t.path_cost)]
    bad = [t for t in targets if not math.isfinite(t.path_cost)]
    for group, colour, symbol, name in ((ok, OK_COLOR, "diamond", "science target"),
                                        (bad, BAD_COLOR, "x", "target with no safe path")):
        if not group:
            continue
        fig.add_trace(go.Scatter(
            x=[t.location[1] for t in group], y=[t.location[0] for t in group], mode="markers+text",
            text=[t.id for t in group], textposition="top center", name=name, customdata=[t.id for t in group],
            marker=dict(symbol=symbol, size=[18 if t.id == selected else 12 for t in group], color=colour,
                        line=dict(color="white", width=[3 if t.id == selected else 1 for t in group])),
            hovertext=[f"{t.id} ({t.kind})<br>score {t.score:.3f}, rank {t.rank_interval[0]} to {t.rank_interval[1]}"
                       for t in group],
            hovertemplate="%{hovertext}<br>click to select<extra></extra>"))

    fig.update_yaxes(autorange="reversed", scaleanchor="x", constrain="domain", title="row")
    fig.update_xaxes(constrain="domain", title="col")
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=520, template="plotly_white",
                      legend=dict(orientation="h", y=-0.12), clickmode="event+select", dragmode="pan")
    return fig


def terrain_3d_figure(res: C.PipelineResult, layer: str, pr: Optional[C.PathResult],
                      selected: Optional[C.ScienceTarget] = None, max_side: int = 128) -> go.Figure:
    dem = np.asarray(res.terrain.dem, dtype=float)
    step = max(1, math.ceil(max(dem.shape) / max_side))
    colour = view.layer_grid(res, layer)
    label = dict(view.layer_options(res)).get(layer, layer)
    fig = go.Figure(go.Surface(z=dem[::step, ::step], x=np.arange(dem.shape[1])[::step],
                               y=np.arange(dem.shape[0])[::step], surfacecolor=colour[::step, ::step],
                               colorscale="Cividis", colorbar=dict(title=dict(text=label, side="right"), len=0.7)))
    lift = 0.02 * float(np.nanmax(dem) - np.nanmin(dem) or 1.0)
    if pr is not None and pr.cells:
        x, y = _xy(pr.cells)
        z = [float(dem[c]) + lift for c in pr.cells]
        fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode="lines", line=dict(color=PATH_COLOR, width=6),
                                   name="planned path"))
    sr, sc = res.start
    fig.add_trace(go.Scatter3d(x=[sc], y=[sr], z=[float(dem[sr, sc]) + lift], mode="markers", name="rover start",
                               marker=dict(size=6, color="white", line=dict(color="black", width=1))))
    if selected is not None:
        r, c = selected.location
        fig.add_trace(go.Scatter3d(x=[c], y=[r], z=[float(dem[r, c]) + lift], mode="markers+text",
                                   text=[selected.id], name=selected.id, marker=dict(size=6, color=OK_COLOR)))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=480, scene=dict(
        aspectmode="data", yaxis=dict(autorange="reversed", title="row"), xaxis=dict(title="col"),
        zaxis=dict(title="elevation (m)")))
    return fig


def target_bands_figure(rows: list[dict]) -> go.Figure:
    """Score with its 5 to 95 percent band, one row per target. Unreachable targets sit at zero."""
    rows = rows[::-1]
    fig = go.Figure(go.Scatter(
        x=[r["score"] for r in rows], y=[r["id"] for r in rows], mode="markers",
        marker=dict(size=9, color=[OK_COLOR if r["reachable"] else BAD_COLOR for r in rows]),
        error_x=dict(type="data", symmetric=False,
                     array=[max(r["score_high"] - r["score"], 0) for r in rows],
                     arrayminus=[max(r["score"] - r["score_low"], 0) for r in rows]),
        hovertemplate="%{y}: score %{x:.3f}<extra></extra>"))
    fig.update_layout(height=40 + 28 * len(rows), margin=dict(l=10, r=10, t=5, b=25), template="plotly_white",
                      xaxis=dict(title="score with 5 to 95 percent band"), yaxis=dict(type="category"))
    return fig


def risk_curve_figure(res: C.PipelineResult) -> Optional[go.Figure]:
    pts = [p for p in res.risk_curve if math.isfinite(p.path_length) and math.isfinite(p.hazard_violation_rate)]
    if not pts:
        return None
    fig = go.Figure(go.Scatter(
        x=[p.path_length for p in pts], y=[p.hazard_violation_rate for p in pts], mode="lines+markers+text",
        text=[f"alpha {p.alpha:g}" for p in pts], textposition="top right",
        hovertemplate="alpha %{text}<br>length %{x:.1f} cells<br>violation rate %{y:.2f}<extra></extra>"))
    fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=30), template="plotly_white",
                      xaxis=dict(title="path length (cells)"), yaxis=dict(title="share of cells above hazard threshold"))
    return fig
