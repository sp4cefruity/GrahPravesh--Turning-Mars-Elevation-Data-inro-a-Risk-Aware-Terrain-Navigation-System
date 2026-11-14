"""Check the science stage against the answer key (spec 03 and spec 05). Never used by the pipeline.

The scene generator keeps the signals as they really are (`SceneTruth.clean_bands`: no sensor noise, no
missing patches, no conflict fault). The truth value of a target is what `model.compute_fields` gives when it
reads those clean bands, so the only difference from the real run is the sensor trouble we injected.

Three groups of metrics, all plain numbers (NaN when there is nothing to measure):
- value:  mean absolute error, and how often the truth falls inside the stated 90 percent interval.
- rank:   Spearman between estimated and true score, how often the true rank falls inside the stated
          rank interval, and whether the truly best target is inside the estimated top 3.
- recall: how many planted targets have a candidate of the same kind close by, and the reverse.

True score is true value divided by the same access cost the ranking used, with nominal weights of 1.
Targets in a missing patch hold only the scene prior, so they are left out of the value metrics.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from ..data.scene import block_mean
from ..tables import mean as _mean, to_markdown  # noqa: F401  (to_markdown is re-exported)
from .model import compute_fields


def _rank_desc(x) -> np.ndarray:
    """Rank 1 is the largest. Ties share the best rank."""
    x = np.asarray(x, dtype=float)
    return np.array([1 + int((x > v).sum()) for v in x])


def value_metrics(targets, truth_values) -> dict:
    keep = [i for i, t in enumerate(targets) if "NO DATA" not in t.evidence and np.isfinite(truth_values[i])]
    return {
        "n_measured": len(keep),
        "value_mae": _mean(abs(targets[i].value_mean - truth_values[i]) for i in keep),
        "value_coverage": _mean(targets[i].value_ci[0] <= truth_values[i] <= targets[i].value_ci[1] for i in keep),
    }


def rank_metrics(targets, truth_values) -> dict:
    idx = [i for i, t in enumerate(targets) if np.isfinite(t.path_cost) and np.isfinite(truth_values[i])]
    out = {"n_reachable": len(idx), "rank_spearman": float("nan"),
           "rank_interval_coverage": float("nan"), "truth_best_in_top3": float("nan")}
    if not idx:
        return out
    est = np.array([targets[i].score for i in idx])
    tru = np.array([truth_values[i] / targets[i].path_cost for i in idx])
    true_rank = _rank_desc(tru)
    out["rank_interval_coverage"] = _mean(targets[i].rank_interval[0] <= r <= targets[i].rank_interval[1]
                                          for i, r in zip(idx, true_rank))
    est_rank = _rank_desc(est)
    out["truth_best_in_top3"] = float(est_rank[int(np.argmax(tru))] <= 3)
    if len(idx) >= 3 and np.ptp(est_rank) > 0 and np.ptp(true_rank) > 0:  # Spearman is Pearson on ranks
        out["rank_spearman"] = float(np.corrcoef(est_rank, true_rank)[0, 1])
    return out


def recall_metrics(candidates, planted, radius: float = 8.0) -> dict:
    """A candidate finds a planted target if it has the same kind and is within `radius` cells."""
    def near(c, p) -> bool:
        return c.kind == p["kind"] and np.hypot(c.location[0] - p["row"], c.location[1] - p["col"]) <= radius

    measured = [c for c in candidates if "NO DATA" not in c.evidence]
    return {
        "planted_recall": _mean(any(near(c, p) for c in measured) for p in planted),
        "candidate_precision": _mean(any(near(c, p) for p in planted) for c in measured),
    }


def truth_values(res, truth, config=None) -> list[float]:
    """True value at each target's cell, from the clean bands and the same formulas as the science stage."""
    cfg = config or res.config
    source_valid = ~np.isnan(block_mean(truth.dem_truth))  # cells the source DEM really has, gaps included
    clean = dataclasses.replace(res.terrain, bands=truth.clean_bands, valid_mask=source_valid)
    f = compute_fields(clean, res.hazards, cfg)
    return [float((f.ice_value if t.kind == "ice" else f.geo_value)[t.location]) for t in res.targets]


def evaluate(res, truth, config=None, radius: float = 8.0) -> dict:
    """All metrics for one finished pipeline run. `res` needs terrain, hazards, candidates, targets, config."""
    tv = truth_values(res, truth, config)
    return {"n_targets": len(res.targets), **value_metrics(res.targets, tv), **rank_metrics(res.targets, tv),
            **recall_metrics(res.candidates, truth.targets, radius)}


# ---------------------------------------------------------------- running it over tiles, seeds and noise

METRICS = ("n_targets", "n_reachable", "value_mae", "value_coverage", "rank_spearman",
           "rank_interval_coverage", "truth_best_in_top3", "planted_recall", "candidate_precision")


def run_one(tile_id: str, seed: int = 0, noise_level: float = 1.0, n_candidates: int = 5) -> dict:
    """Build one scene, run the real pipeline on it, score it. A failed run comes back with `error` set."""
    from ..data.tile_report import run_scene  # imported here so importing this module never pulls in the pipeline

    row = {"tile": tile_id, "seed": seed, "noise": noise_level, "n_candidates": n_candidates}
    try:
        res, truth = run_scene(tile_id, seed, noise_level, n_candidates)
    except Exception as e:  # one bad tile must not abort a long study
        return {**row, "error": f"{type(e).__name__}: {e}"}
    if not res.complete:
        return {**row, "error": f"{res.error.stage}: {res.error.reason}"}
    return {**row, "error": "", **evaluate(res, truth)}


def summarize(rows, by=("tile",)) -> list[dict]:
    """Mean of each metric per group, ignoring NaN. Failed runs are counted, never averaged in."""
    groups: dict = {}
    for r in rows:
        groups.setdefault(tuple(r[k] for k in by), []).append(r)
    table = []
    for key, rs in sorted(groups.items()):
        ok = [r for r in rs if not r.get("error")]
        line = {**dict(zip(by, key)), "runs": len(rs), "failed": len(rs) - len(ok)}
        for m in METRICS:
            line[m] = _mean(r[m] for r in ok if np.isfinite(r[m]))
        table.append(line)
    return table


def write_csv(rows, path) -> None:
    """Every run in one file. Columns are whatever the rows carry, so a new metric can never be dropped or crash the
    write. Failed runs have no metrics, so those cells are left empty."""
    import csv

    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(dict.fromkeys(k for r in rows for k in r)), restval="")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Score the science stage against the planted answer key.")
    ap.add_argument("--tiles", default="T1", help="comma separated, for example T1,T2,T3,T4,T5")
    ap.add_argument("--seeds", default="0", help="comma separated scene seeds")
    ap.add_argument("--noise", default="1.0", help="comma separated noise levels")
    ap.add_argument("--candidates", default="5", help="comma separated n_candidates values")
    ap.add_argument("--csv", help="also write every run to this file")
    a = ap.parse_args()
    rows = []
    for tile in a.tiles.split(","):
        for seed in map(int, a.seeds.split(",")):
            for noise in map(float, a.noise.split(",")):
                for k in map(int, a.candidates.split(",")):
                    rows.append(run_one(tile, seed, noise, k))
                    print(f"done {tile} seed {seed} noise {noise} candidates {k}", flush=True)
    for by in (("tile",), ("noise",), ("n_candidates",)):
        print(f"\nBy {by[0]}\n" + to_markdown(summarize(rows, by)))
    if a.csv:
        write_csv(rows, a.csv)


if __name__ == "__main__":
    main()
