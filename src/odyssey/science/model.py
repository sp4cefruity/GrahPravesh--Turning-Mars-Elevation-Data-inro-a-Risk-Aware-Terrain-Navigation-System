"""Value model and noise model for science targets.

ASSUMPTIONS, NOT SCIENCE. All bands are simulated. Nothing here is a claim about real ice.

Value formulas (all on a 0 to 1 scale)
- Ice value  = robust scale of the simulated ice band (2nd percentile to the maximum of valid cells).
- Geology value = distinctness * slope_free.
    distinctness = mean of (a) class rarity, sum_k p_k * (1 - area share of class k), using the
                   HazardMap class probabilities, and (b) the robust scaled mineral band when present.
    slope_free   = clip(1 - slope_deg / hard_block_slope_deg, 0, 1), so gentle ground scores high.

Noise model (per cell standard deviation of value, terms added in quadrature)
- sensor      : SENSOR_SD * noise_level. Additive Gaussian, because the simulated sensor noise is
                Gaussian and independent per band, and the sum of a few small independent errors is
                close to Gaussian.
- classifier  : CLASS_SD_GAIN * epistemic_std from the hazard map (disagreement of the terrain model).
- missing     : MISSING_SD_GAIN * share of no-data cells in a 7 by 7 window. A candidate next to a gap
                is read from interpolated neighbours, so it is less certain.
- conflict    : CONFLICT_SD_GAIN * conflict strength, where the ice band reads high while the thermal
                proxy band reads low (convention from specs/05-data.md: high thermal proxy means
                ice-consistent). Conflict widens the interval, it does not move the mean.
- no data at the cell: mean is the scene prior (median of valid cell values) and sd is the spread of
                the scene values, floored at NO_DATA_SD_FLOOR. This is the widest interval we report.

Intervals are 90 percent (mean +/- Z90 * sd). The gains are working assumptions, set once here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter

Z90 = 1.6449  # two sided 90 percent interval
SENSOR_SD = 0.05
CLASS_SD_GAIN = 0.5
MISSING_SD_GAIN = 0.30
CONFLICT_SD_GAIN = 0.25
NO_DATA_SD_FLOOR = 0.25
WINDOW = 7
ICE_BAND = "ice_simulated"
MINERAL_BAND = "mineral_simulated"


@dataclass
class ValueFields:
    ice_value: np.ndarray
    geo_value: np.ndarray
    sd: np.ndarray  # per cell value sd, with all noise terms
    missing_frac: np.ndarray
    conflict: np.ndarray  # 0 to 1
    has_thermal: bool
    prior_ice: float
    prior_geo: float
    prior_sd: float
    sd_parts: dict[str, np.ndarray]


def _robust_scale(x: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if not valid.any():
        return np.zeros_like(x, dtype=float)
    lo, hi = np.percentile(x[valid], 2), x[valid].max()  # no top clip, so peaks stay distinct
    if hi - lo < 1e-12:
        return np.zeros_like(x, dtype=float)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def _fill(x: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = np.nan_to_num(x.astype(float), nan=0.0)
    out[~valid] = np.median(out[valid]) if valid.any() else 0.0
    return out


def find_thermal_band(bands: dict[str, np.ndarray]) -> Optional[np.ndarray]:
    for name, arr in bands.items():
        if "thermal" in name.lower():
            return arr
    return None


def compute_fields(terrain, hazards, config) -> ValueFields:
    valid = terrain.valid_mask & np.ones(terrain.shape, bool)
    shape = terrain.shape
    ice_raw = terrain.bands.get(ICE_BAND)
    ice = _robust_scale(_fill(ice_raw, valid & np.isfinite(ice_raw)), valid) if ice_raw is not None \
        else np.zeros(shape)

    probs = hazards.class_probs
    labels = hazards.terrain_class
    k = probs.shape[0]
    share = np.array([(labels[valid] == i).mean() if valid.any() else 0.0 for i in range(k)])
    rarity = np.tensordot(1.0 - share, probs, axes=(0, 0))
    rarity = np.clip(rarity, 0.0, 1.0)
    mineral_raw = terrain.bands.get(MINERAL_BAND)
    if mineral_raw is not None:
        mineral = _robust_scale(_fill(mineral_raw, valid & np.isfinite(mineral_raw)), valid)
        distinct = 0.5 * (rarity + mineral)
    else:
        distinct = rarity
    slope = terrain.slope_deg if terrain.slope_deg is not None else np.zeros(shape)
    slope_free = np.clip(1.0 - slope / config.hard_block_slope_deg, 0.0, 1.0)
    geo = distinct * slope_free

    miss = uniform_filter((~valid).astype(float), size=WINDOW, mode="nearest")

    thermal_raw = find_thermal_band(terrain.bands)
    has_thermal = thermal_raw is not None
    if has_thermal:
        thermal = _robust_scale(_fill(thermal_raw, valid & np.isfinite(thermal_raw)), valid)
        strength = np.clip(np.minimum(ice, 1.0 - thermal) - 0.5, 0.0, None) * 2.0
        conflict = np.clip(gaussian_filter(strength, 1.0), 0.0, 1.0)
        conflict = np.maximum(conflict, strength * (strength > 0.3))
    else:
        conflict = np.zeros(shape)

    parts = {
        "sensor": np.full(shape, SENSOR_SD * config.noise_level),
        "classifier": CLASS_SD_GAIN * np.asarray(hazards.epistemic_std, dtype=float),
        "missing": MISSING_SD_GAIN * miss,
        "conflict": CONFLICT_SD_GAIN * conflict,
    }
    sd = np.sqrt(sum(p ** 2 for p in parts.values()))

    prior_ice = float(np.median(ice[valid])) if valid.any() else 0.0
    prior_geo = float(np.median(geo[valid])) if valid.any() else 0.0
    spread = float(np.std(np.concatenate([ice[valid], geo[valid]]))) if valid.any() else 0.0
    prior_sd = max(spread, NO_DATA_SD_FLOOR)
    return ValueFields(ice, geo, sd, miss, conflict, has_thermal, prior_ice, prior_geo, prior_sd, parts)


def interval(mean: float, sd: float) -> tuple[float, float]:
    """90 percent interval. The lower end is floored at 0 (value cannot be negative)."""
    return (max(0.0, mean - Z90 * sd), mean + Z90 * sd)


def sd_from_interval(mean: float, ci: tuple[float, float]) -> float:
    """Recover sd from the upper side, which is never clipped."""
    return max((ci[1] - mean) / Z90, 0.0)
