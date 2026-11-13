"""Spec 01 acceptance checks for the DEM Monte Carlo."""

import dataclasses

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from odyssey import pipeline
from odyssey.config import PipelineConfig, Seeds
from odyssey.contracts import TerrainGrid, validate_hazards
from odyssey.perception import compute_hazards
from odyssey.uncertainty import fill_slope_uncertainty
from odyssey.uncertainty.montecarlo import correlated_noise, slope_monte_carlo


def scene(valid=None, n=64):
    rng = np.random.default_rng(0)
    z = gaussian_filter(rng.standard_normal((n, n)), 8)
    dem = z / z.std() * 0.5
    valid = np.ones((n, n), dtype=bool) if valid is None else valid
    return TerrainGrid(dem=dem, valid_mask=valid, cell_size_m=2.0, source="test")


def run(cfg, terrain=None):
    full, h = compute_hazards(terrain or scene(), cfg)
    return full, fill_slope_uncertainty(full, h, cfg)


def test_noise_is_spatially_correlated_with_the_requested_std():
    rng = np.random.default_rng(3)
    z = correlated_noise(rng, (128, 128), sigma_z=0.4, corr_cells=6.0)
    assert z.std() == pytest.approx(0.4, rel=0.25)
    neighbour_corr = np.corrcoef(z[:, :-1].ravel(), z[:, 1:].ravel())[0, 1]
    assert neighbour_corr > 0.8  # white noise would give about 0


def test_fills_slope_std_and_keeps_the_rest_of_the_hazard_map():
    cfg = PipelineConfig()
    full, h = compute_hazards(scene(), cfg)
    out = fill_slope_uncertainty(full, h, cfg)
    validate_hazards(out, full.shape, need_slope_std=True)
    assert np.nanmin(out.slope_std_deg) >= 0
    assert np.array_equal(out.hard_block, h.hard_block) and np.array_equal(out.evidence_code, h.evidence_code)
    assert out.evidence == h.evidence and h.slope_std_deg is None  # input is not mutated


def test_slope_std_is_larger_at_higher_noise():
    lo = run(dataclasses.replace(PipelineConfig(), noise_level=0.5))[1].slope_std_deg
    hi = run(dataclasses.replace(PipelineConfig(), noise_level=2.0))[1].slope_std_deg
    assert hi.mean() > 2.0 * lo.mean()


def test_same_seed_same_std_different_seed_differs():
    a = run(PipelineConfig())[1].slope_std_deg
    b = run(PipelineConfig())[1].slope_std_deg
    c = run(dataclasses.replace(PipelineConfig(), seeds=Seeds(uncertainty=77)))[1].slope_std_deg
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_zero_noise_gives_zero_std():
    out = run(dataclasses.replace(PipelineConfig(), noise_level=0.0))[1]
    assert np.allclose(out.slope_std_deg, 0.0)


def test_missing_cells_stay_nan_in_slope_std():
    valid = np.ones((64, 64), dtype=bool)
    valid[10:20, 10:20] = False
    out = run(PipelineConfig(), scene(valid))[1]
    assert np.isnan(out.slope_std_deg[~valid]).all() and np.isfinite(out.slope_std_deg[valid]).all()


def test_monte_carlo_returns_mean_and_std_and_rejects_one_draw():
    t = scene()
    mean, std = slope_monte_carlo(t.dem, t.valid_mask, t.cell_size_m, sigma_z=0.3, corr_cells=5.0,
                                  n_draws=60, seed=1)
    assert mean.shape == std.shape == t.shape
    with pytest.raises(ValueError, match="n_draws"):
        slope_monte_carlo(t.dem, t.valid_mask, t.cell_size_m, sigma_z=0.3, corr_cells=5.0, n_draws=1, seed=1)


def test_pipeline_uses_real_uncertainty():
    res = pipeline.run_pipeline(PipelineConfig())
    assert res.complete, res.error
