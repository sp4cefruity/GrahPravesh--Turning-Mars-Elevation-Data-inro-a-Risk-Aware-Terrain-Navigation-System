"""Perception thresholds.

Every number here is a working ASSUMPTION unless a source is named next to it. None of them
is fitted to rover data. `docs/RESEARCH_NOTES.md` lists what still needs a citation.
`hard_block_slope_deg` and `hazard_delta` are not here, they live in `PipelineConfig`.
To override anything for a sweep, set a `perception` attribute on the config that holds a
`PerceptionParams`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerceptionParams:
    # P_slope = Phi((slope - center) / sigma). Assumption: center sits between the planner soft
    # slope scale (15 deg) and the hard limit (25 deg), see docs/ARCHITECTURE.md working values.
    slope_center_deg: float = 20.0
    slope_sigma_deg: float = 3.0
    # P_rough = Phi((roughness - center) / sigma), roughness is plane-fit residual std in a 3 by 3 window.
    # Assumption. The wheel size rationale is unverified, see RESEARCH_NOTES.
    rough_center_m: float = 0.25
    rough_sigma_m: float = 0.10
    rough_window_cells: int = 3
    # Crater rim rule: strongly convex cell with steep ground within two cells. Assumption.
    rim_convexity_per_m: float = 0.05
    rim_slope_deg: float = 10.0
    # Class label for "moderate slope" in the pseudo-labels. Assumption.
    moderate_slope_deg: float = 10.0
    # A hazard_prob at or above this gets a soft-hazard evidence note even without a hard block.
    soft_flag_prob: float = 0.5
    # Random Forest (pseudo-labelled from the rules)
    n_trees: int = 50
    max_depth: int = 8
    min_samples_leaf: int = 5
    max_train_cells: int = 20000
    # Terrain classifier: "forest" (default, fallback) or "cnn" (experiment, specs/01-perception.md).
    classifier: str = "forest"
    # CNN: small fully convolutional net trained on random patches of the rule pseudo-labels.
    # All values are working assumptions, not tuned. The ensemble spread gives epistemic_std.
    cnn_patch: int = 32
    cnn_members: int = 3
    cnn_epochs: int = 60  # optimiser steps, one batch of cnn_batch patches each
    cnn_batch: int = 16
    cnn_width: int = 16
    cnn_dropout: float = 0.1
    cnn_lr: float = 0.01
    # Loss weights against class imbalance: "none", "sqrt_inverse" or "inverse" class frequency.
    cnn_class_weight: str = "sqrt_inverse"
    # Monte Carlo DEM noise (see docs/RESEARCH_NOTES.md, DEM noise model)
    dem_sigma_base_m: float = 0.3  # at noise_level 1.0, "tens of centimeters" for HiRISE DTMs
    corr_length_m: float = 20.0  # plan range is 10 to 50 m, tunable


def params_from(config) -> PerceptionParams:
    return getattr(config, "perception", None) or PerceptionParams()
