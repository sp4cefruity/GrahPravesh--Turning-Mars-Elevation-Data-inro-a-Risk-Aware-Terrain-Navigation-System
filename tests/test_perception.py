"""Spec 01 acceptance checks for perception: slope kernel, rules, Random Forest, hazard map."""

import dataclasses

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from odyssey import pipeline
from odyssey.config import PipelineConfig
from odyssey.contracts import TerrainGrid, validate_hazards, validate_terrain
from odyssey.perception import compute_hazards
from odyssey.perception.hazards import combine_hazard
from odyssey.perception.slope import aspect_deg, horn_slope_deg, roughness_m, step_height_m


def make_terrain(dem, cell=1.0, valid=None):
    dem = np.asarray(dem, dtype=float)
    valid = np.ones(dem.shape, dtype=bool) if valid is None else valid
    return TerrainGrid(dem=dem, valid_mask=valid, cell_size_m=cell,
                       bands={"ice_simulated": np.zeros(dem.shape)}, simulated_layers=["ice_simulated"],
                       source="test")


def ramp(n, deg, cell=1.0, axis=1):
    r = np.arange(n) * np.tan(np.radians(deg)) * cell
    return np.tile(r, (n, 1)) if axis == 1 else np.tile(r[:, None], (1, n))


def smooth_terrain(n=64, seed=0):
    rng = np.random.default_rng(seed)
    z = gaussian_filter(rng.standard_normal((n, n)), 8)
    return z / z.std() * 0.5


# ---------------------------------------------------------------- kernels


def test_horn_slope_recovers_a_planar_ramp():
    s = horn_slope_deg(ramp(20, 30.0, cell=2.0), 2.0)
    assert np.allclose(s[2:-2, 2:-2], 30.0, atol=1e-6)


def test_horn_slope_is_zero_on_flat_ground():
    assert np.allclose(horn_slope_deg(np.full((10, 10), 5.0), 1.0), 0.0)


def test_aspect_points_downhill_clockwise_from_north():
    east_up = ramp(20, 20.0, axis=1)  # rises to the east, so downhill is west (270)
    assert np.allclose(aspect_deg(east_up, 1.0)[3:-3, 3:-3], 270.0)
    south_up = ramp(20, 20.0, axis=0)  # row index grows downward (south), so downhill is north (0 or 360)
    a = aspect_deg(south_up, 1.0)[3:-3, 3:-3]
    assert np.allclose(np.minimum(a, 360.0 - a), 0.0, atol=1e-6)


def test_roughness_is_zero_on_a_plane_and_positive_on_bumps():
    assert np.allclose(roughness_m(ramp(20, 25.0), 1.0), 0.0, atol=1e-9)
    rng = np.random.default_rng(1)
    assert roughness_m(rng.standard_normal((20, 20)) * 0.3, 1.0)[5:-5, 5:-5].mean() > 0.1


def test_step_height_finds_a_ledge():
    z = np.zeros((10, 10))
    z[:, 5:] = 0.4
    st = step_height_m(z)
    assert st[5, 4] == pytest.approx(0.4) and st[5, 5] == pytest.approx(0.4) and st[5, 1] == 0.0


# ---------------------------------------------------------------- hazard maths


def test_combine_hazard_is_the_spec_formula():
    ps, pr, pc = np.array([0.5]), np.array([0.2]), np.array([0.1])
    assert combine_hazard(ps, pr, pc) == pytest.approx(1 - 0.5 * 0.8 * 0.9)


# ---------------------------------------------------------------- compute_hazards


def test_returns_full_terrain_and_contract_valid_hazard_map():
    t = make_terrain(smooth_terrain())
    full, h = compute_hazards(t, PipelineConfig())
    validate_terrain(full, full=True)
    validate_hazards(h, t.shape, need_slope_std=False)
    assert h.slope_std_deg is None
    assert full.dem is t.dem and full.bands is t.bands and full.simulated_layers == t.simulated_layers


def test_slope_map_matches_dem_relief():
    t = make_terrain(ramp(40, 12.0))
    full, _ = compute_hazards(t, PipelineConfig())
    assert np.allclose(full.slope_deg[3:-3, 3:-3], 12.0, atol=1e-6)


def test_forced_steep_patch_is_a_hard_block():
    dem = smooth_terrain()
    dem[20:40, 20:40] += ramp(20, 40.0)  # 40 degree patch, limit is 25
    _, h = compute_hazards(make_terrain(dem), PipelineConfig())
    assert h.hard_block[25:35, 25:35].all()
    assert not h.hard_block[:10, :10].any()


def test_gentle_terrain_has_no_hard_blocks():
    _, h = compute_hazards(make_terrain(smooth_terrain()), PipelineConfig())
    assert not h.hard_block.any()
    assert h.hazard_prob.max() < 0.5


def test_hard_block_limit_comes_from_config():
    t = make_terrain(ramp(40, 15.0))
    _, h = compute_hazards(t, dataclasses.replace(PipelineConfig(), hard_block_slope_deg=10.0))
    assert h.hard_block[5:-5, 5:-5].all()
    _, h = compute_hazards(t, PipelineConfig())
    assert not h.hard_block[5:-5, 5:-5].any()


def test_hazard_delta_comes_from_config():
    dem = smooth_terrain()
    dem[20:40, 20:40] += ramp(20, 22.0)  # below the 25 degree limit, but a high slope probability
    _, strict = compute_hazards(make_terrain(dem), dataclasses.replace(PipelineConfig(), hazard_delta=0.5))
    _, loose = compute_hazards(make_terrain(dem), PipelineConfig())
    assert strict.hard_block.sum() > loose.hard_block.sum()


def test_crater_rim_is_hard_blocked():
    n = 80
    rr, cc = np.indices((n, n))
    radius = np.hypot(rr - 40, cc - 40)
    dem = 1.5 * np.exp(-((radius - 25) ** 2) / (2 * 3.0 ** 2))  # a raised ring, crest radius 25 cells
    _, h = compute_hazards(make_terrain(dem), PipelineConfig())
    crest = np.abs(radius - 25) < 1.0
    assert h.hard_block[crest].mean() > 0.9
    assert not h.hard_block[radius < 10].any()
    assert "rim" in h.evidence[int(h.evidence_code[crest][0])]


def test_missing_cells_stay_flagged_and_are_not_zero_filled():
    valid = np.ones((64, 64), dtype=bool)
    valid[20:30, 20:30] = False
    t = make_terrain(smooth_terrain(), valid=valid)
    full, h = compute_hazards(t, PipelineConfig())
    assert np.array_equal(full.valid_mask, valid)
    for name in ("slope_deg", "roughness", "aspect"):
        assert np.isnan(getattr(full, name)[~valid]).all(), name
        assert np.isfinite(getattr(full, name)[valid]).all(), name
    assert not h.hard_block[~valid].any()  # the planner adds ~valid_mask
    assert "missing" in h.evidence[int(h.evidence_code[~valid][0])]
    assert (h.hazard_prob[~valid] == 1.0).all()


def test_every_hazard_cell_has_an_evidence_note():
    dem = smooth_terrain()
    dem[20:40, 20:40] += ramp(20, 40.0)
    _, h = compute_hazards(make_terrain(dem), PipelineConfig())
    flagged = h.hard_block | (h.hazard_prob >= 0.5)
    assert flagged.any()
    assert (h.evidence_code[flagged] != 0).all()
    assert set(np.unique(h.evidence_code).tolist()) <= set(h.evidence)
    assert all(isinstance(v, str) and v.strip() for v in h.evidence.values())


def test_class_probabilities_are_votes_that_sum_to_one():
    dem = smooth_terrain()
    dem[20:40, 20:40] += ramp(20, 40.0)
    t = make_terrain(dem)
    _, h = compute_hazards(t, PipelineConfig())
    assert h.class_probs.ndim == 3 and h.class_probs.shape[1:] == t.shape
    assert np.allclose(h.class_probs.sum(axis=0), 1.0)
    assert h.epistemic_std.min() >= 0.0 and h.epistemic_std.max() <= 0.5
    assert h.terrain_class.dtype.kind == "i"


def test_same_input_and_seed_give_identical_hazards():
    t = make_terrain(smooth_terrain())
    a = compute_hazards(t, PipelineConfig())[1]
    b = compute_hazards(t, PipelineConfig())[1]
    assert np.array_equal(a.class_probs, b.class_probs) and np.array_equal(a.hazard_prob, b.hazard_prob)


def test_hazard_probability_rises_with_slope():
    lo = compute_hazards(make_terrain(ramp(40, 8.0)), PipelineConfig())[1].hazard_prob[20, 20]
    hi = compute_hazards(make_terrain(ramp(40, 21.0)), PipelineConfig())[1].hazard_prob[20, 20]
    assert hi > lo


def test_all_missing_input_fails_loudly():
    t = make_terrain(np.zeros((10, 10)), valid=np.zeros((10, 10), dtype=bool))
    with pytest.raises(ValueError, match="no valid cells"):
        compute_hazards(t, PipelineConfig())


# ---------------------------------------------------------------- pipeline integration


def test_pipeline_uses_real_perception_and_completes_with_gaps():
    res = pipeline.run_pipeline(PipelineConfig())
    assert res.complete, res.error
    assert np.isnan(res.terrain.slope_deg[~res.terrain.valid_mask]).all()


# ---------------------------------------------------------------- CNN experiment (spec 01, "CNN experiment")

torch = pytest.importorskip("torch")
from odyssey.perception import cnn  # noqa: E402
from odyssey.perception.params import PerceptionParams  # noqa: E402

CNN_PARAMS = PerceptionParams(classifier="cnn", cnn_epochs=8, cnn_members=3)


def cnn_config():
    return dataclasses.replace(PipelineConfig(), perception=CNN_PARAMS)


def steep_patch_terrain():
    dem = smooth_terrain()
    dem[20:40, 20:40] += ramp(20, 40.0)
    return make_terrain(dem)


def test_classifier_flag_defaults_to_the_random_forest():
    assert PerceptionParams().classifier == "forest"
    assert PipelineConfig().perception.classifier == "forest"


def test_cnn_returns_a_contract_valid_hazard_map_with_class_probabilities():
    t = steep_patch_terrain()
    _, h = compute_hazards(t, cnn_config())
    validate_hazards(h, t.shape, need_slope_std=False)
    assert h.class_probs.shape == (5,) + t.shape
    assert np.allclose(h.class_probs.sum(axis=0), 1.0, atol=1e-5)
    assert h.class_probs.min() >= 0.0
    assert h.epistemic_std.min() >= 0.0 and h.epistemic_std.max() <= 0.5


def test_cnn_epistemic_std_is_not_all_zero():
    _, h = compute_hazards(steep_patch_terrain(), cnn_config())
    assert h.epistemic_std.max() > 0.0


def test_cnn_keeps_the_hard_block_rules_and_evidence_codes():
    _, h = compute_hazards(steep_patch_terrain(), cnn_config())
    assert h.hard_block[25:35, 25:35].all()
    assert not h.hard_block[:10, :10].any()
    assert set(np.unique(h.evidence_code).tolist()) <= set(h.evidence)
    assert "CNN" in h.evidence[7]


def test_cnn_same_seed_gives_identical_output():
    t = steep_patch_terrain()
    a = compute_hazards(t, cnn_config())[1]
    b = compute_hazards(t, cnn_config())[1]
    assert np.array_equal(a.class_probs, b.class_probs)
    assert np.array_equal(a.epistemic_std, b.epistemic_std)


def test_cnn_masks_missing_cells_like_the_forest():
    valid = np.ones((64, 64), dtype=bool)
    valid[20:30, 20:30] = False
    full, h = compute_hazards(make_terrain(smooth_terrain(), valid=valid), cnn_config())
    assert np.isnan(full.slope_deg[~valid]).all()
    assert (h.hazard_prob[~valid] == 1.0).all() and not h.hard_block[~valid].any()
    assert (h.terrain_class[~valid] == -1).all()


def test_missing_torch_falls_back_to_the_forest_and_says_so(monkeypatch):
    monkeypatch.setattr(cnn, "torch_available", lambda: False)
    t = steep_patch_terrain()
    _, fallback = compute_hazards(t, cnn_config())
    _, forest = compute_hazards(t, PipelineConfig())
    assert np.array_equal(fallback.class_probs, forest.class_probs)
    assert any("fell back" in note for note in fallback.evidence.values())
    assert "Random Forest" in fallback.evidence[7]


def test_class_weights_raise_rare_classes_and_keep_the_mean_loss_scale():
    y = np.array([0] * 90 + [1] * 9 + [4] * 1)
    valid = np.ones(y.shape, dtype=bool)
    w = cnn.class_weights(y, valid, k=5, mode="inverse")
    assert w[4] > w[1] > w[0]
    assert (w * np.bincount(y, minlength=5) / y.size).sum() == pytest.approx(1.0)
    assert np.allclose(cnn.class_weights(y, valid, k=5, mode="none"), 1.0)
    sq = cnn.class_weights(y, valid, k=5, mode="sqrt_inverse")
    assert w[4] / w[0] > sq[4] / sq[0] > 1.0


def test_class_weights_ignore_invalid_cells_and_reject_unknown_mode():
    y = np.array([0, 0, 0, 1])
    valid = np.array([True, True, True, False])
    w = cnn.class_weights(y, valid, k=2, mode="inverse")
    assert w[0] == pytest.approx(1.0)  # only class 0 is seen
    with pytest.raises(ValueError, match="class weight mode"):
        cnn.class_weights(y, valid, k=2, mode="nope")


def test_cnn_loss_weighting_defaults_on_and_can_be_switched_off():
    assert PerceptionParams().cnn_class_weight == "sqrt_inverse"
    p = dataclasses.replace(CNN_PARAMS, cnn_class_weight="none")
    _, h = compute_hazards(steep_patch_terrain(), dataclasses.replace(PipelineConfig(), perception=p))
    assert np.allclose(h.class_probs.sum(axis=0), 1.0, atol=1e-5)
