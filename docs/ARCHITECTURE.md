# Architecture (owner: Udit)

Status: **approved** by Udit. This file now includes the hackathon build plan from `docs/HACKATHON_BUILD_PLAN.md`. Contracts freeze at 2:15 AM. After that, any change needs both owners to agree.

Background and citations live in `docs/MODEL_AND_BASELINE_PLAN.md`. Section tags like `[Plan §6.3]` point there. The hour-by-hour workflow stays in `docs/HACKATHON_BUILD_PLAN.md` section 6 and `docs/TIMELINE.md`.

## Core idea

Uncertainty is carried end to end. Perception gives probabilities. Those become a cost with a spread. The planner trades risk against path length with one visible dial. Science ranks come with intervals. Every piece maps to a judging criterion in `docs/EVALUATION_MAP.md`.

## Data flow

```
 Real HiRISE DTM tile (crop 512x512, about 1 to 2 m cells)
   + simulated spectral bands, ice signal, noise, gaps (tagged "simulated")
            |
 [data]       load, crop, reproject, valid_mask, seeds --------------> TerrainGrid (raw)
            |
 [perception] Horn slope, roughness, step height, aspect
            |  terrain classes: rules plus Random Forest (tree-vote variance = epistemic std)
            |  P_haz = 1 - (1 - P_slope)(1 - P_rough)(1 - P_class)
            |  hard_block = slope > limit OR crater rim OR P_haz > delta  (Disha)
            v                                                          HazardMap (no slope_std yet)
 [uncertainty] DEM Monte Carlo (spatially correlated noise, 50 to 100 draws)   (Disha)
            |  calls the perception slope kernel, stores mean and std only
            v                                                          HazardMap.slope_std_deg filled
 [planning]  cost map: cost_mean and cost_std built from slope, roughness, P_haz,
            |  slope_std_deg and epistemic_std (first order propagation)   (Udit)
            |  hard blocks stay separate from soft weights
            v                                                          CostMap
 [science 1] candidates from simulated ice and mineral bands plus geomorphic cues,
            |  value with feature noise (no path cost yet)             (Saptarshi)
            v                                                          candidate list
 [planning]  edge cost = mean + std * phi(z_alpha) / (1 - alpha)   (Gaussian CVaR)
            |  8-connected A* (numba optional), Dijkstra cross-check
            |  distance-growing inflation of blocked cells (IROS 2022 drift margin)
            |  one path per candidate, bold and cautious
            |  corridor = cells where D_start + D_goal <= (1 + tau) * best cost
            |  safety verifier on true hazards, risk-vs-length curve over alpha
            v                                                          PathResult per candidate
 [science 2] access cost = path CVaR, then Monte Carlo ranking (1000 draws):
            |  rank interval, P(top 3), evidence string
            v                                                          ScienceTarget[]
 [export]    pipeline writes one JSON bundle per scenario (grids as base64 arrays)   (Udit)
            v                                                          outputs/web/
 [dashboard] static HTML and JS page reads the bundle: cost map, std map, paths, corridor,
             targets with error bars, bold or cautious dial, noise slider, click-to-trace

 Side track DROPPED (Nov 14, by Udit): SegFormer-B0 on an AI4Mars subset. No code was written.
 Uncertainty for terrain classes comes from the Random Forest vote spread only.
```

`pipeline.py` runs the stages in order and returns one `PipelineResult`. Run it once per config and serialise the result, so the demo loads instantly and cannot fail live.

Pipeline order, fixed (science needs path costs, and the planner needs goals, so science runs in two steps): data, perception, uncertainty, cost map, science candidates, planning (one path per candidate), science ranking, planning extras (step 8: baselines B0 and B1 and the risk curve, run last because they need the default goal, which is the top ranked target). The path shown by default goes to the top ranked target. The dashboard can show any precomputed candidate path.

Ownership changes (decided by Udit on Nov 14): the DEM Monte Carlo lives in the `uncertainty` module and is now owned by Disha, because it wraps her slope kernel. Saptarshi owns data and science (including the 1000 draw ranking Monte Carlo). Udit builds the cost map (`cost_mean`, `cost_std`) from Disha's fields. Disha computes `hard_block`.

## Modules and owners

| Module | Folder | Owner | Job |
|---|---|---|---|
| data | `src/odyssey/data/` | Saptarshi | Load the DEM tile, simulated bands, ice signal, noise, gaps, seeds, cache, synthetic DEM fallback |
| perception | `src/odyssey/perception/` | Disha | Horn slope, roughness, step, aspect, rules, Random Forest classes, hazard probability, hard block |
| uncertainty | `src/odyssey/uncertainty/` | Disha | DEM Monte Carlo, `slope_std_deg` |
| planning | `src/odyssey/planning/` | Udit | Cost map (`cost_mean`, `cost_std`), CVaR edge cost, A*, Dijkstra, inflation, corridor, baselines B0 and B1, safety verifier, risk curve |
| science | `src/odyssey/science/` | Saptarshi | Candidates, value, ranking Monte Carlo, evidence strings |
| dashboard | `src/odyssey/dashboard/` | Disha | Interactive UI in plain HTML, CSS and JavaScript (`web/`), no build step, no server needed to view it |
| pipeline | `src/odyssey/pipeline.py` | Udit | Orchestration, config, seeds, serialisation, JSON export for the dashboard |

## Contracts (frozen at 2:15 AM)

All grids are NumPy arrays of shape (H, W), same orientation, same cell size in meters.

- `TerrainGrid`: `dem`, `slope_deg`, `roughness`, `aspect`, `bands` (dict of simulated spectral arrays), `valid_mask` (False where data is missing), `cell_size_m`, `simulated_layers` (names of simulated layers). Additive: `source` (where the DEM came from, "synthetic" for the fallback)
- `HazardMap` (Disha, all fields including `slope_std_deg` and `hard_block`): `hazard_prob` (0 to 1), `terrain_class` (int labels), `class_probs` (K, H, W), `epistemic_std`, `slope_std_deg`, `hard_block` (bool, steep or crater rim), `evidence_code` ((H, W) int, which rule or model fired per cell), `evidence` (legend: code to rule or model note)
- `CostMap` (Udit): `cost_mean`, `cost_std`, `p_haz`, `blocked` (bool). `blocked` = `HazardMap.hard_block` OR `~valid_mask`, then inflated by the planner.
- `PathResult` (Udit): `cells` (list of (row, col)), `total_cost`, `risk_score`, `max_slope_on_path`, `safe` (bool from verification), `planner` ("astar" or "dijkstra"), `mode` ("bold" or "cautious"), `alpha`, `corridor_mask` (bool), `min_feasible_risk` (used when no safe path exists), `baseline` ("b0", "b1" or None). Additive, all with defaults: `candidate_id`, `no_safe_path_reason` (set when there is no safe path), `segments` (list of `SegmentCost`: from_cell, to_cell, length_cells, base, mean, risk_term, edge_cost, slope_deg, p_haz), `nodes_expanded`, `dijkstra_cost`, `dijkstra_nodes_expanded` (optimality cross-check)
- `Candidate` (Saptarshi, science step 1 output, value only, no path cost): `id`, `location` (row, col), `kind` ("ice" or "geology"), `value_mean`, `value_ci` (low, high), `evidence` (string)
- `ScienceTarget` (Saptarshi): `id`, `location`, `value_mean`, `value_ci` (low, high), `path_cost`, `score`, `score_ci`, `rank_interval` (low, high), `p_top3`, `evidence` (string), `kind` ("ice" or "geology")
- `PipelineResult` (Udit): all of the above plus `risk_curve` (list of alpha, path_length, hazard_violation_rate), `baseline_paths`, and `config` (seeds, weights, thresholds) so a run can be reproduced. Additive fields: `terrain`, `hazards`, `cost_map`, `candidates`, `paths` (`paths[candidate_id][mode]` is a `PathResult`), `targets` (sorted best first), `default_target_id` (top ranked target with a safe cautious path), `start` (config.start, default (8, 8)), `timings_s`, `notes`, `error` (`StageFailure` with stage name and reason) and the property `complete` (True when `error` is None). The dashboard shows output only when `complete` is True. `risk_curve` items are `RiskCurvePoint`. `baseline_paths` is keyed "b0" and "b1".

## Dashboard data export (new, needed by the HTML and JS dashboard)

The pickle in `pipeline.save_result` is for Python only. The browser needs a plain format, so the pipeline gets an export step.

- `outputs/web/index.json` lists the scenarios (noise level, missing data flag, file name, config hash) and the default one.
- `outputs/web/<scenario>.json` holds one `PipelineResult`. Grids (`cost_mean`, `cost_std`, `hazard_prob`, `slope_std_deg`, `dem`, `blocked`, `corridor_mask`) are written as `{shape, dtype, data}` with base64 little-endian bytes, NaN for missing. Small objects (`targets`, `paths`, `segments`, `risk_curve`, `baseline_paths`, `config`, `timings_s`, `error`) are plain JSON, with the same field names as the contracts above.
- Simulated layer names and `source` are included so the page can label them.
- If `error` is set, the bundle holds the stage name and reason and no grids. The page shows the reason.
- Open question: serving. Opening `index.html` from disk blocks `fetch` in most browsers, so the page is served with `python -m http.server` from `outputs/web/` (or the bundle is inlined into a script tag as a fallback). Disha and Udit to pick one.

## Planner details

- Bold mode is `alpha = 0`. Cautious mode is `alpha = 0.95`. One dial, shown in the UI.
- Baseline B0: slope threshold plus A*. Baseline B1: reference reproduction of the Electronics paper (Brad and Balog 2025), `cost = z / (friction + eps)`. Both are shown beside the proposed path in the demo. Dijkstra is the optimality check.
- If no safe path exists, return a "no safe path" result with `min_feasible_risk` and the reason. Never return a risky path.

## Components (free and open source)

| Need | Pick |
|---|---|
| Raster I/O, crop, reproject | `rasterio` with GDAL, `numpy`, `scipy` |
| Slope and roughness | Our own numpy Horn kernel (skip `richdem`, it is GPL-3.0) |
| Correlated noise | `scipy.ndimage.gaussian_filter` on white noise |
| Terrain classifier, main | `scikit-learn` RandomForest or `lightgbm`, per-tree votes give variance |
| Terrain classifier, side track | Dropped. Was SegFormer-B0 on AI4Mars |
| Calibration and conformal | `torchmetrics` CalibrationError, hand-rolled temperature scaling, `MAPIE` (stretch) |
| Planner | Our own A* and Dijkstra with `numba`, `scipy.sparse.csgraph.dijkstra` for corridor distances |
| Dashboard | Static HTML, CSS and JavaScript. Plotly.js (vendored, works offline) or canvas for the maps. The old Streamlit page is kept only until the HTML version replaces it |
| Repro | seeds in config, `pytest`, `make demo` |

## Compute notes

- Nothing needs a GPU. The SegFormer side track that would have used one was dropped.
- Store only mean and std from Monte Carlo, never all draws.
- Planning searches at most 256 by 256 (`planning_grid_size` in config). Larger inputs are block-reduced inside `plan_paths` and `plan_extras`, then routes are refined back to full resolution. `TerrainGrid`, `HazardMap`, `CostMap` and every returned path stay full resolution, and the final safety check uses the full resolution blocked mask (spec 02, requirement 11). A 512 input with 5 candidates plans in about 4.5 s. numba is optional and not required.
- Cap the execution simulation at 50 start-goal pairs by 100 draws, or 20 pairs if slow.
- The dashboard never recomputes. Each scenario (noise level, missing data on or off) is precomputed by the pipeline and exported ahead of time, and the page switches between the saved bundles. This keeps the demo fast and unable to fail live.

## Data

- DEM: Jezero HiRISE pair DTM `DTEEC_023524_1985_023379_1985_U01` (about 700 MB) or the USGS Mars Sample Return mosaic. Saptarshi starts the download first and confirms the tile with Disha. Fallback is a seeded synthetic fractal and crater DEM so the demo is never blocked.
- Spectral, ice and noise layers are simulated and labelled as such.
- AI4Mars is not used (side track dropped). Do not claim any rover-camera model.

## Design principles

- Deterministic runs: every random step takes a seed from config.
- Uncertainty is part of every type, not an add-on.
- Hard safety rules are separate from soft cost weights, so a bad weight can never produce an unsafe path.
- Simulated inputs are tagged in the data so the UI and README can say so.

## Working values (assumptions, set in one config file)

- Hard block at 25 degrees slope. Soft-cost slope scale `theta_max` of 15 degrees. Both get a sensitivity sweep.
- Final numbers are cited by Disha in `docs/RESEARCH_NOTES.md` when decided. Until then they are labelled assumptions.

## Assumptions and limits (carry into README)

- One DEM tile, one rover, static map, no wheel slip or power model.
- Spectral and ice layers are simulated. Science ranks say nothing about real Mars.
- Slope limits, class multipliers and weights are assumptions, not fitted to rover data.
- CVaR here is edge-wise and Gaussian. It is conservative but not a formal safety guarantee.
- No public orbital terrain labels were found, so orbital classes come from rules plus a model trained on rule-derived pseudo-labels, not human ground truth.
- AI4Mars class codes and rover slope limits are unverified.

## Cut order if late

SegFormer side track, Dijkstra view, B1 baseline view, conformal wrapper, 3D polish, extra target categories.

Never cut: cost map with std, hazard-avoiding path, ranked targets with intervals, the cautious and bold dial, README limits, backup video.
