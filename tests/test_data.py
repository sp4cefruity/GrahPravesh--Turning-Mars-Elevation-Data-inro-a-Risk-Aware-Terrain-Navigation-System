"""Spec 05 checks. Run from the repo root: PYTHONPATH=src python -m pytest tests/test_data.py -q"""
import time

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from odyssey.data.dem import DemTile, _config, load_tile
from odyssey.data.scene import BANDS, K, block_mean, build_scene, correlated_noise, degrade_dem, make_rngs


def fake_tile(nan_patch=False):
    """Stand-in terrain for tests only. Not a data source."""
    z = gaussian_filter(np.random.default_rng(1).standard_normal((512, 512)), 30) * 200
    z = z.astype("f4")
    valid = np.ones(z.shape, bool)
    if nan_patch:
        z[100:140, 100:140], valid[100:140, 100:140] = np.nan, False
    return DemTile("fake", z, valid, 1.0097, 0.3, "fake", "none", (0, 0))


def test_streams_are_reproducible_and_independent():
    a, b = make_rngs(7), make_rngs(7)
    assert a["gaps"].random() == b["gaps"].random()
    a["targets"].random(100)  # drawing from one stream must not move another
    assert a["band_noise"].random() == b["band_noise"].random()


def test_correlated_noise_has_requested_std_and_is_smooth():
    n = correlated_noise(np.random.default_rng(0), (256, 256), 0.3, 8)
    assert abs(n.std() - 0.3) < 1e-6
    assert np.corrcoef(n[:, :-1].ravel(), n[:, 1:].ravel())[0, 1] > 0.9  # white noise would be about 0


def test_block_mean_shape_value_and_nan():
    a = np.arange(16, dtype=float).reshape(4, 4)
    m = block_mean(a)
    assert m.shape == (2, 2) and m[0, 0] == a[:2, :2].mean()
    a[0, 0] = np.nan
    assert np.isnan(block_mean(a)[0, 0]) and not np.isnan(block_mean(a)[1, 1])


def test_degrade_dem_noise_scales_with_level():
    tile = fake_tile()
    clean, noisy = degrade_dem(tile, np.random.default_rng(0), 1.0)
    assert clean.shape == (256, 256)
    assert abs((noisy - clean).std() - 0.3) < 1e-6
    clean0, noisy0 = degrade_dem(tile, np.random.default_rng(0), 0.0)
    assert np.array_equal(clean0, noisy0)


def test_same_seed_gives_identical_scene():
    a, _ = build_scene(fake_tile(), seed=3)
    b, _ = build_scene(fake_tile(), seed=3)
    assert np.array_equal(a.dem, b.dem, equal_nan=True)
    assert all(np.array_equal(a.bands[k], b.bands[k], equal_nan=True) for k in a.bands)
    c, _ = build_scene(fake_tile(), seed=4)
    assert not np.array_equal(a.dem, c.dem, equal_nan=True)


def test_noise_level_changes_amplitude_not_layout():
    lo, t_lo = build_scene(fake_tile(), seed=3, noise_level=0.5)
    hi, t_hi = build_scene(fake_tile(), seed=3, noise_level=2.0)
    assert np.array_equal(lo.valid_mask, hi.valid_mask)  # same gaps
    assert t_lo.targets == t_hi.targets                  # same planted targets
    assert not np.array_equal(lo.dem, hi.dem, equal_nan=True)


def test_missing_cells_are_invalid_and_nan_everywhere():
    s, t = build_scene(fake_tile(nan_patch=True), seed=3)
    assert not s.valid_mask[t.gap_mask].any()          # gaps are False
    assert not s.valid_mask[50:70, 50:70].any()        # source nodata (rows 100:140 at 1 m) carried over
    assert np.isnan(s.dem[~s.valid_mask]).all()
    assert all(np.isnan(a[~s.valid_mask]).all() for a in s.bands.values())
    assert not np.isnan(s.dem[s.valid_mask]).any()


def test_simulated_layers_tagged_and_shapes():
    s, _ = build_scene(fake_tile(), seed=3)
    assert set(s.simulated_layers) == set(s.bands) == set(BANDS) | {"ice_simulated", "thermal_simulated", "mineral_simulated"}
    assert s.dem.shape == (256, 256) and s.cell_size_m == 1.0097 * K


def test_targets_on_valid_cells_and_signal_follows_value():
    s, t = build_scene(fake_tile(nan_patch=True), seed=3, noise_level=0.0)
    assert len(t.targets) == 10
    assert all(s.valid_mask[x["row"], x["col"]] for x in t.targets)
    ice = [x for x in t.targets if x["kind"] == "ice"]
    if len(ice) >= 2:  # stronger planted value should read stronger on the ice band
        by_val = sorted(ice, key=lambda x: x["value"])
        assert s.bands["ice_simulated"][by_val[-1]["row"], by_val[-1]["col"]] > s.bands["ice_simulated"][by_val[0]["row"], by_val[0]["col"]]


def test_conflict_zone_sensors_disagree():
    s, t = build_scene(fake_tile(), seed=3, noise_level=0.0)
    z = t.conflict_zone & s.valid_mask
    assert z.any()
    assert np.allclose(s.bands["ice_simulated"][z], 0.9, atol=1e-6) and np.allclose(s.bands["thermal_simulated"][z], 0.1, atol=1e-6)


def test_input_dem_differs_from_truth_and_gap_grows_with_noise():
    tile = fake_tile()
    truth_coarse = block_mean(tile.dem)
    errs = []
    for lvl in (0.0, 1.0, 3.0):
        s, _ = build_scene(tile, seed=3, noise_level=lvl)
        errs.append(np.nanstd(s.dem - truth_coarse))
    assert errs[0] == 0 and errs[0] < errs[1] < errs[2]


@pytest.mark.parametrize("tid", ["T1", "T2", "T3", "T4", "T5"])
def test_real_tile_loads_caches_and_builds_a_scene(tid):
    tile = load_tile(tid)  # cache if present, else one windowed fetch (about 10 s)
    assert tile.dem.shape == (512, 512) and tile.valid_mask.mean() > 0.99
    lo, hi = next(p["valid_range_m"] for p in _config()["products"].values() if p["id"] == tile.product_id)
    assert lo <= np.nanmin(tile.dem) and np.nanmax(tile.dem) <= hi  # the label's valid range
    t0 = time.time()
    again = load_tile(tid)
    assert again.data_source == "cache" and time.time() - t0 < 3
    assert np.array_equal(tile.dem, again.dem, equal_nan=True)

    a, truth = build_scene(tile, seed=5)
    b, _ = build_scene(tile, seed=5)
    assert np.array_equal(a.dem, b.dem, equal_nan=True)
    assert not a.valid_mask[truth.gap_mask].any()
    assert all(a.valid_mask[x["row"], x["col"]] for x in truth.targets)
    assert truth.dem_truth.shape == (512, 512) and a.dem.shape == (256, 256)
