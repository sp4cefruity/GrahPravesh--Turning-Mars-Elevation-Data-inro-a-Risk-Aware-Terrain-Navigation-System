"""Dashboard logic with no Streamlit in it, so it can be tested and reused.

Everything here reads a PipelineResult. Nothing here recomputes a stage unless the viewer
changes a scenario control (noise, missing data), and then it goes through the pipeline's own
disk cache first.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from .. import contracts as C
from .. import pipeline, planning
from ..config import PipelineConfig

# ---------------------------------------------------------------- ranked table


def ranked_rows(targets: list[C.ScienceTarget]) -> list[dict[str, Any]]:
    """One flat row per target, best first, with every confidence band the pipeline gives."""
    rows = []
    for i, t in enumerate(targets):
        rows.append({
            "rank": i + 1, "id": t.id, "kind": t.kind, "location": t.location,
            "value": t.value_mean, "value_low": t.value_ci[0], "value_high": t.value_ci[1],
            "score": t.score, "score_low": t.score_ci[0], "score_high": t.score_ci[1],
            "rank_low": t.rank_interval[0], "rank_high": t.rank_interval[1], "p_top3": t.p_top3,
            "path_cost": t.path_cost, "reachable": math.isfinite(t.path_cost), "evidence": t.evidence,
        })
    return rows


def default_target(res: C.PipelineResult, targets: list[C.ScienceTarget], mode: str) -> Optional[str]:
    """Top ranked target that has a safe path in this mode."""
    for t in targets:
        by_mode = res.paths.get(t.id, {})
        if mode in by_mode and by_mode[mode].safe:
            return t.id
    return None


def targets_for_mode(res: C.PipelineResult, mode: str) -> tuple[list[C.ScienceTarget], str]:
    """Ranking for the chosen rover mode.

    The pipeline ranks with the cautious access cost. In bold mode the same ranking stage is
    called again with the bold paths in the cautious slot, so ranks move with the mode. The
    note says so on screen.
    """
    if mode == "cautious":
        return res.targets, ""
    swapped = {cid: {"cautious": by["bold"], "bold": by["bold"]} for cid, by in res.paths.items()}
    try:
        fn, _ = pipeline.resolve_stage(pipeline.STAGES["science_ranking"])
        ranked = fn(res.candidates, swapped, res.terrain, res.hazards, res.config)
        C.validate_targets(ranked, {c.id for c in res.candidates})
    except Exception as e:  # shown to the viewer, not hidden
        return res.targets, (f"Could not re-rank for bold mode ({type(e).__name__}: {e}). "
                             "Showing the cautious ranking.")
    return ranked, "Ranks use the bold access cost (alpha 0). Re-ranked by the same science stage."


# ---------------------------------------------------------------- paths


def select_path(res: C.PipelineResult, target_id: Optional[str], mode: str) -> Optional[C.PathResult]:
    return res.paths.get(target_id, {}).get(mode) if target_id else None


def planner_stats(pr: C.PathResult, planner: str) -> dict[str, Any]:
    """A* and Dijkstra return the same cost (the planner cross-checks it). Only the work differs."""
    if planner == "dijkstra":
        if pr.dijkstra_cost is None:
            return {"planner": "Dijkstra", "cost": None, "nodes_expanded": None,
                    "note": "Dijkstra cross-check was switched off in this run."}
        return {"planner": "Dijkstra", "cost": pr.dijkstra_cost, "nodes_expanded": pr.dijkstra_nodes_expanded,
                "note": "Same route and same cost as A*, found by exhaustive search. Used as the optimality check."}
    return {"planner": "A*", "cost": pr.total_cost, "nodes_expanded": pr.nodes_expanded,
            "note": "A* with an admissible heuristic. Dijkstra confirms the cost is optimal."}


# ---------------------------------------------------------------- safety badge


@dataclass
class Badge:
    level: str  # "pass", "fail" or "none"
    text: str
    detail: str


def safety_badge(res: C.PipelineResult, pr: Optional[C.PathResult]) -> Badge:
    """Re-run the safety check here. The planner's own flag is not trusted."""
    if pr is None:
        return Badge("none", "NO PATH SELECTED", "Pick a target to see its route.")
    if not pr.cells:
        why = pr.no_safe_path_reason or "no safe path"
        extra = ""
        if pr.min_feasible_risk is not None:
            extra = f" Lowest risk route that respects the hard blocks would still carry risk {pr.min_feasible_risk:.2f}."
        return Badge("none", "NO SAFE PATH", f"Reason: {why}.{extra}")
    rep = planning.verify_path(pr.cells, res.cost_map.blocked, res.terrain.slope_deg, res.cost_map.p_haz,
                               raise_on_violation=False)
    if rep.safe and pr.safe:
        return Badge("pass", "SAFETY CHECK: PASS",
                     f"{len(pr.cells)} cells checked against the true hard-block mask (no inflation). "
                     f"Max slope {rep.max_slope:.1f} deg, risk score {rep.risk_score:.2f}.")
    problems = rep.violations[:3] or ["planner marked this path as unsafe"]
    return Badge("fail", "SAFETY CHECK: FAIL", "; ".join(problems))


# ---------------------------------------------------------------- traces


def _f(x: Any) -> float:
    return float(x)


def cell_trace(res: C.PipelineResult, cell: C.Cell) -> dict[str, Any]:
    """Every input and derived value at one cell, with the rule that produced the hazard."""
    r, c = int(cell[0]), int(cell[1])
    h, w = res.terrain.shape
    if not (0 <= r < h and 0 <= c < w):
        raise IndexError(f"cell {(r, c)} is outside the {h} by {w} grid")
    hz, t, cm = res.hazards, res.terrain, res.cost_map
    cls = int(hz.terrain_class[r, c])
    code = int(hz.evidence_code[r, c]) if hz.evidence_code is not None else cls
    return {
        "cell": (r, c),
        "valid": bool(t.valid_mask[r, c]),
        "dem_m": _f(t.dem[r, c]),
        "slope_deg": _f(t.slope_deg[r, c]),
        "roughness": _f(t.roughness[r, c]),
        "hazard_prob": _f(hz.hazard_prob[r, c]),
        "epistemic_std": _f(hz.epistemic_std[r, c]),
        "slope_std_deg": None if hz.slope_std_deg is None else _f(hz.slope_std_deg[r, c]),
        "terrain_class": cls,
        "hard_block": bool(hz.hard_block[r, c]),
        "cost_mean": _f(cm.cost_mean[r, c]),
        "cost_std": _f(cm.cost_std[r, c]),
        "blocked": bool(cm.blocked[r, c]),
        "evidence": hz.evidence.get(code, "no evidence entry for this cell"),
        "simulated_inputs": list(t.simulated_layers),
    }


def segment_trace(res: C.PipelineResult, pr: C.PathResult, index: int) -> dict[str, Any]:
    if not 0 <= index < len(pr.segments):
        raise IndexError(f"segment {index} is outside 0 to {len(pr.segments) - 1}")
    s = pr.segments[index]
    return {
        "index": index, "from_cell": s.from_cell, "to_cell": s.to_cell, "length_cells": s.length_cells,
        "base": s.base, "mean": s.mean, "risk_term": s.risk_term, "edge_cost": s.edge_cost,
        "slope_deg": s.slope_deg, "p_haz": s.p_haz, "alpha": pr.alpha,
        "cell": cell_trace(res, s.to_cell),
    }


def target_trace(res: C.PipelineResult, t: C.ScienceTarget, pr: Optional[C.PathResult]) -> dict[str, Any]:
    cost: dict[str, Any] = {"total": math.inf, "segments": 0, "sum_of_segment_costs": 0.0}
    if pr is not None and pr.cells:
        cost = {"total": pr.total_cost, "risk_score": pr.risk_score, "max_slope_deg": pr.max_slope_on_path,
                "alpha": pr.alpha, "mode": pr.mode, "segments": len(pr.segments),
                "sum_of_segment_costs": float(sum(s.edge_cost for s in pr.segments))}
    return {
        "id": t.id,
        "inputs": {"location": t.location, "kind": t.kind, "start": res.start,
                   "value_mean": t.value_mean, "value_ci": t.value_ci,
                   "simulated_inputs": list(res.terrain.simulated_layers)},
        "score": {"score": t.score, "score_ci": t.score_ci, "rank_interval": t.rank_interval, "p_top3": t.p_top3},
        "cost": cost,
        "evidence": t.evidence,
    }


# ---------------------------------------------------------------- simulated labels and layers


def simulated_labels(res: C.PipelineResult) -> list[str]:
    out = []
    if res.terrain is not None and res.terrain.simulated_layers:
        out.append("Simulated layers: " + ", ".join(res.terrain.simulated_layers))
    if res.stub_stages:
        out.append("Stub stages, dummy output: " + ", ".join(res.stub_stages))
    if res.terrain is not None and res.terrain.source:
        out.append("Terrain source: " + res.terrain.source)
    return out


def layer_options(res: C.PipelineResult) -> list[tuple[str, str]]:
    sim = set(res.terrain.simulated_layers)
    tag = lambda name, label: f"{label} (SIMULATED)" if name in sim else label  # noqa: E731
    opts = [("cost_mean", "Cost, mean"), ("cost_std", "Cost, uncertainty (std)"),
            ("hazard_prob", "Hazard probability"), ("slope_deg", "Slope (deg)"),
            ("roughness", "Roughness"), ("dem", tag("dem", "Elevation (m)")),
            ("blocked", "Hard blocked cells")]
    if res.hazards.slope_std_deg is not None:
        opts.append(("slope_std_deg", "Slope uncertainty (deg)"))
    for name in res.terrain.bands:
        simulated = name in sim or name.endswith("_simulated")
        opts.append((f"band:{name}", f"{name}" + (" (SIMULATED)" if simulated else "")))
    return opts


def layer_grid(res: C.PipelineResult, key: str) -> np.ndarray:
    t, hz, cm = res.terrain, res.hazards, res.cost_map
    if key.startswith("band:"):
        return np.asarray(t.bands[key[5:]], dtype=float)
    table = {"cost_mean": cm.cost_mean, "cost_std": cm.cost_std, "hazard_prob": hz.hazard_prob,
             "slope_deg": t.slope_deg, "roughness": t.roughness, "dem": t.dem,
             "slope_std_deg": hz.slope_std_deg, "blocked": cm.blocked}
    return np.asarray(table[key], dtype=float)


# ---------------------------------------------------------------- scenarios


@dataclass(frozen=True)
class Scenario:
    noise: float
    missing_data: bool


def missing_patch(res: C.PipelineResult) -> np.ndarray:
    """A simulated block of lost data placed on the middle of the default route.

    The demo moment is the route bending around it. The area around the start stays valid.
    """
    shape = res.terrain.shape
    size = max(3, round(0.1 * min(shape)))
    pr = select_path(res, res.default_target_id, "cautious")
    if pr is not None and pr.cells:
        cr, cc = pr.cells[len(pr.cells) // 2]
    else:
        cr, cc = shape[0] // 2, shape[1] // 2
    r0, c0 = max(0, cr - size // 2), max(0, cc - size // 2)
    patch = np.zeros(shape, dtype=bool)
    patch[r0:r0 + size, c0:c0 + size] = True
    sr, sc = res.start
    patch[max(0, sr - 3):sr + 4, max(0, sc - 3):sc + 4] = False
    return patch


def _failure(config: PipelineConfig, stage: str, reason: str) -> C.PipelineResult:
    return C.PipelineResult(config=config, error=C.StageFailure(stage, reason))


def run_scenario(config: PipelineConfig, sc: Scenario) -> C.PipelineResult:
    """Load the saved result for this noise level, or run once and save it.

    With missing data on, the data stage is wrapped so a simulated patch is cut out of the
    valid mask. That run is not saved to disk. Any load failure comes back as a result whose
    `error` says why, so the page can show it.
    """
    cfg = dataclasses.replace(config, noise_level=float(sc.noise))
    try:
        base = pipeline.load_or_run(cfg)
    except Exception as e:
        return _failure(cfg, "dashboard_load", f"{type(e).__name__}: {e}")
    if not sc.missing_data or not base.complete:
        return base

    patch = missing_patch(base)
    data_fn, is_stub = pipeline.resolve_stage(pipeline.STAGES["data"])

    def data_with_patch(config: PipelineConfig) -> C.TerrainGrid:
        t = data_fn(config)
        return dataclasses.replace(
            t, valid_mask=t.valid_mask & ~patch,
            simulated_layers=[*t.simulated_layers, "missing_patch_simulated"])

    try:
        res = pipeline.run_pipeline(cfg, overrides={"data": data_with_patch})
    except Exception as e:
        return _failure(cfg, "dashboard_load", f"{type(e).__name__}: {e}")
    if is_stub:
        res.stub_stages.insert(0, "data")
        res.notes = [n for n in res.notes if not n.startswith("Stub stages")]
        res.notes.append("Stub stages in this run: " + ", ".join(res.stub_stages))
    res.notes.append("Missing data patch added by the dashboard (SIMULATED).")
    return res
