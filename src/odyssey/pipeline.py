"""Pipeline orchestration (owner: Udit). One config in, one PipelineResult out.

Order is fixed by specs/00-system.md:
  1 data, 2 perception, 3 uncertainty, 4 cost map, 5 science candidates,
  6 planning, 7 science ranking, then 8 planning extras (baselines, risk curve)
  for the default goal, which is only known after step 7.

How other roles plug in
  Each stage is looked up by module and function name (see STAGES) when it runs. A missing
  module or function stops the run with a StageFailure for that stage. Nobody edits this file
  to plug in.

Failure rule (spec 00)
  If a stage raises or breaks its contract, the run stops, `result.error` holds the stage
  name and reason, and `result.complete` is False. The dashboard must check `complete`.

Run:  python -m odyssey.pipeline [--config path.json] [--force]
"""

from __future__ import annotations

import argparse
import importlib
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from . import contracts as C
from . import planning
from .config import PipelineConfig


@dataclass(frozen=True)
class StageSpec:
    name: str
    owner: str
    module: str  # module that should expose the real function
    func: str  # expected function name
    signature: str  # documentation only


STAGES: dict[str, StageSpec] = {s.name: s for s in [
    StageSpec("data", "Saptarshi", "odyssey.data", "load_terrain",
              "load_terrain(config) -> TerrainGrid (raw: dem, bands, valid_mask, cell_size_m)"),
    StageSpec("perception", "Disha", "odyssey.perception", "compute_hazards",
              "compute_hazards(terrain, config) -> (TerrainGrid full, HazardMap with slope_std_deg None)"),
    StageSpec("uncertainty", "Disha", "odyssey.uncertainty", "fill_slope_uncertainty",
              "fill_slope_uncertainty(terrain, hazards, config) -> HazardMap with slope_std_deg filled"),
    StageSpec("cost_map", "Udit", "odyssey.planning", "build_cost_map",
              "build_cost_map(terrain, hazards, config) -> CostMap"),
    StageSpec("science_candidates", "Saptarshi", "odyssey.science", "find_candidates",
              "find_candidates(terrain, hazards, config) -> list[Candidate], value only"),
    StageSpec("planning", "Udit", "odyssey.planning", "plan_paths",
              "plan_paths(terrain, hazards, cost_map, candidates, config) -> {candidate_id: {mode: PathResult}}"),
    StageSpec("science_ranking", "Saptarshi", "odyssey.science", "rank_targets",
              "rank_targets(candidates, paths, terrain, hazards, config) -> list[ScienceTarget]"),
    StageSpec("planning_extras", "Udit", "odyssey.planning", "plan_extras",
              "plan_extras(terrain, hazards, cost_map, goal, config) -> PlanExtras"),
]}


def resolve_stage(spec: StageSpec) -> Callable[..., Any]:
    """Find the stage function by module and name. A missing module or function raises, and
    `run_pipeline` records that as a failure of the stage. Nothing is hidden or replaced."""
    return getattr(importlib.import_module(spec.module), spec.func)


class _Stop(Exception):
    pass


def run_pipeline(config: Optional[PipelineConfig] = None,
                 overrides: Optional[dict[str, Callable[..., Any]]] = None) -> C.PipelineResult:
    """Run all stages. `overrides` maps stage name to a function, used by tests."""
    config = config or PipelineConfig()
    overrides = overrides or {}
    res = C.PipelineResult(config=config, start=tuple(config.start))

    def call(name: str, *args: Any) -> Any:
        t0 = time.perf_counter()
        try:
            fn = overrides[name] if name in overrides else resolve_stage(STAGES[name])
            return fn(*args, config)
        except Exception as e:  # recorded, then the run stops
            res.error = C.StageFailure(name, f"{type(e).__name__}: {e}")
            raise _Stop() from e
        finally:
            res.timings_s[name] = time.perf_counter() - t0

    def check(name: str, fn: Callable[..., None], *args: Any, **kw: Any) -> None:
        try:
            fn(*args, **kw)
        except C.ContractError as e:
            res.error = C.StageFailure(name, f"ContractError: {e}")
            raise _Stop() from e

    def fail(name: str, reason: str) -> None:
        res.error = C.StageFailure(name, reason)
        raise _Stop()

    try:
        # 1 data
        res.terrain = call("data")
        check("data", C.validate_terrain, res.terrain, full=False)
        shape = res.terrain.shape
        start = res.start
        if not (0 <= start[0] < shape[0] and 0 <= start[1] < shape[1]):
            fail("data", f"start cell {start} is outside the {shape} grid")

        # 2 perception
        res.terrain, res.hazards = call("perception", res.terrain)
        check("perception", C.validate_terrain, res.terrain, full=True)
        check("perception", C.validate_hazards, res.hazards, shape, need_slope_std=False)

        # 3 uncertainty
        res.hazards = call("uncertainty", res.terrain, res.hazards)
        check("uncertainty", C.validate_hazards, res.hazards, shape, need_slope_std=True)

        # 4 cost map
        res.cost_map = call("cost_map", res.terrain, res.hazards)
        if res.cost_map.blocked[start]:
            fail("cost_map", f"start cell {start} is blocked (hard block or missing data)")

        # 5 science candidates
        res.candidates = call("science_candidates", res.terrain, res.hazards)
        check("science_candidates", C.validate_candidates, res.candidates, shape)

        # 6 planning
        # Full resolution cost map, terrain and hazards stay in the result and feed the safety check
        # below. When the grid exceeds planning_grid_size, plan_paths and plan_extras search a
        # block-reduced copy and return full resolution cells (see specs/02-planning.md).
        f = planning.coarse_factor(shape, config)
        if f > 1:
            n_c = (-(-shape[0] // f), -(-shape[1] // f))
            res.notes.append(f"Planning searched a {n_c[0]} by {n_c[1]} grid (block size {f}) and refined "
                             f"routes to the full {shape[0]} by {shape[1]} grid. Safety check ran at full resolution.")
        res.paths = call("planning", res.terrain, res.hazards, res.cost_map, res.candidates)
        _check_paths(res, fail)

        # 7 science ranking
        res.targets = call("science_ranking", res.candidates, res.paths, res.terrain, res.hazards)
        check("science_ranking", C.validate_targets, res.targets, {c.id for c in res.candidates})

        # default target: best ranked one that has a safe path in the default (cautious) mode
        for t in res.targets:
            if res.paths[t.id]["cautious"].safe:
                res.default_target_id = t.id
                break
        if res.default_target_id is None:
            res.notes.append("No safe path to any candidate. Nothing is shown as a route.")
        else:
            goal = next(t.location for t in res.targets if t.id == res.default_target_id)
            # 8 extras for the default goal
            extras = call("planning_extras", res.terrain, res.hazards, res.cost_map, goal)
            res.risk_curve, res.baseline_paths = extras.risk_curve, extras.baseline_paths
        unreachable = [c for c, m in res.paths.items() if not m["cautious"].safe]
        if unreachable:
            res.notes.append(f"No safe path (cautious mode) to: {', '.join(sorted(unreachable))}")
    except _Stop:
        pass
    return res


def _check_paths(res: C.PipelineResult, fail: Callable[[str, str], None]) -> None:
    """Independent final safety check. Never trusts the planner's own `safe` flag."""
    ids = {c.id for c in res.candidates}
    if set(res.paths) != ids:
        fail("planning", f"paths cover {sorted(res.paths)}, candidates are {sorted(ids)}")
    for cid, by_mode in res.paths.items():
        if set(by_mode) != set(C.MODES):
            fail("planning", f"candidate {cid} needs modes {C.MODES}, got {sorted(by_mode)}")
        for mode, pr in by_mode.items():
            if pr.cells:
                try:
                    planning.verify_path(pr.cells, res.cost_map.blocked, res.terrain.slope_deg, res.cost_map.p_haz)
                except planning.SafetyViolation as e:
                    fail("safety_check", f"path to {cid} ({mode}) crosses blocked cells: {e}")
                if not pr.safe:
                    fail("safety_check", f"path to {cid} ({mode}) has cells but safe is False")
            elif pr.safe:
                fail("safety_check", f"path to {cid} ({mode}) is empty but marked safe")


# ---------------------------------------------------------------- serialisation


def result_path(config: PipelineConfig) -> Path:
    return Path(config.output_dir) / f"result_{config.config_hash()}.pkl"


def save_result(res: C.PipelineResult, path: Optional[Path] = None) -> Path:
    path = path or result_path(res.config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(res, f, protocol=pickle.HIGHEST_PROTOCOL)
    return path


def load_result(path: Path) -> C.PipelineResult:
    """Only load files this pipeline wrote. Pickle is not safe for untrusted input."""
    with open(path, "rb") as f:
        return pickle.load(f)


def load_or_run(config: Optional[PipelineConfig] = None, force: bool = False) -> C.PipelineResult:
    """What the dashboard calls. Runs once per config, then loads from disk."""
    config = config or PipelineConfig()
    path = result_path(config)
    if path.exists() and not force:
        return load_result(path)
    res = run_pipeline(config)
    save_result(res, path)
    return res


def summary(res: C.PipelineResult) -> str:
    lines = [f"config {res.config.config_hash()}  complete={res.complete}"]
    if res.error:
        lines.append(f"FAILED at stage '{res.error.stage}': {res.error.reason}")
    for n, t in res.timings_s.items():
        lines.append(f"  {n:20s} {t:7.2f}s")
    for t in res.targets:
        lines.append(f"  {t.id} {t.kind:8s} score {t.score:.3f} rank {t.rank_interval} cost {t.path_cost:.1f}")
    lines.append(f"default target: {res.default_target_id}")
    lines.extend(f"note: {n}" for n in res.notes)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Odyssey pipeline and save the result.")
    ap.add_argument("--config", help="JSON config file (defaults are used if omitted)")
    ap.add_argument("--force", action="store_true", help="recompute even if a saved result exists")
    ap.add_argument("--dump-default-config", metavar="PATH", help="write the default config and exit")
    args = ap.parse_args()
    if args.dump_default_config:
        PipelineConfig().to_json(args.dump_default_config)
        return
    config = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    res = load_or_run(config, force=args.force)
    print(summary(res))
    print("saved:", result_path(config))


if __name__ == "__main__":
    main()
