"""Per-tile results table (spec 05). One real pipeline run per tile, reported tile by tile and by site, never pooled.

`tile_row` turns one finished run into one row. It is a pure function of the run, so it can be tested with
known answers. Columns, all measured on the 256 by 256 planning grid at about 2 m:
- terrain:   valid share, median and 95th percentile slope, share steeper than the hard block limit, blocked share.
- reach:     candidates found, and how many have a safe route in bold and in cautious mode.
- route:     cautious cost over bold cost for the default target, and the steepest slope each route touches
             (cautious, and the two baselines B0 and B1, which have no hazard model of their own).
- safe:      whether each baseline route passes the independent safety check (1 yes, 0 no).
- time:      seconds spent planning, and in the whole run.
NaN means the thing does not exist for that tile (for example no safe route to any target), never zero.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from ..tables import mean, to_markdown

NAN = float("nan")


def _route_ok(p) -> bool:
    return p is not None and bool(p.safe) and bool(p.cells)


def _slope(p) -> float:
    """Steepest slope on a route, NaN if there is no route."""
    return float(p.max_slope_on_path) if p is not None and p.cells and np.isfinite(p.max_slope_on_path) else NAN


def tile_row(res, meta: dict) -> dict:
    """One row from a finished, complete pipeline run. `meta` carries tile, site and role."""
    terrain, cm, cfg = res.terrain, res.cost_map, res.config
    slope = terrain.slope_deg[terrain.valid_mask]
    slope = slope[np.isfinite(slope)]
    reach = lambda mode: sum(bool(by[mode].safe) for by in res.paths.values())

    goal = res.paths.get(res.default_target_id, {}) if res.default_target_id else {}
    bold, caut = goal.get("bold"), goal.get("cautious")
    base = res.baseline_paths or {}
    timings = res.timings_s

    row = dict(meta)
    row.update({
        "valid_pct": 100.0 * float(terrain.valid_mask.mean()),
        "slope_p50": float(np.percentile(slope, 50)) if slope.size else NAN,
        "slope_p95": float(np.percentile(slope, 95)) if slope.size else NAN,
        "steep_pct": 100.0 * float((slope > cfg.hard_block_slope_deg).mean()) if slope.size else NAN,
        "blocked_pct": 100.0 * float(cm.blocked.mean()),
        "candidates": len(res.candidates),
        "reach_bold": reach("bold"),
        "reach_cautious": reach("cautious"),
        "caut_over_bold_cost": (caut.total_cost / bold.total_cost
                                if _route_ok(caut) and _route_ok(bold) and bold.total_cost > 0 else NAN),
        "max_slope_cautious": _slope(caut) if _route_ok(caut) else NAN,
        "max_slope_b0": _slope(base.get("b0")),
        "max_slope_b1": _slope(base.get("b1")),
        "b0_safe": float(base["b0"].safe) if base.get("b0") is not None and base["b0"].cells else NAN,
        "b1_safe": float(base["b1"].safe) if base.get("b1") is not None and base["b1"].cells else NAN,
        "plan_s": float(timings.get("planning", 0.0) + timings.get("planning_extras", 0.0)),
        "total_s": float(sum(timings.values())),
        "error": "",
    })
    return row


# ---------------------------------------------------------------- running it over the tiles

TILE_COLUMNS = ("tile", "site", "role", "valid_pct", "slope_p50", "slope_p95", "steep_pct", "blocked_pct",
                "candidates", "reach_bold", "reach_cautious", "caut_over_bold_cost", "max_slope_cautious",
                "max_slope_b0", "max_slope_b1", "b0_safe", "b1_safe", "plan_s", "total_s", "error")
TEXT_COLUMNS = ("tile", "site", "role", "error")


def run_scene(tile_id: str, seed: int = 0, noise_level: float = 1.0, n_candidates: int = 5):
    """Build one scene from a tile and run the real pipeline on it. Returns (result, truth)."""
    from .. import pipeline
    from ..config import PipelineConfig, Seeds
    from .dem import load_tile
    from .scene import build_scene

    cfg = dataclasses.replace(PipelineConfig(), seeds=Seeds(data=seed), noise_level=noise_level,
                              n_candidates=n_candidates)
    grid, truth = build_scene(load_tile(tile_id), seed=seed, noise_level=noise_level, keep_clear=tuple(cfg.start))
    return pipeline.run_pipeline(cfg, overrides={"data": lambda c: grid}), truth


def tile_meta(tile_id: str) -> dict:
    from .dem import _config

    cfg = _config()
    t = cfg["tiles"][tile_id]
    return {"tile": tile_id, "site": cfg["products"].get(t["product"], {}).get("name", t["product"]),
            "role": t.get("role", "")}


def _complete(row: dict) -> dict:
    """Every column present, so a failed tile still lines up with the others."""
    return {c: row.get(c, "" if c in TEXT_COLUMNS else NAN) for c in TILE_COLUMNS}


def run_tile(tile_id: str, seed: int = 0, noise_level: float = 1.0) -> dict:
    """One row for one tile. Any failure becomes an error row, so one bad tile never stops the table."""
    try:
        meta = tile_meta(tile_id)
    except KeyError:
        return _complete({"tile": tile_id, "error": f"KeyError: no tile {tile_id} in tiles.yaml"})
    try:
        res, _ = run_scene(tile_id, seed, noise_level)
    except Exception as e:
        return _complete({**meta, "error": f"{type(e).__name__}: {e}"})
    if not res.complete:
        return _complete({**meta, "error": f"{res.error.stage}: {res.error.reason}"})
    return _complete(tile_row(res, meta))


def run_all(tiles=None, seed: int = 0, noise_level: float = 1.0) -> list[dict]:
    from .dem import _config

    return [run_tile(t, seed, noise_level) for t in (tiles or list(_config()["tiles"]))]


def by_site(rows) -> list[dict]:
    """Mean of each numeric column per site, over tiles that ran. Failed tiles are counted, not averaged in."""
    sites: dict = {}
    for r in rows:
        sites.setdefault(r["site"], []).append(r)
    table = []
    for site, rs in sites.items():
        ok = [r for r in rs if not r["error"]]
        line = {"site": site, "tiles": len(rs), "failed": len(rs) - len(ok)}
        for c in TILE_COLUMNS:
            if c not in TEXT_COLUMNS:
                line[c] = mean(r[c] for r in ok if np.isfinite(r[c]))
        table.append(line)
    return table


COLUMN_NOTES = """\
- `valid_pct`: share of cells with data. It includes the gaps we inject on purpose, so it is the same for every tile at one seed.
- `slope_p50`, `slope_p95`: median and 95th percentile slope in degrees, on the 2 m planning grid.
- `steep_pct`: share of cells steeper than the hard block limit.
- `blocked_pct`: share of cells the planner may never enter (hard block or no data).
- `candidates`: science targets found. `reach_bold` and `reach_cautious`: how many have a safe route in each mode.
- `caut_over_bold_cost`: cost of the cautious route divided by the bold route to the default target.
- `max_slope_cautious`, `max_slope_b0`, `max_slope_b1`: the steepest slope each route touches. B0 and B1 are the baselines.
- `b0_safe`, `b1_safe`: 1 if that baseline route passes the independent safety check, 0 if not.
- `plan_s`, `total_s`: seconds spent planning and in the whole run. They depend on the machine.
- `n/a` means the thing does not exist for that tile, for example no safe route to any target."""

CAVEATS = """\
- One seed and one noise level. This is a snapshot of one scene per tile, not an average over scenes.
- Slopes are measured after the scene is reduced to 2 m cells. At the native 1 m, slope is mostly pixel noise.
- The sites are never pooled. Jezero and Promethei Terra are different terrain, processed as separate DTMs.
- The per-site rows average a few tiles. Treat them as a summary of the table above, not as a measurement."""


def render_doc(rows, seed: int, noise_level: float) -> str:
    return (
        "# Per-tile results\n\n"
        "Generated by `python -m odyssey.data.tile_report --doc docs/TILE_RESULTS.md`. One real pipeline run per tile "
        f"with scene seed {seed} and noise level {noise_level}, default config, on the 256 by 256 planning grid "
        "(about 2 m per cell). Tile windows and sources are in `src/odyssey/data/tiles.yaml`.\n\n"
        "## Per tile\n\n" + to_markdown(rows) + "\n\n"
        "## By site\n\n" + to_markdown(by_site(rows)) + "\n\n"
        "## Columns\n\n" + COLUMN_NOTES + "\n\n"
        "## Read this carefully\n\n" + CAVEATS + "\n"
    )


def main() -> None:
    import argparse
    import csv

    ap = argparse.ArgumentParser(description="Per-tile results table, one real pipeline run per tile.")
    ap.add_argument("--tiles", help="comma separated, default is every tile in tiles.yaml")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--noise", type=float, default=1.0)
    ap.add_argument("--csv", help="also write the per-tile rows to this file")
    ap.add_argument("--doc", help="also write the full markdown page, for example docs/TILE_RESULTS.md")
    a = ap.parse_args()
    rows = run_all(a.tiles.split(",") if a.tiles else None, a.seed, a.noise)
    print("Per tile\n" + to_markdown(rows) + "\n\nBy site\n" + to_markdown(by_site(rows)))
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(TILE_COLUMNS))
            w.writeheader()
            w.writerows(rows)
    if a.doc:
        with open(a.doc, "w", encoding="utf-8") as f:
            f.write(render_doc(rows, a.seed, a.noise))


if __name__ == "__main__":
    main()
