"""Dashboard export (owner: Udit). Turns PipelineResults into plain JSON for the HTML dashboard.

Writes, under outputs/web/ by default:
  index.json       list of scenarios and the default one
  <scenario>.json  one scenario, same field names as the contracts in docs/ARCHITECTURE.md
  bundle.js        the same content as a script tag payload (window.ODYSSEY_BUNDLE), so the page
                   works when opened from disk, where fetch() is blocked in most browsers

Encoding
  Grids become {"shape": [H, W], "dtype": ..., "data": base64}. Floats are little-endian float32
  with NaN for missing. Bool grids use dtype "bool_packbits": row-major, numpy packbits order
  (most significant bit first), unpack with H*W bits and ignore the padding. Ints are int16.
  Scalars that are inf or NaN become null (strict JSON). A null path cost means no safe path.
  If a scenario failed, its file holds `error` (stage and reason) and no grids.

Scenarios
  noise level (default 0, 1, 2) times missing data (off, on). The missing data patch is the one
  the Streamlit dashboard uses (view.missing_patch), labelled simulated. Both rover modes carry
  their own ranking in `targets_by_mode`, because ranks move with the mode.

Run:  python -m odyssey.export [--noise 0 1 2] [--no-missing] [--out outputs/web]
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import json
import math
from pathlib import Path
from typing import Any, Optional

import numpy as np

from . import contracts as C
from .config import PipelineConfig

DEFAULT_NOISE = (0.0, 1.0, 2.0)


# ---------------------------------------------------------------- encoding


def encode_grid(arr: np.ndarray) -> dict[str, Any]:
    a = np.asarray(arr)
    if a.dtype == bool:
        raw, dtype = np.packbits(a.ravel()).tobytes(), "bool_packbits"
    elif a.dtype.kind in "iu":
        raw, dtype = a.astype("<i2").tobytes(), "int16"
    else:
        raw, dtype = a.astype("<f4").tobytes(), "float32"
    return {"shape": list(a.shape), "dtype": dtype, "data": base64.b64encode(raw).decode("ascii")}


def _num(x: Any) -> Any:
    if isinstance(x, (float, np.floating)):
        return float(x) if math.isfinite(x) else None
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def to_plain(obj: Any) -> Any:
    """Dataclasses, tuples and numpy scalars to JSON types. Arrays become encoded grids."""
    if isinstance(obj, np.ndarray):
        return encode_grid(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    return _num(obj)


def _path_plain(pr: C.PathResult, with_corridor: bool) -> dict[str, Any]:
    d = to_plain(pr)
    if not with_corridor:
        d["corridor_mask"] = None
    return d


# ---------------------------------------------------------------- one scenario


def scenario_name(noise: float, missing: bool) -> str:
    return f"n{noise:g}_{'missing' if missing else 'full'}".replace(".", "p")


def result_to_bundle(res: C.PipelineResult, noise: float, missing: bool) -> dict[str, Any]:
    from .dashboard import view  # Streamlit free helpers, reused so the ranking matches the old UI

    head = {"scenario": scenario_name(noise, missing), "noise_level": noise, "missing_data": missing,
            "config_hash": res.config.config_hash(), "config": to_plain(res.config)}
    if not res.complete:
        return {**head, "complete": False, "error": to_plain(res.error), "notes": list(res.notes),
                "timings_s": to_plain(res.timings_s)}

    t, hz, cm = res.terrain, res.hazards, res.cost_map
    grids = {
        "dem": t.dem, "slope_deg": t.slope_deg, "roughness": t.roughness, "valid_mask": t.valid_mask,
        "hazard_prob": hz.hazard_prob, "terrain_class": hz.terrain_class,
        "slope_std_deg": hz.slope_std_deg, "hard_block": hz.hard_block,
        "cost_mean": cm.cost_mean, "cost_std": cm.cost_std, "blocked": cm.blocked,
    }
    targets_by_mode: dict[str, Any] = {}
    rank_notes: dict[str, str] = {}
    default_by_mode: dict[str, Optional[str]] = {}
    for mode in C.MODES:
        ranked, note = view.targets_for_mode(res, mode)
        targets_by_mode[mode] = to_plain(ranked)
        rank_notes[mode] = note
        default_by_mode[mode] = view.default_target(res, ranked, mode)

    paths = {cid: {m: _path_plain(pr, with_corridor=True) for m, pr in by.items()}
             for cid, by in res.paths.items()}
    return {
        **head,
        "complete": True,
        "error": None,
        "shape": list(t.shape),
        "cell_size_m": t.cell_size_m,
        "source": t.source,
        "simulated_layers": list(t.simulated_layers),
        "start": list(res.start),
        "grids": {k: encode_grid(v) for k, v in grids.items() if v is not None},
        "bands": {k: encode_grid(v) for k, v in t.bands.items()},
        "evidence_legend": {str(k): v for k, v in hz.evidence.items()},
        "evidence_code": encode_grid(hz.evidence_code) if hz.evidence_code is not None else None,
        "candidates": to_plain(res.candidates),
        "targets": to_plain(res.targets),
        "targets_by_mode": targets_by_mode,
        "rank_notes": rank_notes,
        "default_target_id": res.default_target_id,
        "default_target_by_mode": default_by_mode,
        "paths": paths,
        "risk_curve": to_plain(res.risk_curve),
        "baseline_paths": {k: _path_plain(v, with_corridor=False) for k, v in res.baseline_paths.items()},
        "notes": list(res.notes),
        "timings_s": to_plain(res.timings_s),
    }


# ---------------------------------------------------------------- the whole export


def export_all(config: Optional[PipelineConfig] = None, noise_levels: tuple[float, ...] = DEFAULT_NOISE,
               include_missing: bool = True, out_dir: str | Path = "outputs/web") -> Path:
    from .dashboard import view

    config = config or PipelineConfig()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scenarios: list[dict[str, Any]] = []
    bundles: dict[str, Any] = {}
    for noise in noise_levels:
        for missing in ((False, True) if include_missing else (False,)):
            name = scenario_name(noise, missing)
            res = view.run_scenario(config, view.Scenario(noise=float(noise), missing_data=missing))
            b = result_to_bundle(res, float(noise), missing)
            (out / f"{name}.json").write_text(json.dumps(b, allow_nan=False), encoding="utf-8")
            bundles[name] = b
            scenarios.append({"name": name, "noise_level": noise, "missing_data": missing,
                              "file": f"{name}.json", "config_hash": b["config_hash"],
                              "complete": b["complete"]})
            print(f"{name}: {'ok' if b['complete'] else 'FAILED ' + str(b['error'])}")
    ok = [s for s in scenarios if s["complete"]]
    base_noise = min(noise_levels, key=lambda v: abs(v - config.noise_level))
    default = scenario_name(base_noise, False)
    if default not in {s["name"] for s in ok} and ok:
        default = ok[0]["name"]
    index = {"scenarios": scenarios, "default": default,
             "grid_encoding": "see src/odyssey/export.py docstring"}
    (out / "index.json").write_text(json.dumps(index, allow_nan=False), encoding="utf-8")
    payload = json.dumps({"index": index, "scenarios": bundles}, allow_nan=False)
    (out / "bundle.js").write_text(f"window.ODYSSEY_BUNDLE = {payload};\n", encoding="utf-8")
    print(f"wrote {len(scenarios)} scenarios to {out} (default {default})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Export pipeline results as JSON for the HTML dashboard.")
    ap.add_argument("--config", help="JSON config file (defaults are used if omitted)")
    ap.add_argument("--noise", type=float, nargs="+", default=list(DEFAULT_NOISE))
    ap.add_argument("--no-missing", action="store_true", help="skip the missing data scenarios")
    ap.add_argument("--out", default="outputs/web")
    args = ap.parse_args()
    cfg = PipelineConfig.from_json(args.config) if args.config else PipelineConfig()
    export_all(cfg, tuple(args.noise), not args.no_missing, args.out)


if __name__ == "__main__":
    main()
