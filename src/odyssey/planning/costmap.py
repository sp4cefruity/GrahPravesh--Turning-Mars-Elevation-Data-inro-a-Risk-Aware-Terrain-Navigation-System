"""Cost map and blocked mask.

cost_mean is a weighted sum of normalised slope, roughness and hazard_prob.
cost_std is first order propagation of slope_std_deg and epistemic_std through the same weights.
Weights are labelled assumptions (see PlanningConfig).

Hard blocks are separate from soft cost. `blocked` comes only from the hazard map and the
valid mask. No weight appears in it, so a weight change cannot unblock a cell.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt

from ..config import PipelineConfig
from ..contracts import CostMap, HazardMap, TerrainGrid


def blocked_mask(terrain: TerrainGrid, hazards: HazardMap) -> np.ndarray:
    """True (uninflated) blocked mask: hard_block OR ~valid_mask."""
    return hazards.hard_block.astype(bool) | ~terrain.valid_mask.astype(bool)


def build_cost_map(terrain: TerrainGrid, hazards: HazardMap, config: PipelineConfig) -> CostMap:
    p = config.planning
    slope = np.nan_to_num(terrain.slope_deg, nan=0.0)
    rough = np.nan_to_num(terrain.roughness, nan=0.0)
    rough_scale = p.roughness_scale or float(np.percentile(rough[terrain.valid_mask], 99)) or 1.0

    slope_n = np.clip(slope / p.theta_max_deg, 0.0, 1.0)
    rough_n = np.clip(rough / rough_scale, 0.0, 1.0)
    haz = np.clip(hazards.hazard_prob, 0.0, 1.0)

    cost_mean = p.w_slope * slope_n + p.w_roughness * rough_n + p.w_hazard * haz

    slope_std_n = np.nan_to_num(hazards.slope_std_deg, nan=0.0) / p.theta_max_deg
    epi = np.nan_to_num(hazards.epistemic_std, nan=0.0)
    # first order, ignores the clip derivative (conservative where the clip is active)
    cost_std = np.sqrt((p.w_slope * slope_std_n) ** 2 + (p.w_hazard * epi) ** 2)

    return CostMap(
        cost_mean=cost_mean,
        cost_std=cost_std,
        p_haz=haz,
        blocked=blocked_mask(terrain, hazards),
    )


def inflate_blocked(blocked: np.ndarray, start: tuple[int, int], r0: float, growth: float) -> np.ndarray:
    """Grow blocked cells by a margin that increases with distance from the start.

    Models localization drift: the further the rover has driven, the less it trusts its position.
    The start cell is never inflated shut. Truly blocked cells stay blocked.
    """
    if not blocked.any():
        return blocked.copy()
    dist_to_block = distance_transform_edt(~blocked)
    rr, cc = np.indices(blocked.shape)
    dist_from_start = np.hypot(rr - start[0], cc - start[1])
    margin = r0 + growth * dist_from_start
    inflated = blocked | (dist_to_block <= margin)
    if not blocked[start]:
        inflated[start] = False
    return inflated
