"""Shared data contracts between pipeline stages.

Source of truth for the field lists is `docs/ARCHITECTURE.md` (section Contracts).
This file turns them into dataclasses plus light validators, so a stage that
returns the wrong shape fails with a clear message and the stage name.

Conventions
- All grids are NumPy arrays of shape (H, W), same orientation, same cell size.
- A location is (row, col), row 0 at the top of the array.
- Fields marked "additive" are not in the frozen contract list. They have defaults,
  so nobody has to fill them. They are listed in the spec gap report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

Cell = tuple[int, int]

MODES = ("bold", "cautious")


class ContractError(ValueError):
    """A stage returned data that does not match the contract."""


# ---------------------------------------------------------------- terrain


@dataclass
class TerrainGrid:
    """Raw part comes from data. Perception fills slope, roughness, aspect."""

    dem: np.ndarray
    valid_mask: np.ndarray  # False where data is missing
    cell_size_m: float
    bands: dict[str, np.ndarray] = field(default_factory=dict)
    simulated_layers: list[str] = field(default_factory=list)
    slope_deg: Optional[np.ndarray] = None
    roughness: Optional[np.ndarray] = None
    aspect: Optional[np.ndarray] = None
    source: str = ""  # additive: where the DEM came from, and "synthetic" if it is a fallback

    @property
    def shape(self) -> tuple[int, int]:
        return self.dem.shape


# ---------------------------------------------------------------- hazards


@dataclass
class HazardMap:
    """Owned by Disha. `slope_std_deg` stays None until the uncertainty stage runs."""

    hazard_prob: np.ndarray  # 0 to 1
    terrain_class: np.ndarray  # int labels
    class_probs: np.ndarray  # (K, H, W)
    epistemic_std: np.ndarray
    hard_block: np.ndarray  # bool, steep or crater rim or P_haz > delta
    evidence: dict[int, str] = field(default_factory=dict)  # legend: evidence code -> rule or model note
    slope_std_deg: Optional[np.ndarray] = None
    evidence_code: Optional[np.ndarray] = None  # (H, W) int, which rule or model fired per cell, keys into `evidence`


# ---------------------------------------------------------------- planning


@dataclass
class CostMap:
    cost_mean: np.ndarray
    cost_std: np.ndarray
    p_haz: np.ndarray
    blocked: np.ndarray  # hard_block | ~valid_mask, NOT inflated (planner inflates)


@dataclass
class SegmentCost:
    """Cost breakdown of one step of a path, for the dashboard trace. Additive."""

    from_cell: Cell
    to_cell: Cell
    length_cells: float
    base: float
    mean: float
    risk_term: float  # std * phi(z_alpha) / (1 - alpha)
    edge_cost: float
    slope_deg: float
    p_haz: float


@dataclass
class PathResult:
    cells: list[Cell]  # empty when there is no safe path
    total_cost: float  # sum of CVaR edge costs at this alpha, inf when no safe path
    risk_score: float  # sum of p_haz over path cells, inf when no safe path
    max_slope_on_path: float
    safe: bool  # from verification on the true (uninflated) blocked mask
    planner: str  # "astar" or "dijkstra"
    mode: str  # "bold" or "cautious"
    alpha: float
    corridor_mask: Optional[np.ndarray]  # bool (H, W)
    min_feasible_risk: Optional[float]  # set when no safe path exists
    baseline: Optional[str]  # "b0", "b1" or None
    # additive fields
    candidate_id: Optional[str] = None
    no_safe_path_reason: Optional[str] = None
    segments: list[SegmentCost] = field(default_factory=list)
    nodes_expanded: int = 0
    dijkstra_cost: Optional[float] = None  # optimality cross-check
    dijkstra_nodes_expanded: Optional[int] = None


@dataclass
class RiskCurvePoint:
    alpha: float
    path_length: float  # in cells (diagonals count sqrt(2)), inf when no safe path
    hazard_violation_rate: float  # share of path cells with p_haz above config threshold


@dataclass
class PlanExtras:
    """Things that need the default goal, so they run after science ranking."""

    risk_curve: list[RiskCurvePoint]
    baseline_paths: dict[str, PathResult]  # "b0", "b1"


# ---------------------------------------------------------------- science


@dataclass
class Candidate:
    """Science step 1 output. Value only, no path cost. Not in the frozen contract list."""

    id: str
    location: Cell
    kind: str  # "ice" or "geology"
    value_mean: float
    value_ci: tuple[float, float]
    evidence: str = ""


@dataclass
class ScienceTarget:
    id: str
    location: Cell
    value_mean: float
    value_ci: tuple[float, float]
    path_cost: float  # CVaR access cost used for the score, inf when unreachable
    score: float
    score_ci: tuple[float, float]
    rank_interval: tuple[int, int]  # 1 is best
    p_top3: float
    evidence: str
    kind: str


# ---------------------------------------------------------------- result


@dataclass
class StageFailure:
    stage: str
    reason: str


@dataclass
class PipelineResult:
    config: Any  # PipelineConfig, kept untyped here to avoid an import cycle
    terrain: Optional[TerrainGrid] = None
    hazards: Optional[HazardMap] = None
    cost_map: Optional[CostMap] = None
    candidates: list[Candidate] = field(default_factory=list)
    # paths[candidate_id][mode] -> PathResult
    paths: dict[str, dict[str, PathResult]] = field(default_factory=dict)
    targets: list[ScienceTarget] = field(default_factory=list)  # sorted best first
    default_target_id: Optional[str] = None  # top ranked target with a safe path
    risk_curve: list[RiskCurvePoint] = field(default_factory=list)
    baseline_paths: dict[str, PathResult] = field(default_factory=dict)
    start: Optional[Cell] = None
    stub_stages: list[str] = field(default_factory=list)  # stages that ran as stubs
    timings_s: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # for example "no safe path to any target"
    error: Optional[StageFailure] = None

    @property
    def complete(self) -> bool:
        """The dashboard must only show output when this is True."""
        return self.error is None


# ---------------------------------------------------------------- validators


def _grid(name: str, arr: Any, shape: tuple[int, int], dtype_kind: Optional[str] = None) -> None:
    if not isinstance(arr, np.ndarray):
        raise ContractError(f"{name} must be a numpy array, got {type(arr).__name__}")
    if arr.shape != shape:
        raise ContractError(f"{name} has shape {arr.shape}, expected {shape}")
    if dtype_kind and arr.dtype.kind != dtype_kind:
        raise ContractError(f"{name} has dtype {arr.dtype}, expected kind '{dtype_kind}'")


def validate_terrain(t: Any, *, full: bool) -> None:
    """full=False checks the raw data output. full=True also needs slope, roughness, aspect."""
    if not isinstance(t, TerrainGrid):
        raise ContractError(f"expected TerrainGrid, got {type(t).__name__}")
    if t.dem.ndim != 2:
        raise ContractError(f"dem must be 2D, got {t.dem.ndim}D")
    shape = t.dem.shape
    _grid("valid_mask", t.valid_mask, shape, "b")
    if not t.cell_size_m > 0:
        raise ContractError("cell_size_m must be positive")
    for name, band in t.bands.items():
        _grid(f"bands[{name}]", band, shape)
    if full:
        for name in ("slope_deg", "roughness", "aspect"):
            _grid(name, getattr(t, name), shape)


def validate_hazards(h: Any, shape: tuple[int, int], *, need_slope_std: bool) -> None:
    if not isinstance(h, HazardMap):
        raise ContractError(f"expected HazardMap, got {type(h).__name__}")
    _grid("hazard_prob", h.hazard_prob, shape)
    _grid("terrain_class", h.terrain_class, shape, "i")
    _grid("epistemic_std", h.epistemic_std, shape)
    _grid("hard_block", h.hard_block, shape, "b")
    if h.evidence_code is not None:
        _grid("evidence_code", h.evidence_code, shape, "i")
        missing = set(np.unique(h.evidence_code).tolist()) - set(h.evidence)
        if missing:
            raise ContractError(f"evidence_code values {sorted(missing)} have no legend entry in evidence")
    if not (isinstance(h.class_probs, np.ndarray) and h.class_probs.ndim == 3 and h.class_probs.shape[1:] == shape):
        raise ContractError("class_probs must have shape (K, H, W)")
    if h.hazard_prob.min() < 0 or h.hazard_prob.max() > 1:
        raise ContractError("hazard_prob must be within 0 to 1")
    if need_slope_std:
        if h.slope_std_deg is None:
            raise ContractError("slope_std_deg is None, the uncertainty stage must fill it")
        _grid("slope_std_deg", h.slope_std_deg, shape)


def validate_candidates(cands: Any, shape: tuple[int, int]) -> None:
    if not isinstance(cands, list):
        raise ContractError("candidates must be a list")
    seen: set[str] = set()
    for c in cands:
        if not isinstance(c, Candidate):
            raise ContractError(f"expected Candidate, got {type(c).__name__}")
        if c.id in seen:
            raise ContractError(f"duplicate candidate id {c.id}")
        seen.add(c.id)
        r, col = c.location
        if not (0 <= r < shape[0] and 0 <= col < shape[1]):
            raise ContractError(f"candidate {c.id} location {c.location} is outside the grid")
        if c.kind not in ("ice", "geology"):
            raise ContractError(f"candidate {c.id} kind must be 'ice' or 'geology', got {c.kind!r}")


def validate_targets(targets: Any, candidate_ids: set[str]) -> None:
    if not isinstance(targets, list):
        raise ContractError("targets must be a list")
    for t in targets:
        if not isinstance(t, ScienceTarget):
            raise ContractError(f"expected ScienceTarget, got {type(t).__name__}")
        if t.id not in candidate_ids:
            raise ContractError(f"target {t.id} is not a known candidate")
        if not t.evidence.strip():
            raise ContractError(f"target {t.id} has an empty evidence string")
    ids = [t.id for t in targets]
    if len(set(ids)) != len(ids):
        raise ContractError("duplicate target ids")
