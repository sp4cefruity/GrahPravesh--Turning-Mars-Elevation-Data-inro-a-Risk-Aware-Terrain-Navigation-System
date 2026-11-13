"""Science step 1: candidate detection. Value only, no path cost. See `model.py` for the formulas."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, label, maximum_filter

from ..contracts import Candidate, HazardMap, TerrainGrid
from .model import ValueFields, compute_fields, interval

PEAK_WINDOW = 7  # a peak must be the maximum of this window
MIN_SEPARATION = 8.0  # cells between candidates
MAX_MISSING_TARGETS = 2  # largest no-data regions that get a low confidence target
MIN_MISSING_REGION = 12  # cells


def _peaks(values: np.ndarray, eligible: np.ndarray, count: int, taken: list) -> list[tuple[int, int]]:
    masked = np.where(eligible, values, -np.inf)
    is_peak = (masked == maximum_filter(masked, size=PEAK_WINDOW)) & eligible
    flat = np.flatnonzero(is_peak)
    order = flat[np.argsort(-masked.ravel()[flat], kind="stable")]  # ties keep scan order
    out: list[tuple[int, int]] = []
    for f in order:
        loc = tuple(int(x) for x in np.unravel_index(f, values.shape))
        if len(out) >= count:
            break
        if any(np.hypot(loc[0] - t[0], loc[1] - t[1]) < MIN_SEPARATION for t in taken + out):
            continue
        out.append(loc)
    return out


def _evidence(kind: str, loc, f: ValueFields, terrain: TerrainGrid, hazards: HazardMap, mean: float, sd: float) -> str:
    r, c = loc
    slope = float(terrain.slope_deg[r, c]) if terrain.slope_deg is not None else float("nan")
    if kind == "ice":
        sig = f"simulated ice band reads {mean:.2f} on a 0 to 1 scale (peak of its neighbourhood)"
    else:
        sig = (f"terrain class {int(hazards.terrain_class[r, c])} is distinct from its surroundings "
               f"(geology score {mean:.2f}, class share and mineral band)")
    parts = [f"{kind}: {sig}, slope {slope:.1f} deg, 90% interval {interval(mean, sd)[0]:.2f} to "
             f"{interval(mean, sd)[1]:.2f}"]
    if f.missing_frac[r, c] > 0.05:
        parts.append(f"MISSING: {100 * f.missing_frac[r, c]:.0f}% of nearby cells have no data, interval widened")
    if f.conflict[r, c] > 0.05:
        parts.append("CONFLICT: ice band reads high but the thermal band reads low here, interval widened")
    parts.append("bands are simulated")
    return "; ".join(parts) + "."


def find_candidates(terrain: TerrainGrid, hazards: HazardMap, config) -> list[Candidate]:
    f = compute_fields(terrain, hazards, config)
    shape = terrain.shape
    margin = config.drift_margin_cells(shape)
    blocked = hazards.hard_block | ~terrain.valid_mask
    dist = distance_transform_edt(~blocked) if blocked.any() else np.full(shape, np.inf)
    eligible = dist >= margin
    eligible[tuple(config.start)] = False

    n = max(int(config.n_candidates), 1)
    n_ice = (n + 1) // 2
    ice_locs = _peaks(f.ice_value, eligible, n_ice, [])
    geo_locs = _peaks(f.geo_value, eligible, n - len(ice_locs), ice_locs)
    if len(ice_locs) + len(geo_locs) < n:  # geology ran short, let ice fill the rest
        ice_locs += _peaks(f.ice_value, eligible, n - len(ice_locs) - len(geo_locs), ice_locs + geo_locs)

    found: list[tuple[float, str, tuple[int, int], float]] = []
    for kind, locs, vals in (("ice", ice_locs, f.ice_value), ("geology", geo_locs, f.geo_value)):
        for loc in locs:
            found.append((float(vals[loc]), kind, loc, float(f.sd[loc])))
    found.sort(key=lambda x: -x[0])

    out: list[Candidate] = []
    for mean, kind, loc, sd in found:
        out.append(Candidate(id=f"T{len(out) + 1}", location=loc, kind=kind, value_mean=mean,
                             value_ci=interval(mean, sd), evidence=_evidence(kind, loc, f, terrain, hazards, mean, sd)))

    # Missing regions stay in the list, with the scene prior and the widest interval.
    lab, n_lab = label(~terrain.valid_mask)
    regions = sorted(((int((lab == i).sum()), i) for i in range(1, n_lab + 1)), reverse=True)
    for size, i in regions[:MAX_MISSING_TARGETS]:
        if size < MIN_MISSING_REGION:
            continue
        rows, cols = np.nonzero(lab == i)
        cr, cc = rows.mean(), cols.mean()
        j = int(np.argmin((rows - cr) ** 2 + (cols - cc) ** 2))
        loc = (int(rows[j]), int(cols[j]))
        mean = f.prior_ice if len(out) % 2 == 0 else f.prior_geo
        kind = "ice" if len(out) % 2 == 0 else "geology"
        sd = f.prior_sd
        out.append(Candidate(
            id=f"T{len(out) + 1}", location=loc, kind=kind, value_mean=mean, value_ci=interval(mean, sd),
            evidence=(f"NO DATA at this cell ({size} cells missing in this patch). Value is the scene median "
                      f"{mean:.2f}, not a measurement, so the {kind} 90% interval is wide: "
                      f"{interval(mean, sd)[0]:.2f} to {interval(mean, sd)[1]:.2f}. Low confidence; the "
                      "planner treats missing cells as blocked, so expect no safe path.")))
    return out
