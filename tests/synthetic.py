"""A small synthetic scene for tests only. It is not a data source and the pipeline never uses it."""

import numpy as np
from scipy.ndimage import gaussian_filter

from odyssey.contracts import TerrainGrid


def synthetic_terrain(config, n=64):
    """Gentle relief, a steep north-south ridge with gaps near the top and bottom, a missing patch."""
    rng = np.random.default_rng(config.seeds.data)
    relief = gaussian_filter(rng.standard_normal((n, n)), n / 8)
    relief = relief / relief.std() * 1.5  # about 1.5 m of relief
    rr, cc = np.indices((n, n))
    ridge = 15.0 * np.exp(-((cc - n * 0.5) ** 2) / (2 * (n * 0.04) ** 2)) * (rr > n * 0.15) * (rr < n * 0.85)
    noise = config.noise_level * 0.2 * rng.standard_normal((n, n))
    valid = np.ones((n, n), dtype=bool)
    valid[int(n * 0.6):int(n * 0.7), int(n * 0.2):int(n * 0.3)] = False
    ice = gaussian_filter(rng.random((n, n)), 3)
    return TerrainGrid(
        dem=relief + ridge + noise, valid_mask=valid, cell_size_m=2.0,
        bands={"ice_simulated": ice, "mineral_simulated": gaussian_filter(rng.random((n, n)), 4)},
        simulated_layers=["dem", "ice_simulated", "mineral_simulated"],
        source="synthetic test scene",
    )
