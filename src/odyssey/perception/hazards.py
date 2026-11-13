"""Rule-based hazards, Random Forest terrain classes, hazard probability and hard block.

Flow (specs/01-perception.md)
1. Slope, roughness, step, convexity from the DEM.
2. Rules give pseudo-labels for 5 terrain classes. A Random Forest learns them. The rules are
   not human ground truth, so the forest only shows how stable the rule boundaries are.
   Tree votes give class_probs, and the spread of the hazard vote gives epistemic_std.
3. hazard_prob = 1 - (1 - P_slope)(1 - P_rough)(1 - P_class).
4. hard_block = slope > limit OR crater rim OR hazard_prob > delta, on valid cells only.
Missing cells keep valid_mask False, get NaN derived layers and a "missing data" evidence code.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.special import ndtr
from sklearn.ensemble import RandomForestClassifier

from ..config import PipelineConfig
from ..contracts import HazardMap, TerrainGrid
from .params import PerceptionParams, params_from
from .slope import (aspect_deg, convexity_per_m, fill_invalid_nearest, horn_slope_deg, roughness_m,
                    step_height_m)

CLASS_NAMES = {0: "smooth", 1: "moderate slope", 2: "rough", 3: "crater rim", 4: "steep"}
HAZARD_CLASSES = (3, 4)
MISSING_CLASS = -1  # label for cells with no data

CODE_NONE, CODE_STEEP, CODE_RIM, CODE_DELTA, CODE_MISSING, CODE_SOFT_SLOPE, CODE_SOFT_ROUGH, CODE_SOFT_CLASS = range(8)


def combine_hazard(p_slope: np.ndarray, p_rough: np.ndarray, p_class: np.ndarray) -> np.ndarray:
    """Independence assumption, conservative when the errors are positively correlated."""
    return 1.0 - (1.0 - p_slope) * (1.0 - p_rough) * (1.0 - p_class)


def _legend(limit: float, delta: float, p: PerceptionParams) -> dict[int, str]:
    return {
        CODE_NONE: "no hazard rule fired",
        CODE_STEEP: f"rule: slope above the hard limit of {limit:g} deg",
        CODE_RIM: (f"rule: crater rim (convexity above {p.rim_convexity_per_m:g} per m "
                   f"with slope above {p.rim_slope_deg:g} deg nearby)"),
        CODE_DELTA: f"model: combined hazard probability above delta {delta:g}",
        CODE_MISSING: "missing data (valid_mask False), no hazard estimate, not filled",
        CODE_SOFT_SLOPE: f"soft: slope probability dominates, hazard probability at least {p.soft_flag_prob:g}",
        CODE_SOFT_ROUGH: f"soft: roughness probability dominates, hazard probability at least {p.soft_flag_prob:g}",
        CODE_SOFT_CLASS: f"soft: Random Forest class vote dominates, hazard probability at least {p.soft_flag_prob:g}",
    }


def _rule_labels(slope, rough, rim, limit, p: PerceptionParams) -> np.ndarray:
    """Pseudo-labels. Priority: steep, rim, rough, moderate slope, smooth."""
    y = np.zeros(slope.shape, dtype=int)
    y[slope >= p.moderate_slope_deg] = 1
    y[rough > p.rough_center_m] = 2
    y[rim] = 3
    y[slope > limit] = 4
    return y


def _forest_votes(features: np.ndarray, labels: np.ndarray, valid: np.ndarray, seed: int,
                  p: PerceptionParams) -> tuple[np.ndarray, np.ndarray]:
    """Return (class_probs (K, H, W), p_class_std (H, W)) from per-tree hard votes."""
    h, w, nf = features.shape
    k = len(CLASS_NAMES)
    rng = np.random.default_rng(seed)
    flat_x = features.reshape(-1, nf)
    idx = np.flatnonzero(valid.ravel())
    train = idx if idx.size <= p.max_train_cells else rng.choice(idx, p.max_train_cells, replace=False)
    rf = RandomForestClassifier(n_estimators=p.n_trees, max_depth=p.max_depth,
                                min_samples_leaf=p.min_samples_leaf, random_state=seed, n_jobs=1)
    rf.fit(flat_x[train], labels.ravel()[train])
    x = flat_x[idx]
    votes = np.zeros((k, idx.size))
    hazard_votes = np.zeros((len(rf.estimators_), idx.size))
    for t, tree in enumerate(rf.estimators_):
        lab = rf.classes_[tree.predict(x).astype(int)]
        votes[lab, np.arange(idx.size)] += 1
        hazard_votes[t] = np.isin(lab, HAZARD_CLASSES)
    probs = np.zeros((k, h * w))
    probs[:, idx] = votes / len(rf.estimators_)
    std = np.zeros(h * w)
    std[idx] = hazard_votes.std(axis=0)
    return probs.reshape(k, h, w), std.reshape(h, w)


def compute_hazards(terrain: TerrainGrid, config: PipelineConfig) -> tuple[TerrainGrid, HazardMap]:
    """Pipeline stage `perception`. Returns the full TerrainGrid and a HazardMap (slope_std_deg None)."""
    p = params_from(config)
    limit, delta = config.hard_block_slope_deg, config.hazard_delta
    valid = np.asarray(terrain.valid_mask, dtype=bool)
    cs = terrain.cell_size_m
    dem = fill_invalid_nearest(terrain.dem, valid)  # internal only, masked back below

    slope = horn_slope_deg(dem, cs)
    aspect = aspect_deg(dem, cs)
    rough = roughness_m(dem, cs, p.rough_window_cells)
    step = step_height_m(dem, p.rough_window_cells)
    convex = convexity_per_m(dem, cs)

    rim = (convex < -p.rim_convexity_per_m) & (maximum_filter(slope, size=5, mode="nearest") > p.rim_slope_deg)
    labels = _rule_labels(slope, rough, rim, limit, p)
    features = np.stack([slope, rough, step, convex], axis=-1)
    class_probs, epistemic = _forest_votes(features, labels, valid, config.seeds.perception, p)

    p_slope = ndtr((slope - p.slope_center_deg) / p.slope_sigma_deg)
    p_rough = ndtr((rough - p.rough_center_m) / p.rough_sigma_m)
    p_class = class_probs[list(HAZARD_CLASSES)].sum(axis=0)
    hazard = combine_hazard(p_slope, p_rough, p_class)

    steep = (slope > limit) & valid
    rim_v = rim & valid
    over_delta = (hazard > delta) & valid
    hard_block = steep | rim_v | over_delta

    soft = valid & (hazard >= p.soft_flag_prob)
    dominant = np.argmax(np.stack([p_slope, p_rough, p_class]), axis=0)
    code = np.full(slope.shape, CODE_NONE, dtype=int)
    code[soft] = np.array([CODE_SOFT_SLOPE, CODE_SOFT_ROUGH, CODE_SOFT_CLASS])[dominant][soft]
    code[over_delta] = CODE_DELTA
    code[rim_v] = CODE_RIM
    code[steep] = CODE_STEEP
    code[~valid] = CODE_MISSING

    terrain_class = np.where(valid, class_probs.argmax(axis=0), MISSING_CLASS).astype(int)
    hazard = np.where(valid, np.clip(hazard, 0.0, 1.0), 1.0)  # no data is treated as maximal hazard

    def keep(a: np.ndarray) -> np.ndarray:
        return np.where(valid, a, np.nan)

    full = TerrainGrid(dem=terrain.dem, valid_mask=terrain.valid_mask, cell_size_m=cs, bands=terrain.bands,
                       simulated_layers=terrain.simulated_layers, slope_deg=keep(slope), roughness=keep(rough),
                       aspect=keep(aspect), source=terrain.source)
    hazards = HazardMap(hazard_prob=hazard, terrain_class=terrain_class, class_probs=class_probs,
                        epistemic_std=epistemic, hard_block=hard_block, evidence=_legend(limit, delta, p),
                        slope_std_deg=None, evidence_code=code)
    return full, hazards
