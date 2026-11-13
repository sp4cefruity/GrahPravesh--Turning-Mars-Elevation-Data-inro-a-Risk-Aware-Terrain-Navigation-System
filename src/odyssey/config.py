"""Pipeline config. One file in, one reproducible run out.

Every value here is a working assumption unless `docs/RESEARCH_NOTES.md` cites it.
Every random step reads a seed from `Seeds`. Load from JSON with `PipelineConfig.from_json`.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Seeds:
    data: int = 0  # scene, noise, missing patches
    uncertainty: int = 1  # DEM Monte Carlo
    perception: int = 2  # Random Forest
    science_candidates: int = 3
    ranking: int = 4  # ranking Monte Carlo


@dataclass(frozen=True)
class PlanningConfig:
    # soft cost weights (assumptions), applied to normalised slope, roughness, hazard_prob
    w_slope: float = 0.4
    w_roughness: float = 0.2
    w_hazard: float = 0.4
    theta_max_deg: float = 15.0  # soft-cost slope scale (assumption)
    roughness_scale: float = 0.0  # 0 means use the 99th percentile of roughness
    base_cost: float = 1.0  # cost of a unit step on perfect ground, keeps A* heuristic admissible
    alpha_bold: float = 0.0
    alpha_cautious: float = 0.95
    # inflation margin in cells: inflate_r0 + inflate_growth * distance from start (localization drift)
    inflate_r0: float = 1.0
    inflate_growth: float = 0.01
    corridor_tau: float = 0.10
    cross_check_dijkstra: bool = True
    # risk curve and baselines
    risk_curve_alphas: tuple[float, ...] = (0.0, 0.5, 0.8, 0.9, 0.95, 0.99)
    violation_p_haz: float = 0.5  # a path cell above this counts as a hazard violation (assumption)
    b0_slope_limit_deg: float = 15.0  # baseline B0 blocks cells steeper than this
    # Baseline B1, reference reproduction of Brad and Balog, Electronics 2025: cost = z / (friction + eps).
    # Friction per terrain class label, index = HazardMap.terrain_class. The paper uses hand-set values
    # from 0.1 (water) to 0.9 (concrete). These defaults are assumptions for 3 stub classes
    # (0 flat, 1 sloped, 2 steep). Labels beyond the table, or a missing class map, use the fallback.
    b1_friction_by_class: tuple[float, ...] = (0.9, 0.6, 0.3)
    b1_friction_fallback: float = 0.5  # assumption, mid range of the paper's 0.1 to 0.9
    b1_eps: float = 0.05  # the paper's eps, keeps the division finite (assumption)
    b1_z_offset_m: float = 1.0  # z = dem - min(dem) + offset, so cost stays positive (assumption)


def _perception_params(**kw):
    # Imported lazily: perception imports this module, so a top level import would be circular.
    from .perception.params import PerceptionParams
    return PerceptionParams(**kw)


@dataclass(frozen=True)
class PipelineConfig:
    seeds: Seeds = field(default_factory=Seeds)
    planning: PlanningConfig = field(default_factory=PlanningConfig)
    perception: Any = field(default_factory=_perception_params)  # a PerceptionParams
    start: tuple[int, int] = (8, 8)  # rover landing cell (row, col)
    noise_level: float = 1.0  # one dial, read by data and uncertainty
    hard_block_slope_deg: float = 25.0  # read by perception (assumption)
    hazard_delta: float = 0.9  # P_haz above this is a hard block (assumption)
    n_dem_draws: int = 50  # DEM Monte Carlo, 50 to 100
    n_ranking_draws: int = 1000  # ranking Monte Carlo
    planning_grid_size: int = 256  # documented default planning grid, 256 x 256 keeps sweeps to seconds
    n_candidates: int = 5  # target number of candidates from the science stage
    output_dir: str = "outputs"

    def drift_margin_cells(self, shape: tuple[int, int]) -> float:
        """Largest blocked-cell inflation margin the planner uses on a grid of this shape, in cells.

        The margin is inflate_r0 + inflate_growth * distance from start, so it is largest at the
        farthest corner. Candidate detection should skip cells closer than this to a hard block.
        """
        p = self.planning
        far = max(math.hypot(r - self.start[0], c - self.start[1])
                  for r in (0, shape[0] - 1) for c in (0, shape[1] - 1))
        return p.inflate_r0 + p.inflate_growth * far

    # ---- serialisation
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def config_hash(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, default=list)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineConfig":
        d = dict(d)
        seeds = Seeds(**d.pop("seeds", {}))
        planning_d = dict(d.pop("planning", {}))
        for key in ("risk_curve_alphas", "b1_friction_by_class"):
            if key in planning_d:
                planning_d[key] = tuple(planning_d[key])
        planning = PlanningConfig(**planning_d)
        perception = _perception_params(**d.pop("perception", {}))
        if "start" in d:
            d["start"] = tuple(d["start"])
        return cls(seeds=seeds, planning=planning, perception=perception, **d)

    @classmethod
    def from_json(cls, path: str | Path) -> "PipelineConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
