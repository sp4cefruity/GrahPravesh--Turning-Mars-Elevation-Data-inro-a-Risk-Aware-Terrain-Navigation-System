from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

from odyssey.contracts import TerrainGrid
from odyssey.data.dem import DemTile

K=2
MATERIALS = ["basalt", "clay", "dust", "ice"]
BANDS = ["b1", "b2", "b3", "b4", "b5"]
ICE, CLAY = 3,1
ICE_BIAS = 2.5
STREAMS = ["dem_noise", "materials", "gaps", "targets", "band_noise"]

SPECTRA = np.array([
    [0.08, 0.10, 0.12, 0.14, 0.15],
    [0.20, 0.25, 0.30, 0.18, 0.28],
    [0.25, 0.35, 0.42, 0.45, 0.47],
    [0.60, 0.55, 0.35, 0.10, 0.15],
])

def make_rngs(seed):
    kids = np.random.SeedSequence(seed).spawn(len(STREAMS))
    return {name: np.random.default_rng(k) for name,k in zip(STREAMS,kids)}

def correlated_noise(rng, shape, sigma, corr_cells):
    n = gaussian_filter(rng.standard_normal(shape), corr_cells)
    return n/n.std() * sigma

def block_mean(a, k=K):
    h, w = a.shape
    return a.reshape(h//k, k, w//k, k).mean(axis=(1,3))

def degrade_dem(tile, rng, noise_level, corr_cells=8):
    clean = block_mean(tile.dem)
    noise = correlated_noise(rng, clean.shape, tile.sigma_z_m*noise_level, corr_cells)
    return clean, clean + noise

def abundances(rng, clean, cell_m):
    z = np.where(np.isnan(clean), np.nanmean(clean), clean)  # internal only, never output
    gy, gx = np.gradient(z, cell_m)
    slope = np.hypot(gx, gy)
    s = (slope - slope.mean()) / slope.std()
    e = (z - z.mean()) / z.std()
    blobs = np.stack([correlated_noise(rng, z.shape, 1.0, 12) for _ in MATERIALS])
    terrain = np.stack([s, -e, -s, -e - s])  # basalt on slopes, clay and ice low, dust flat
    score = terrain + 1.5 * blobs
    score[ICE] -= ICE_BIAS  # keep background ice rare so planted ice targets stand out
    ex = np.exp(score - score.max(axis=0))  # softmax over the 4 materials
    return ex / ex.sum(axis=0)

def gap_mask(rng, shape, n_blocks=6, max_size=30, stripe_len=90):
    bad = np.zeros(shape, bool)
    for _ in range(n_blocks):
        h, w = rng.integers(8, max_size, 2)
        r, c = rng.integers(0, shape[0] - h), rng.integers(0, shape[1] - w)
        bad[r:r + h, c:c + w] = True
    r0, c0 = rng.integers(0, shape[0] - stripe_len), rng.integers(0, shape[1] - 3)
    bad[r0:r0 + stripe_len, c0:c0 + 3] = True  # partial seam stripe, a full one would wall off the map
    return bad

def plant_targets(rng, valid, n=10, margin=10):
    cells = np.argwhere(valid[margin:-margin, margin:-margin]) + margin
    picks = cells[rng.choice(len(cells), n, replace=False)]
    return [{"id": f"P{i}", "row": int(r), "col": int(c),
             "kind": "ice" if rng.random() < 0.5 else "geology",
             "value": float(rng.uniform(0.2, 1.0))}
            for i, (r, c) in enumerate(picks)]

def paint(ab, targets, radius=6):
    """Add each target's blob to the ice or clay abundance, so signal strength encodes its value."""
    rr, cc = np.mgrid[:ab.shape[1], :ab.shape[2]]
    for t in targets:
        blob = t["value"] * np.exp(-((rr - t["row"]) ** 2 + (cc - t["col"]) ** 2) / (2 * radius ** 2))
        ab[ICE if t["kind"] == "ice" else CLAY] += 2 * blob
    ab /= ab.sum(axis=0)

def conflict_zone(rng, valid, radius=10):
    rows, cols = np.nonzero(valid)
    i = rng.integers(len(rows))
    rr, cc = np.mgrid[:valid.shape[0], :valid.shape[1]]
    return (rr - rows[i]) ** 2 + (cc - cols[i]) ** 2 <= radius ** 2

def make_bands(ab):
    bands = np.einsum("kb,khw->bhw", SPECTRA, ab)  # linear mixing of material spectra
    # Science reads: ice, thermal (high = ice consistent, so low thermal beside high ice is a conflict), mineral.
    return bands, ab[ICE].copy(), ab[ICE].copy(), ab[CLAY].copy()

@dataclass(frozen=True)
class SceneTruth:  # for evaluation only, never given to the planner
    dem_truth: np.ndarray
    targets: list
    conflict_zone: np.ndarray
    gap_mask: np.ndarray

def build_scene(tile: DemTile, seed=0, noise_level=1.0):
    rng = make_rngs(seed)
    clean, dem = degrade_dem(tile, rng["dem_noise"], noise_level)
    ab = abundances(rng["materials"], clean, tile.cell_size_m * K)
    gaps = gap_mask(rng["gaps"], clean.shape)
    valid = ~np.isnan(clean) & ~gaps
    targets = plant_targets(rng["targets"], valid)
    paint(ab, targets)
    zone = conflict_zone(rng["targets"], valid)

    bands, ice, thermal, mineral = make_bands(ab)
    ice[zone], thermal[zone] = 0.9, 0.1  # ice sensor says ice, thermal says not ice: they disagree

    sigma = 0.03 * noise_level  # band noise, independent per cell
    out = {}
    for name, arr in zip(BANDS + ["ice_simulated", "thermal_simulated", "mineral_simulated"], [*bands, ice, thermal, mineral]):
        noisy = arr + rng["band_noise"].standard_normal(arr.shape) * sigma
        noisy[~valid] = np.nan
        out[name] = noisy.astype(np.float32)
    dem = np.where(valid, dem, np.nan).astype(np.float32)

    source = (f"HiRISE DTM {tile.product_id} {tile.tile_id} ({tile.data_source}): real elevation, "
              f"2 m block mean plus simulated noise")
    grid = TerrainGrid(dem=dem, valid_mask=valid, cell_size_m=tile.cell_size_m * K, bands=out,
                       simulated_layers=list(out), source=source)
    return grid, SceneTruth(tile.dem, targets, zone, gaps)