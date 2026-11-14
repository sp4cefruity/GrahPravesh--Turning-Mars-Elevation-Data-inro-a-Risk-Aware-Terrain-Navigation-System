"""Keep or drop run for the CNN experiment (specs/01-perception.md, "CNN experiment").

Run: python -m odyssey.perception.cnn_eval

Trains the Random Forest and the CNN on tiles T1 to T3 and scores them on held-out T4 and T5,
against the rule pseudo-labels. That measures how well each model imitates the rules on unseen
terrain. It is not accuracy against real terrain. Scenes use the simulated noise, bands and gaps
from the data stage (simulated, seed from the config). Writes outputs/cnn_eval.md.
"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter
from sklearn.ensemble import RandomForestClassifier

from ..config import PipelineConfig
from . import cnn
from .hazards import CLASS_NAMES, HAZARD_CLASSES, _rule_labels, compute_hazards
from .params import PerceptionParams
from .slope import convexity_per_m, fill_invalid_nearest, horn_slope_deg, roughness_m, step_height_m

TRAIN_TILES = ("T1", "T2", "T3")
TEST_TILES = ("T4", "T5")
K = len(CLASS_NAMES)


def expected_calibration_error(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Binary ECE: weighted gap between mean predicted probability and observed frequency per bin."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    err = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            err += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(err)


def macro_f1(y: np.ndarray, pred: np.ndarray, k: int) -> tuple[float, np.ndarray]:
    """Macro F1 over classes present in y, plus per-class F1 (NaN where the class is absent)."""
    per = np.full(k, np.nan)
    for c in range(k):
        if not (y == c).any():
            continue
        tp = ((pred == c) & (y == c)).sum()
        fp, fn = ((pred == c) & (y != c)).sum(), ((pred != c) & (y == c)).sum()
        per[c] = 2 * tp / (2 * tp + fp + fn)
    return float(np.nanmean(per)), per


def _tile(tile_id: str, config: PipelineConfig):
    from ..data.dem import load_tile
    from ..data.scene import build_scene
    p = config.perception
    grid, _ = build_scene(load_tile(tile_id), seed=config.seeds.data, noise_level=config.noise_level,
                          keep_clear=tuple(config.start))
    valid = np.asarray(grid.valid_mask, bool)
    dem = fill_invalid_nearest(grid.dem, valid)
    cs = grid.cell_size_m
    slope, rough = horn_slope_deg(dem, cs), roughness_m(dem, cs, p.rough_window_cells)
    step, convex = step_height_m(dem, p.rough_window_cells), convexity_per_m(dem, cs)
    rim = (convex < -p.rim_convexity_per_m) & (maximum_filter(slope, size=5, mode="nearest") > p.rim_slope_deg)
    labels = _rule_labels(slope, rough, rim, config.hard_block_slope_deg, p)
    return dict(grid=grid, valid=valid, labels=labels, feats=np.stack([slope, rough, step, convex], -1),
                chans=cnn.build_channels(dem, slope, rough, grid.bands, valid))


def _forest(train, test, p: PerceptionParams, seed: int):
    rng = np.random.default_rng(seed)
    x = np.concatenate([t["feats"][t["valid"]] for t in train])
    y = np.concatenate([t["labels"][t["valid"]] for t in train])
    sel = rng.choice(len(y), min(len(y), p.max_train_cells), replace=False)
    rf = RandomForestClassifier(n_estimators=p.n_trees, max_depth=p.max_depth, min_samples_leaf=p.min_samples_leaf,
                                random_state=seed, n_jobs=1).fit(x[sel], y[sel])
    out = []
    for t in test:
        f = t["feats"][t["valid"]]
        votes = np.zeros((K, len(f)))
        haz = np.zeros((len(rf.estimators_), len(f)))
        for i, tree in enumerate(rf.estimators_):
            lab = rf.classes_[tree.predict(f).astype(int)]
            votes[lab, np.arange(len(f))] += 1
            haz[i] = np.isin(lab, HAZARD_CLASSES)
        out.append((votes / len(rf.estimators_), haz.std(axis=0)))
    return out


def _cnn(train, test, p: PerceptionParams, seed: int):
    nets = [cnn.train_member([(t["chans"], t["labels"], t["valid"]) for t in train], seed + i, K, p)
            for i in range(p.cnn_members)]
    out = []
    for t in test:
        probs, std = cnn.predict_members(nets, t["chans"], t["valid"], HAZARD_CLASSES)
        out.append((probs[:, t["valid"]], std[t["valid"]]))
    return out


def _score(y, probs, std):
    pred = probs.argmax(axis=0)
    p_haz = probs[list(HAZARD_CLASSES)].sum(axis=0)
    y_haz = np.isin(y, HAZARD_CLASSES).astype(int)
    f1, per = macro_f1(y, pred, K)
    wrong = pred != y
    return dict(acc=float((pred == y).mean()), f1=f1, per=per, ece=expected_calibration_error(p_haz, y_haz),
                brier=float(((p_haz - y_haz) ** 2).mean()),
                std_wrong=float(std[wrong].mean()) if wrong.any() else float("nan"),
                std_right=float(std[~wrong].mean()), pred=pred)


def main() -> str:
    config = PipelineConfig()
    p = config.perception
    seed = config.seeds.perception
    tiles = {t: _tile(t, config) for t in TRAIN_TILES + TEST_TILES}
    train, test = [tiles[t] for t in TRAIN_TILES], [tiles[t] for t in TEST_TILES]
    ytest = [t["labels"][t["valid"]] for t in test]

    t0 = time.perf_counter()
    rf_out = _forest(train, test, p, seed)
    t_rf = time.perf_counter() - t0
    t0 = time.perf_counter()
    cnn_out = _cnn(train, test, p, seed)
    t_cnn = time.perf_counter() - t0

    lines = ["# CNN keep or drop run", "",
             f"Train {', '.join(TRAIN_TILES)}, held out {', '.join(TEST_TILES)}. Scored against rule pseudo-labels "
             "(imitation of the rules, not real terrain accuracy). Scenes use simulated noise and bands. "
             f"CNN params: {p.cnn_members} members, {p.cnn_epochs} steps, batch {p.cnn_batch}, untuned.", "",
             "## Rule label share per tile (valid cells)", "",
             "| tile | " + " | ".join(CLASS_NAMES.values()) + " |", "|---|" + "---|" * K]
    for tid, t in tiles.items():
        share = np.bincount(t["labels"][t["valid"]], minlength=K) / t["valid"].sum()
        lines.append(f"| {tid} | " + " | ".join(f"{s:.3f}" for s in share) + " |")

    lines += ["", "## Held-out scores", "",
              "| tile | model | accuracy | macro F1 | ECE (hazard classes) | Brier | std on wrong | std on right |",
              "|---|---|---|---|---|---|---|---|"]
    rows = {}
    for name, out in (("forest", rf_out), ("cnn", cnn_out)):
        for tid, y, (probs, std) in zip(TEST_TILES, ytest, out):
            s = rows[(name, tid)] = _score(y, probs, std)
            lines.append(f"| {tid} | {name} | {s['acc']:.3f} | {s['f1']:.3f} | {s['ece']:.3f} | {s['brier']:.3f} | "
                         f"{s['std_wrong']:.3f} | {s['std_right']:.3f} |")
        s = rows[(name, "all")] = _score(np.concatenate(ytest), np.concatenate([o[0] for o in out], axis=1),
                                         np.concatenate([o[1] for o in out]))
        lines.append(f"| T4+T5 | {name} | {s['acc']:.3f} | {s['f1']:.3f} | {s['ece']:.3f} | {s['brier']:.3f} | "
                     f"{s['std_wrong']:.3f} | {s['std_right']:.3f} |")

    lines += ["", "## Per-class F1 on T4+T5 (blank = class absent)", "",
              "| model | " + " | ".join(CLASS_NAMES.values()) + " |", "|---|" + "---|" * K]
    for name in ("forest", "cnn"):
        per = rows[(name, "all")]["per"]
        lines.append(f"| {name} | " + " | ".join("" if np.isnan(v) else f"{v:.3f}" for v in per) + " |")

    a, b = rows[("forest", "all")]["pred"], rows[("cnn", "all")]["pred"]
    lines += ["", "## Agreement, forest vs CNN, T4+T5", "",
              f"- same class: {(a == b).mean():.3f}",
              f"- same hazard or not-hazard call: {(np.isin(a, HAZARD_CLASSES) == np.isin(b, HAZARD_CLASSES)).mean():.3f}"]

    # Pipeline path: each model fits the scene it predicts, as compute_hazards does. Timed on T1.
    grid = tiles["T1"]["grid"]
    t0 = time.perf_counter()
    _, h_rf = compute_hazards(grid, config)
    t_pipe_rf = time.perf_counter() - t0
    cfg_cnn = dataclasses.replace(config, perception=dataclasses.replace(p, classifier="cnn"))
    t0 = time.perf_counter()
    _, h_cnn = compute_hazards(grid, cfg_cnn)
    t_pipe_cnn = time.perf_counter() - t0
    codes_ok = set(np.unique(h_cnn.evidence_code).tolist()) <= set(h_cnn.evidence)
    lines += ["", "## Pipeline path on T1 (fit and predict the same scene)", "",
              f"- compute_hazards forest: {t_pipe_rf:.2f} s, cnn: {t_pipe_cnn:.2f} s",
              f"- held-out run time, train plus predict: forest {t_rf:.2f} s, cnn {t_cnn:.2f} s",
              f"- every CNN evidence code has a legend entry: {codes_ok}",
              f"- hard_block cells, forest {int(h_rf.hard_block.sum())}, cnn {int(h_cnn.hard_block.sum())}",
              f"- cells where forest and CNN disagree on hard_block: {int((h_rf.hard_block != h_cnn.hard_block).sum())}"]

    f, c = rows[("forest", "all")], rows[("cnn", "all")]
    checks = [("1 macro F1 at least the forest", c["f1"] >= f["f1"]), ("2 ECE no worse", c["ece"] <= f["ece"]),
              ("3 std higher on wrong cells", c["std_wrong"] > c["std_right"]), ("4 evidence codes work", codes_ok)]
    lines += ["", "## Keep rule (check 5, runtime, is judged from the timings above)", ""]
    lines += [f"- {n}: {'pass' if ok else 'FAIL'}" for n, ok in checks]
    text = "\n".join(lines) + "\n"
    out = Path(__file__).parents[3] / "outputs" / "cnn_eval.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    return text


if __name__ == "__main__":
    main()
