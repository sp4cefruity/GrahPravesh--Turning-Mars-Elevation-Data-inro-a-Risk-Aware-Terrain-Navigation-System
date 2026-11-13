"""Stub stages for data, perception, uncertainty and science.

They return dummy output in the contract shape so the pipeline runs end to end before the
real stages land. Everything here is SIMULATED and meaningless as science. Each real stage
replaces its stub by exposing the function named in `pipeline.STAGES`, no pipeline edit needed.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter

from .config import PipelineConfig
from .contracts import Candidate, HazardMap, PathResult, ScienceTarget, TerrainGrid

STUB_NOTE = "STUB: dummy output in contract shape, not real data"


def stub_load_terrain(config: PipelineConfig) -> TerrainGrid:
    n = config.stub_grid_size
    rng = np.random.default_rng(config.seeds.data)
    relief = gaussian_filter(rng.standard_normal((n, n)), n / 8)
    relief = relief / relief.std() * 1.5  # about 1.5 m of relief
    rr, cc = np.indices((n, n))
    ridge = 15.0 * np.exp(-((cc - n * 0.5) ** 2) / (2 * (n * 0.04) ** 2)) * (rr > n * 0.15) * (rr < n * 0.85)
    dem = relief + ridge  # a steep north-south ridge with a gap near the top and bottom
    noise = config.noise_level * 0.2 * rng.standard_normal((n, n))
    valid = np.ones((n, n), dtype=bool)
    valid[int(n * 0.6):int(n * 0.7), int(n * 0.2):int(n * 0.3)] = False  # a missing patch
    ice = gaussian_filter(rng.random((n, n)), 3)
    return TerrainGrid(
        dem=dem + noise, valid_mask=valid, cell_size_m=2.0,
        bands={"ice_simulated": ice, "mineral_simulated": gaussian_filter(rng.random((n, n)), 4)},
        simulated_layers=["dem", "ice_simulated", "mineral_simulated"],
        source="stub synthetic DEM (" + STUB_NOTE + ")",
    )


def stub_compute_hazards(terrain: TerrainGrid, config: PipelineConfig) -> tuple[TerrainGrid, HazardMap]:
    dem = terrain.dem
    gy, gx = np.gradient(dem, terrain.cell_size_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    rough = np.sqrt(np.maximum(uniform_filter(dem ** 2, 3) - uniform_filter(dem, 3) ** 2, 0.0))
    aspect = np.degrees(np.arctan2(-gx, gy)) % 360.0
    full = TerrainGrid(dem=dem, valid_mask=terrain.valid_mask, cell_size_m=terrain.cell_size_m,
                       bands=terrain.bands, simulated_layers=terrain.simulated_layers,
                       slope_deg=slope, roughness=rough, aspect=aspect, source=terrain.source)
    p_slope = 1.0 / (1.0 + np.exp(-(slope - 20.0) / 3.0))
    p_rough = 1.0 / (1.0 + np.exp(-(rough - 2.0) / 0.5))
    hazard_prob = 1.0 - (1.0 - p_slope) * (1.0 - p_rough)
    terrain_class = np.digitize(slope, [8.0, 18.0]).astype(int)  # 0 flat, 1 sloped, 2 steep
    class_probs = np.eye(3)[terrain_class].transpose(2, 0, 1) * 0.9 + 0.1 / 3
    hazards = HazardMap(
        hazard_prob=hazard_prob, terrain_class=terrain_class, class_probs=class_probs,
        epistemic_std=0.05 + 0.1 * hazard_prob,
        hard_block=(slope > config.hard_block_slope_deg) | (hazard_prob > config.hazard_delta),
        evidence={0: "stub: slope below 8 deg", 1: "stub: slope 8 to 18 deg", 2: "stub: slope above 18 deg"},
        slope_std_deg=None,
    )
    return full, hazards


def stub_fill_slope_uncertainty(terrain: TerrainGrid, hazards: HazardMap, config: PipelineConfig) -> HazardMap:
    rng = np.random.default_rng(config.seeds.uncertainty)
    jitter = gaussian_filter(rng.random(terrain.shape), 4)
    std = config.noise_level * (0.5 + 0.08 * terrain.slope_deg) * (0.5 + jitter)
    return HazardMap(
        hazard_prob=hazards.hazard_prob, terrain_class=hazards.terrain_class, class_probs=hazards.class_probs,
        epistemic_std=hazards.epistemic_std, hard_block=hazards.hard_block, evidence=hazards.evidence,
        slope_std_deg=std,
    )


def stub_find_candidates(terrain: TerrainGrid, hazards: HazardMap, config: PipelineConfig) -> list[Candidate]:
    rng = np.random.default_rng(config.seeds.science_candidates)
    ice = terrain.bands["ice_simulated"]
    ok = ~hazards.hard_block & terrain.valid_mask
    score = np.where(ok, ice, -np.inf)
    out: list[Candidate] = []
    taken: list[tuple[int, int]] = []
    for flat in np.argsort(score, axis=None)[::-1]:
        loc = tuple(int(x) for x in np.unravel_index(flat, score.shape))
        if not np.isfinite(score[loc]) or len(out) >= config.n_candidates:
            break
        if any(np.hypot(loc[0] - t[0], loc[1] - t[1]) < 8 for t in taken) or loc == tuple(config.start):
            continue
        taken.append(loc)
        val = float(ice[loc])
        sd = 0.05 + 0.05 * rng.random()
        out.append(Candidate(id=f"T{len(out) + 1}", location=loc, kind="ice" if len(out) % 2 == 0 else "geology",
                             value_mean=val, value_ci=(val - 1.96 * sd, val + 1.96 * sd),
                             evidence=f"{STUB_NOTE}: peak of simulated ice band"))
    return out


def stub_rank_targets(candidates: list[Candidate], paths: dict[str, dict[str, PathResult]],
                      terrain: TerrainGrid, hazards: HazardMap, config: PipelineConfig) -> list[ScienceTarget]:
    """Access cost is the cautious path total_cost (the path CVaR). Unreachable targets stay listed."""
    rng = np.random.default_rng(config.seeds.ranking)
    n_draws = min(config.n_ranking_draws, 200)
    cands = list(candidates)
    cost = np.array([paths[c.id]["cautious"].total_cost for c in cands])
    mean = np.array([c.value_mean for c in cands])
    sd = np.array([(c.value_ci[1] - c.value_ci[0]) / (2 * 1.96) for c in cands])
    vals = np.clip(mean + sd * rng.standard_normal((n_draws, len(cands))), 0.0, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        scores = np.where(np.isfinite(cost), vals / cost, 0.0)
    ranks = (-scores).argsort(axis=1).argsort(axis=1) + 1
    targets = []
    for i, c in enumerate(cands):
        reach = "reachable" if np.isfinite(cost[i]) else "NO SAFE PATH"
        targets.append(ScienceTarget(
            id=c.id, location=c.location, value_mean=c.value_mean, value_ci=c.value_ci,
            path_cost=float(cost[i]), score=float(scores[:, i].mean()),
            score_ci=(float(np.percentile(scores[:, i], 5)), float(np.percentile(scores[:, i], 95))),
            rank_interval=(int(np.percentile(ranks[:, i], 5)), int(np.percentile(ranks[:, i], 95))),
            p_top3=float((ranks[:, i] <= 3).mean()),
            evidence=f"{STUB_NOTE}: value {c.value_mean:.2f} over cautious path cost, {reach}",
            kind=c.kind,
        ))
    targets.sort(key=lambda t: -t.score)
    return targets
