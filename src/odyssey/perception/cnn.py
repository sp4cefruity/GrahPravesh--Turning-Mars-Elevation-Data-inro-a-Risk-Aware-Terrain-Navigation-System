"""Small CNN terrain classifier, an experiment beside the Random Forest (specs/01-perception.md).

Same job as `hazards._forest_votes`: learn the rule pseudo-labels and return
(class_probs (K, H, W), epistemic_std (H, W)). Accuracy against those labels measures how well
the net imitates the rules, not how well it knows real terrain.

The net is fully convolutional, so it trains on random 32 by 32 patches and runs on the whole
grid. Three conv layers, receptive field of 7 cells. A 3-member ensemble (seeds seed, seed+1, ...)
gives the mean class probabilities. epistemic_std is the spread of the hazard probability
(classes 3 and 4) over the members.
"""

from __future__ import annotations

import importlib.util

import numpy as np
from scipy.ndimage import uniform_filter

from .params import PerceptionParams

BAND_NAMES = ("b1", "b2", "b3", "b4", "b5")  # real bands only, the simulated ones stay out of v1
RELIEF_WINDOW = 33  # DEM channel is the DEM minus its local mean, so absolute height does not leak in


def torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def build_channels(dem, slope, rough, bands: dict, valid: np.ndarray) -> np.ndarray:
    """(C, H, W) float32: relief, slope, roughness, b1 to b5 (zeros if absent), validity. Invalid cells are 0."""
    relief = dem - uniform_filter(dem, RELIEF_WINDOW, mode="nearest")
    chans = [relief, slope, rough] + [np.asarray(bands.get(b, np.zeros(dem.shape)), dtype=float) for b in BAND_NAMES]
    out = []
    for c in chans:
        c = np.where(valid, np.nan_to_num(c), 0.0)
        sd = c[valid].std()
        out.append(np.where(valid, (c - c[valid].mean()) / (sd if sd > 1e-9 else 1.0), 0.0))
    out.append(valid.astype(float))
    return np.stack(out).astype(np.float32)


def _make_net(n_in: int, k: int, p: PerceptionParams):
    from torch import nn
    w = p.cnn_width
    return nn.Sequential(
        nn.Conv2d(n_in, w, 3, padding=1), nn.ReLU(), nn.Dropout2d(p.cnn_dropout),
        nn.Conv2d(w, w, 3, padding=2, dilation=2), nn.ReLU(),
        nn.Conv2d(w, k, 1),
    )


def class_weights(labels: np.ndarray, valid: np.ndarray, k: int, mode: str) -> np.ndarray:
    """Per-class loss weights from label frequency on valid cells, scaled so the mean weight per cell is 1."""
    if mode not in ("none", "sqrt_inverse", "inverse"):
        raise ValueError(f"unknown class weight mode {mode!r}, use 'none', 'sqrt_inverse' or 'inverse'")
    if mode == "none":
        return np.ones(k)
    freq = np.bincount(labels[valid], minlength=k) / max(int(valid.sum()), 1)
    w = np.where(freq > 0, 1.0 / np.maximum(freq, 1e-12), 0.0) ** (1.0 if mode == "inverse" else 0.5)
    return np.where(freq > 0, w / (w * freq).sum(), 1.0)  # classes never seen get 1, they never appear in the loss


def train_member(grids, seed: int, k: int, p: PerceptionParams):
    """Train one net on random patches drawn from one or more (channels, labels, valid) grids."""
    import torch
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    n_in = grids[0][0].shape[0]
    net = _make_net(n_in, k, p)
    opt = torch.optim.Adam(net.parameters(), lr=p.cnn_lr)
    data = [(torch.from_numpy(x), torch.from_numpy(np.where(v, y, -1).astype(np.int64))) for x, y, v in grids]
    pooled_y = np.concatenate([y[v] for _, y, v in grids])
    w = class_weights(pooled_y, np.ones(pooled_y.shape, dtype=bool), k, p.cnn_class_weight)
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(w, dtype=torch.float32), ignore_index=-1)  # -1 is invalid
    net.train()
    for _ in range(p.cnn_epochs):
        xs, ys = [], []
        for g in rng.integers(0, len(data), p.cnn_batch):
            xt, yt = data[g]
            _, h, w = xt.shape
            ps = min(p.cnn_patch, h, w)
            i, j = rng.integers(0, h - ps + 1), rng.integers(0, w - ps + 1)
            xs.append(xt[:, i:i + ps, j:j + ps])
            ys.append(yt[i:i + ps, j:j + ps])
        opt.zero_grad()
        loss_fn(net(torch.stack(xs)), torch.stack(ys)).backward()
        opt.step()
    net.eval()
    return net


def predict_members(nets, channels: np.ndarray, valid: np.ndarray, hazard_classes: tuple[int, ...]):
    """Return (class_probs (K, H, W), epistemic_std (H, W)) from trained members. Invalid cells get 0."""
    import torch
    with torch.no_grad():
        members = np.stack([torch.softmax(n(torch.from_numpy(channels)[None]), dim=1)[0].numpy() for n in nets])
    probs = members.mean(axis=0) * valid
    std = members[:, list(hazard_classes)].sum(axis=1).std(axis=0) * valid  # spread of the hazard probability
    return probs.astype(float), std.astype(float)


def cnn_votes(channels: np.ndarray, labels: np.ndarray, valid: np.ndarray, seed: int, k: int,
              hazard_classes: tuple[int, ...], p: PerceptionParams) -> tuple[np.ndarray, np.ndarray]:
    """Train the ensemble on this grid and predict it, like the forest does in the pipeline."""
    nets = [train_member([(channels, labels, valid)], seed + i, k, p) for i in range(p.cnn_members)]
    return predict_members(nets, channels, valid, hazard_classes)
