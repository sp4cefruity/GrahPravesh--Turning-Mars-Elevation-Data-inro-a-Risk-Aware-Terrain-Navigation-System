# Hackathon Build Plan (trimmed from MODEL_AND_BASELINE_PLAN.md)

Status: proposal for Udit to approve and fold into `docs/ARCHITECTURE.md` and the specs before the 2:15 AM contract freeze. Full survey, citations and caveats are in `docs/MODEL_AND_BASELINE_PLAN.md`; section tags below like `[Plan §6.3]` point there.

## 0. What we keep and what we cut

The base concept that earns points is **uncertainty carried end to end**: perception gives probabilities, those become a cost with a spread, the planner trades risk against length with a visible dial, and science ranks come with intervals. Every "angle" below maps to a judging criterion in `docs/EVALUATION_MAP.md`.

| Keep (the angles) | Cheap hackathon form | Cut or defer |
|---|---|---|
| Physically-based hazards (slope, roughness, step) | Numpy Horn slope on one cropped DEM tile | Footprint-scale wheel model |
| DEM uncertainty | Monte Carlo with spatially correlated noise, 50 to 100 draws | Full PDS artifact masking |
| Learned terrain classes with calibrated uncertainty | Random Forest vote variance on the DEM tile (main). SegFormer-B0 on an AI4Mars subset (side track, kill at 4:00 AM) | 5-model ensembles, evidential heads, orbital hand-labelling |
| Risk-aware planning (CVaR) | Closed-form Gaussian CVaR edge cost, one `alpha` dial. Cautious mode is `alpha=0.95`, bold is `alpha=0` | Monte Carlo CVaR, chance-constrained Lagrangian, RRT*, FMM |
| Localization drift margin (IROS 2022) | Distance-based inflation of blocked cells, one confidence knob | Fixed-point iteration |
| Baselines | B0 (slope threshold + A*) and B1 (Electronics-paper cost) shown side by side, Dijkstra as the optimality check | RRT* comparison |
| Corridor | Two-Dijkstra cost-tolerance corridor | Similarity band |
| Science ranking with intervals | Monte Carlo (1000 draws) over feature noise and weights, rank intervals, `P(top 3)` | Orienteering tour |
| Conformal guarantee | `MAPIE` conformal on hazard recall if time allows (stretch) | Conformal risk control for segmentation |

## 1. Hardware reality and where each thing runs

| Person | Machine | Use it for |
|---|---|---|
| Disha | MacBook Air M2, 16 GB, no CUDA (PyTorch `mps` backend works) | Data prep, DEM layers, Random Forest classifier, dashboard-free work. Do not train deep models on it |
| Udit | Ryzen 7 PRO 7840U laptop, 16 GB, no usable GPU, **100 AWS credits** | Planner, pipeline, integration. If the SegFormer side track runs, rent one GPU instance (for example a single-GPU `g5.xlarge` class; price and quota not verified, check the console) and stop it after training |
| Saptarshi | i5-12450H, RTX 3050 4 GB, 16 GB (CUDA) | Fine-tune SegFormer-B0 with small batches and `fp16` autocast. Monte Carlo and dashboard |

All core stages are CPU-light at 512 by 512 (A* with numba is milliseconds; 100 slope Monte Carlo draws is seconds). Nothing in the main path needs a GPU. Install `torch` per machine (MPS, CUDA, CPU).

## 2. Architecture

```
 Real HiRISE DTM tile (crop 512x512, ~1-2 m cells)
   + simulated spectral bands, ice signal, noise, gaps (tagged "simulated")
            │
 [data]      load, crop, reproject, valid_mask, seeds ─────────────► TerrainGrid
            │
 [perception] Horn slope θ, roughness ρ, step h, aspect
            │  DEM Monte Carlo (correlated noise) ─► θ mean/std
            │  Terrain classes: rules ∪ Random Forest (tree-vote = epistemic var)
            │  P_haz = 1 - Π(1 - P_slope)(1 - P_rough)(1 - P_class)
            ▼                                                        HazardMap
 [uncertainty] cost_mean μ, cost_std σ from slope, roughness, class mixture
            │  hard_block = slope > limit OR P_haz > δ  (separate from soft weights)
            ▼                                                        CostMap
 [planning]  edge cost = μ + σ·φ(zα)/(1-α)   (Gaussian CVaR, α from mode)
            │  8-connected A* (numba), Dijkstra cross-check
            │  distance-growing blocked-cell inflation (IROS 2022)
            │  corridor = {D_s + D_g ≤ (1+τ)·C*}
            │  safety verifier on truth hazards, risk-vs-length curve over α
            ▼                                                        PathResult
 [science]   candidates from simulated ice/mineral bands + geomorphic cues
            │  value with feature noise, access cost = path CVaR
            │  Monte Carlo ranking: rank interval, P(top 3), evidence string
            ▼                                                        ScienceTarget[]
 [dashboard] Streamlit + Plotly: cost map, σ map, path(s), corridor, targets with
             error bars, bold/cautious toggle, noise slider, click-to-trace

 Side track B (surface perception): SegFormer-B0 on AI4Mars subset → softmax,
 entropy, calibration plot, rover-view panel in dashboard. Optional.
```

### Contract additions (proposal to Udit; existing fields unchanged)

- `HazardMap`: add `class_probs` (K,H,W), `epistemic_std` (H,W), `slope_std_deg` (H,W).
- `CostMap`: keep `cost_mean`, `cost_std`, `blocked`. Add `p_haz`.
- `PathResult`: add `alpha`, `corridor_mask` (bool H,W), `min_feasible_risk` (float, for the no-path fallback), `baseline` ("b0", "b1" or None).
- `PipelineResult`: add `risk_curve` (list of alpha, path_length, hazard_violation_rate) and `baseline_paths`.
- `ScienceTarget`: add `rank_interval` (low, high) and `p_top3`.

## 3. Components (free and open source)

| Need | Pick | Why |
|---|---|---|
| Raster I/O, crop, reproject | `rasterio` + GDAL, `numpy`, `scipy` | Standard, reads the USGS GeoTIFFs |
| Slope and roughness | Own numpy Horn kernel (avoid `richdem`, GPL-3.0) [Plan §12] | Zero dependency risk |
| Correlated noise | `scipy.ndimage.gaussian_filter` on white noise | One line, defensible |
| Terrain classifier (main) | `scikit-learn` RandomForest or `lightgbm`; per-tree votes give variance | Runs on any laptop, explainable, matches the repo decision to keep rules plus RF as fallback |
| Terrain classifier (side track) | `transformers` `nvidia/segformer-b0-finetuned-ade-512-512` fine-tuned on AI4Mars | No Mars checkpoint was found on the Hub (search done 2026-11-14), so fine-tuning is the route. ADE20K checkpoint is the one named in the HF docs |
| Calibration and conformal | `torchmetrics` CalibrationError, temperature scaling by hand, `MAPIE` (BSD-3) | All free; `MAPIE` is a stretch |
| Planner | Own A*/Dijkstra with `numba` (or `heapq`), `scikit-image` `MCP` or `scipy.sparse.csgraph.dijkstra` for the corridor distances | Fast, no new dependencies |
| Dashboard | Streamlit + Plotly (already chosen) | Fast to build, click events via `plotly` selection |
| Repro | seeds in config, `pytest`, `make demo` | Part of the explainability score |

## 4. Data

- **DEM:** the individual Jezero HiRISE pair DTM `DTEEC_023524_1985_023379_1985_U01` is listed at about 700 MB on the HiRISE site; the USGS Mars Sample Return mosaic set is a 5.3 GB zip (DOI 10.5066/P13CPYYU). Sources: [HiRISE DTM page](https://hirise.lpl.arizona.edu/dtm/ESP_023524_1985), [USGS MSR mosaics](https://astrogeology.usgs.gov/search/map/mars-sample-return-terrain-relative-navigation-hirise-dtm-mosaic). Disha should start the download first. On hotel/venue Wi-Fi this may be slow; **fallback:** a seeded fractal/crater synthetic DEM so the demo is never blocked.
- **Spectral/ice/noise:** simulated, labelled as such, per the existing decision in `CONTEXT.md`. Keep the generator in `src/odyssey/data/`.
- **AI4Mars (side track only):** Zenodo v0.6, 17.8 GB full. Download only a subset (a few thousand images plus labels) or skip the side track. Pixel codes 0-3 per Zenodo; confirm against its README.
- Do **not** claim the AI4Mars model works on the orbital tile. It is a separate surface-view panel [Plan §4.1].

## 5. Compute bottlenecks (hackathon scale)

1. **Downloads:** the DTM is hundreds of MB to several GB. Start first, crop immediately, commit only the small crop if the licence allows (check).
2. **SegFormer fine-tune:** the only GPU-bound item. B0 at 512 px with batch 4 and fp16 should fit the 3050's 4 GB; this is an expectation, not measured. Cap at one hour. If it fails by 4:00 AM, drop it.
3. **DEM Monte Carlo:** 100 draws × Gaussian filter + Horn slope on 512² is cheap; store only mean and std, never all draws.
4. **Planning sweeps:** the risk-vs-length curve needs several A* runs (about 5 alphas × several start-goal pairs). With numba this is seconds. Plain Python A* on 512² may take seconds each, so use numba or a downsampled 256² planning grid.
5. **Evaluation:** a 100-run execution simulation per path is the one thing that can blow up. Cap at 50 start-goal pairs × 100 draws, vectorised, or reduce to 20 pairs.
6. **Dashboard:** keep renders at 512². Cache pipeline output with `st.cache_data`; never recompute on every widget change except the toggles that need it.

Run `pipeline.py` once per config and serialise the `PipelineResult`, so the demo is instant and cannot fail live.

## 6. Workflow against the existing timeline

Current checkpoints come from `docs/TIMELINE.md`. Do not change roles.

| When | Disha | Udit | Saptarshi |
|---|---|---|---|
| Now to 2:15 | Start DEM download. Crop 512². Write the simulated band generator | Approve contract additions above, freeze at 2:15, set up `pipeline.py` and config/seed | Dashboard shell with dummy `PipelineResult`. Download AI4Mars subset if the side track is on |
| 2:30 to 4:00 | Horn slope, roughness, hard-block rule, rule classifier, RF trial | B0 cost map and A*/Dijkstra. Add CVaR edge cost, corridor | DEM Monte Carlo, candidate generation, ranking MC. Start SegFormer fine-tune on the 3050 if on |
| 4:00 to 4:30 | Break and decision: SegFormer side track keep or drop | | |
| 4:30 to 6:00 | Hazard map with `class_probs` and `epistemic_std` delivered | Real cost map into A*. Inflation, risk curve, safety verifier, B1 reproduction | Rank intervals, evidence strings, calibration plot |
| 6:00 | First end-to-end `pipeline.py` run | owner of this | |
| 6:00 to 7:30 | Failure scenes (noise, gaps, conflicting bands) | Wire planner outputs to dashboard | Cautious/bold toggle, noise slider, click-to-trace, risk curve chart |
| 7:30 | Feature freeze | | |
| After | README approach and limits, demo rehearsal, backup video | | |

**Cut order if late** (extends the timeline's list): SegFormer side track, Dijkstra view, B1 baseline view, conformal wrapper, 3D polish, extra target categories. **Never cut:** cost map with `σ`, hazard-avoiding path, ranked targets with intervals, the cautious/bold dial, README limits, backup video.

## 7. Demo story (maps to the eight minutes)

1. Show the cost map and its uncertainty map side by side.
2. Show B1 (naive) path crossing hazards, B0 path, then the proposed path with corridor.
3. Drag the cautious/bold dial: path gets longer and safer, with the risk-vs-length curve below.
4. Drag the noise slider: ranks shift, intervals widen, some targets become "tied".
5. Click a target: evidence string and path cost breakdown. Click a cell: input trace.
6. (If kept) rover-view panel with predicted terrain and entropy.

## 8. Honest limits to state in the README

- One DEM tile, static map, no wheel slip or power model.
- Spectral and ice layers are simulated; science ranks are not evidence about real Mars.
- Slope limits, class multipliers and weights are assumptions, not fitted to rover data [Plan §13]. Working values until decided: hard block at 25 degrees (matches `docs/ARCHITECTURE.md`), soft-cost slope scale `theta_max` of 15 degrees, both set in one config file and swept in a sensitivity plot. Final numbers are a later decision, ideally cited by Disha in `docs/RESEARCH_NOTES.md`.
- CVaR here is edge-wise and Gaussian; it is conservative and is not a formal safety guarantee.
- No public orbital terrain labels were found, so orbital classes come from rules plus a model trained on rule-derived pseudo-labels, not from human ground truth.
