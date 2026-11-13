"""DEM derivatives with our own numpy kernels (no GPL dependency).

Slope and aspect use the Horn (1981) 3 by 3 weighted finite difference, the same
method as `gdaldem slope`. Borders use odd reflection, which continues a plane exactly. Curved terrain at the border is still less reliable.

Conventions
- Row 0 is the top of the array and is treated as north.
- Aspect is the downhill direction in degrees clockwise from north (0 to 360).
- Roughness is the standard deviation of the residual after fitting a plane in a
  window (so a smooth ramp has zero roughness, however steep).
- Step height is the largest height difference inside a window.
"""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.ndimage import gaussian_filter, maximum_filter, minimum_filter


def _pad(dem: np.ndarray, width: int) -> np.ndarray:
    """Odd reflection continues a plane through the border, so ramps keep their exact slope there."""
    return np.pad(np.asarray(dem, dtype=float), width, mode="reflect", reflect_type="odd")


def _horn_gradients(dem: np.ndarray, cell_size_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (dz/d east, dz/d row) in metres per metre."""
    p = _pad(dem, 1)
    dz_dx = ((p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])) / (8 * cell_size_m)
    dz_dr = ((p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])) / (8 * cell_size_m)
    return dz_dx, dz_dr


def horn_slope_deg(dem: np.ndarray, cell_size_m: float) -> np.ndarray:
    gx, gr = _horn_gradients(dem, cell_size_m)
    return np.degrees(np.arctan(np.hypot(gx, gr)))


def aspect_deg(dem: np.ndarray, cell_size_m: float) -> np.ndarray:
    gx, gr = _horn_gradients(dem, cell_size_m)
    # downhill east component is -gx, downhill north component is +gr (north is up, rows grow south)
    return np.degrees(np.arctan2(-gx, gr)) % 360.0


def roughness_m(dem: np.ndarray, cell_size_m: float, window: int = 3) -> np.ndarray:
    """Plane-fit residual std in a window x window neighbourhood, in metres.

    `cell_size_m` is not needed for the vertical residual. It is kept in the signature so every
    kernel takes the same arguments.
    """
    off = np.arange(window) - (window - 1) / 2
    xx, yy = np.meshgrid(off, off)
    design = np.stack([np.ones(window * window), xx.ravel(), yy.ravel()], axis=1)
    resid_op = np.eye(window * window) - design @ np.linalg.pinv(design)
    pad = window // 2
    p = _pad(dem, pad)
    win = sliding_window_view(p, (window, window)).reshape(*dem.shape, window * window)
    resid = win @ resid_op.T
    return np.sqrt(np.mean(resid ** 2, axis=-1))


def step_height_m(dem: np.ndarray, window: int = 3) -> np.ndarray:
    z = np.asarray(dem, dtype=float)
    return maximum_filter(z, size=window, mode="nearest") - minimum_filter(z, size=window, mode="nearest")


def convexity_per_m(dem: np.ndarray, cell_size_m: float, smooth_sigma_cells: float = 1.0) -> np.ndarray:
    """Laplacian of the lightly smoothed DEM in 1/m. Negative on ridge crests and crater rims."""
    z = gaussian_filter(np.asarray(dem, dtype=float), smooth_sigma_cells, mode="nearest")
    p = np.pad(z, 1, mode="edge")
    lap = p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * z
    return lap / cell_size_m ** 2


def fill_invalid_nearest(dem: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Internal helper for the kernels only: copy the nearest valid height into gaps.

    The filled values never reach the output. Callers mask derived layers back to NaN where
    `valid` is False.
    """
    from scipy.ndimage import distance_transform_edt

    if not valid.any():
        raise ValueError("DEM has no valid cells")
    z = np.where(valid, np.nan_to_num(dem, nan=0.0), 0.0).astype(float)
    if valid.all():
        return z
    idx = distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return z[tuple(idx)]
