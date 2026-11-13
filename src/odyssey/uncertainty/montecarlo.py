"""DEM Monte Carlo: how much does slope move when the DEM is wrong by a plausible amount.

Noise model (documented in docs/RESEARCH_NOTES.md)
- Each draw adds a spatially correlated Gaussian random field to the DEM: white noise passed
  through a Gaussian filter, then rescaled to the target std `sigma_z`.
- Correlated noise matters. Independent per-pixel noise would overstate slope noise a lot.
- Each draw runs the same Horn slope kernel as perception. Only the running mean and std over
  draws are kept (Welford), never the draws themselves.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from ..config import PipelineConfig
from ..contracts import HazardMap, TerrainGrid
from ..perception.params import params_from
from ..perception.slope import fill_invalid_nearest, horn_slope_deg


def correlated_noise(rng: np.random.Generator, shape: tuple[int, int], sigma_z: float,
                     corr_cells: float) -> np.ndarray:
    """Gaussian random field with std sigma_z and Gaussian correlation length `corr_cells`."""
    white = rng.standard_normal(shape)
    if corr_cells <= 0:
        return sigma_z * white
    smooth = gaussian_filter(white, corr_cells, mode="reflect")
    # std of white noise after a 2D Gaussian filter of width s is 1 / (2 sqrt(pi) s)
    return sigma_z * smooth * (2.0 * np.sqrt(np.pi) * corr_cells)


def slope_monte_carlo(dem: np.ndarray, valid: np.ndarray, cell_size_m: float, *, sigma_z: float,
                      corr_cells: float, n_draws: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, std) of slope in degrees over `n_draws` noisy DEMs. NaN where `valid` is False."""
    if n_draws < 2:
        raise ValueError(f"n_draws must be at least 2 for a spread, got {n_draws}")
    base = fill_invalid_nearest(dem, valid)
    rng = np.random.default_rng(seed)
    mean = np.zeros(base.shape)
    m2 = np.zeros(base.shape)
    for i in range(1, n_draws + 1):
        s = horn_slope_deg(base + correlated_noise(rng, base.shape, sigma_z, corr_cells), cell_size_m)
        delta = s - mean
        mean += delta / i
        m2 += delta * (s - mean)
    std = np.sqrt(m2 / (n_draws - 1))
    return np.where(valid, mean, np.nan), np.where(valid, std, np.nan)


def fill_slope_uncertainty(terrain: TerrainGrid, hazards: HazardMap, config: PipelineConfig) -> HazardMap:
    """Pipeline stage `uncertainty`. Returns a copy of `hazards` with slope_std_deg filled."""
    p = params_from(config)
    _, std = slope_monte_carlo(
        terrain.dem, terrain.valid_mask, terrain.cell_size_m,
        sigma_z=config.noise_level * p.dem_sigma_base_m,
        corr_cells=p.corr_length_m / terrain.cell_size_m,
        n_draws=config.n_dem_draws, seed=config.seeds.uncertainty)
    return HazardMap(
        hazard_prob=hazards.hazard_prob, terrain_class=hazards.terrain_class, class_probs=hazards.class_probs,
        epistemic_std=hazards.epistemic_std, hard_block=hazards.hard_block, evidence=hazards.evidence,
        slope_std_deg=std, evidence_code=hazards.evidence_code)
