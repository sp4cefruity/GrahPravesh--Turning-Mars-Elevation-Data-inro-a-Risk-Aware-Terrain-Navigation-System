# MARS-09 (ODYSSEY): Model and Baseline Design Plan

Status: research draft, 2026-11-14. Repo was empty (no commits, no docs convention), so this file follows the requested default path.

**Provenance tags used throughout**

| Tag | Meaning |
|---|---|
| `[P1]` | Brad & Balog, *Electronics* 2025, 14, 921 (attached PDF, read in full) |
| `[P2]` | Sanchez-Ibanez et al., IROS 2022, "Optimal and Risk-Aware Path Planning considering Localization Uncertainty for Space Exploration Rovers" (attached `opt risk aware.pdf`, read in full) |
| `[S#]` | External source, listed in section 11 with a verification level |
| `[R]` | Our own recommendation or assumption. Not from any source; needs testing |

Verification levels in section 11: **F** = page/paper fetched and read this session; **SN** = only seen in search-result snippets (treat as unconfirmed); **U** = not verified.

Method note: the PDF reader tool could not render pages (no poppler), so both PDFs were read via text extraction (pypdf). Figures and photos were not inspected; claims below about figures are taken from captions and surrounding text only.

---

## 1. Problem restatement

Build **MARS-09**, an autonomous Mars rover pipeline that turns multi-spectral orbital/surface imagery, DEMs, slope measurements and science objectives into three deliverables, under communication delay and limited onboard compute:

1. **Terrain/cost map**: per-cell traversal cost (and its uncertainty) from terrain class, slope, roughness and hazards.
2. **Planned path with hazards avoided**: a route (plus a traversable corridor) that respects hazard limits at a stated risk level.
3. **Ranked science targets with uncertainty**: candidate formations/resources (for example subsurface ice, hydrated minerals) ranked by expected science value, with uncertainty on both the scores and the ranks.

Technical objectives: (a) perception/terrain intelligence (classify terrain, find hazards, build 3D elevation maps); (b) planning/cost mapping (A*, Dijkstra, RRT-family, corridors, movement cost, hazard avoidance); (c) science discovery and uncertainty reasoning (rank formations, find resources, quantify sensor and model uncertainty).

Operational constraints that shape every design choice `[R]`: (i) comms delay means plans are uplinked in batches and the rover must tolerate drift and surprises between uplinks, so we output corridors and risk-qualified paths, not a single brittle line; (ii) onboard compute is small, so the heavy stack (ensembles, Monte Carlo CVaR) runs "on the ground" and a light stack (small model, precomputed cost tiles, incremental replanning) runs "onboard". Both must be evaluated.

---

## 2. Summary of the two attached papers

### 2.1 `[P1]` Brad & Balog, *Electronics* 2025, 14(5), 921 (MDPI, CC BY)

**What it proposes.** A pipeline that plans a path on a grid combining DEM elevation with a *friction map* estimated from satellite imagery: (1) pick an AOI and start/goal as GeoJSON in a Leaflet UI; (2) download a DEM from OpenTopography (SRTMGL1, 30 m) and export lon/lat/elevation CSV; (3) classify the satellite image into water/vegetation/dirt/grass/forest/stone/road/concrete with hand-set RGB thresholds (OpenCV `inRange`) and assign hand-chosen friction coefficients (0.1 water to 0.9 concrete); (4) run A* with Euclidean heuristic on a per-cell cost `TerrainCost = Elevation / (Friction + eps)` (the PDF text extraction lost the division sign; the prose says higher elevation and lower friction raise cost, so division is the consistent reading), compared with an elevation-only cost; (5) build a "deviation band" around the path from cells whose elevation/friction are within a 5% tolerance of the path cell.

**Datasets.** Earth, not Mars: SRTMGL1 30 m DEM via OpenTopography API; satellite RGB imagery for a Romanian AOI (lon about 23.1 to 23.6, lat about 46.5 to 46.8) plus five further AOIs (Table 5: 25 start-goal pairs).

**Metrics and results (as reported).** Sum of friction coefficients along the path rose from 94.26 to 138.99, which the paper calls "over 32%" improvement in traction, with distance +24% on the main example. Table 5 (25 pairs) shows traction improvement from 0.59% to 20.57% and distance increase from 0% to 8.2%. Table 6 shows mean friction on path for three trajectories (e.g. 0.484 vs 0.483 on trajectory 1, 0.719 vs 0.473 on trajectory 2).

**Limitations (ours, from reading it, plus the authors' own).**
- Authors: 30 m raster resolution misses micro-topography; friction coefficients are statistical estimates not measured in situ; needs field validation.
- Ours: the cost uses *absolute elevation*, not slope, so cost depends on the datum (a high plateau is "expensive" for no physical reason); no slope/roughness/step hazard model; RGB thresholds are not a learned classifier and have no accuracy figure; friction values are asserted not measured; no uncertainty anywhere; no hazard-violation metric; "validation on real terrain" is a qualitative figure, not a quantitative test. Arithmetic check: 94.26 to 138.99 is a 47.5% increase, not 32%, so the headline number is not reproducible from the numbers printed (we could not find where 32% comes from; treat as unexplained).
- Mapping to MARS-09: useful as a **data-plumbing template** (AOI as GeoJSON, DEM raster to grid, class raster to cost layer, A* with a with/without-terrain ablation, path-corridor output) and as a **naive baseline** to beat. Not usable as a physical cost model. Its idea of a corridor around the path is relevant to the comms-delay constraint, but a cost-tolerance corridor (section 6.5) is better justified than a 5% property-similarity band.

### 2.2 `[P2]` Sanchez-Ibanez, Sanchez-Cuevas, Olivares-Mendez, IROS 2022

**What it proposes.** A planner that makes the costmap aware of *growing localization uncertainty* (odometry drift, no GPS/loop closure). Obstacle cells get three dilations: geometric (vehicle size, alpha), tracking-error (epsilon, from the C-Pursuit trajectory tracker), and an **uncertainty dilation** that grows with distance travelled. Cell (i,j) joins the uncertainty dilation if `d~_ij <= eps + f(gamma) * sigma_ij(d_ij)` (eq. 2), where `d~` is distance to nearest obstacle (distance transform), `d_ij` is path distance from start (Fast Marching Method, FMM, solving the eikonal equation with unit cost), `f(gamma)` converts a confidence level gamma to a multiple of sigma, and `sigma_ij = sqrt(d_ij/v_m) * sqrt(dT) * sigma_nu` from integrating a noisy velocity sensor (first-order model, zero bias, white Gaussian noise; eqs. 3 to 8). Algorithm 1 iterates FMM and cost-map update until no new cells are added, then extracts the path by gradient descent.

**Datasets/setup.** No real planetary data. Simulation in ROS/Gazebo with a LeoRover model; a 300x300 grid at 0.05 m with four 0.15 m circular obstacles; experiments in the University of Luxembourg LunaLab (11x7 m basalt-filled lunar analogue, OptiTrack mocap as ground truth, velocity noise injected in software).

**Metrics and results.** Path length and whether the ground-truth trajectory violated the geometric dilation. Without uncertainty, corridor violations occurred at up to 64.1% of path points (mean 14.35%, sd 19.07%). With confidence 68.27%, 95.45%, 99.73% no violation in any simulation (120 runs: 40 per path). Cost: path length 5.55 m to 5.92 m (+6.67%) and 9.52 m to 11.27 m (+18.38%) at 68.27%; +56.58% and +44.01% at 95.45% (the paper labels it "95.45%(sigma)"). At 99.73% one scenario's goal became unreachable at the required confidence.

**Limitations (authors' + ours).** Authors: isotropic cost, no turning cost, only localization uncertainty (no terrain-dependent uncertainty; listed as future work), no onboard-sensor uncertainty model. Ours: only binary traversable/non-traversable (no graded terrain costs); assumes a perfectly known map; the noise model is a random walk (error growing as sqrt of distance) rather than the drift growth typically seen with visual odometry (to be checked against rover data); experiments are small and the paper reports no statistical tests; stated guarantee is "at least the chosen confidence", which holds only under the assumed noise model.

**Mapping to MARS-09.** Directly supports (b): (1) the *distance-dependent safety inflation* is cheap and well suited to limited onboard compute and comms delay; (2) FMM gives smooth, grid-independent paths and the distance field `d_ij` is reusable for corridors; (3) the confidence-vs-length trade-off is a ready-made experiment ("risk knob"). **Gap**: it is *not* CVaR/chance-constrained planning over terrain uncertainty; the "risk-aware" content is localization-error inflation only. We combine it with CVaR-style terrain risk (section 6.4) from `[S12]`.

---

## 3. Survey of existing datasets, models and systems

"V" column = verification level from section 11.

### 3.1 Datasets and data products

| Item | What it is | Key facts (as verified) | Use in MARS-09 | V |
|---|---|---|---|---|
| **AI4Mars** [S1-S4] | Crowdsourced terrain-segmentation labels on Curiosity/Opportunity/Spirit (v0.6 adds Perseverance) surface images | Four classes (soil, bedrock, sand, big rock; Zenodo says labels are pixel values 0-3) [S6, S8]. Counts differ by source: CVPRW/NTRS abstract says about 35K images and 326K labels, about 10 labelers per image, about 1.5K expert validation labels (rover planners/scientists); Zenodo v0.6 says about 50K images, about 425K labels, 5 to 10 labelers, 17.8 GB, CC BY 4.0. A DeepLabv3 baseline reports over 96% overall accuracy [S3]. | Train/evaluate the learned terrain classifier. Use the expert-labelled set for validation and calibration. Pixel accuracy is dominated by easy classes, so report mIoU too. | F (Zenodo, NTRS); SN (CVPRW PDF 403) |
| **S5Mars** [S5] | Sparsely-annotated, confidence-based Mars segmentation set for semi-supervised learning | about 6K high-resolution images; code/data via project page. Class list and metrics not confirmed by us. | Optional second dataset / SSL ablation | F (abstract only) |
| **Mars-Seg / MSL surface classification** [S6] | Semi-supervised classification+segmentation paper evaluated on AI4Mars | On AI4Mars (4 classes) the paper's best method reports mIoU 70.34 (vs ReCo with ImageNet pretraining 69.15). Useful as a mIoU reference range for AI4Mars. | Sanity target for our segmentation baseline | F |
| **Mars32k** [S7] | about 32,000 Curiosity Mastcam colour images, 560x500, unlabeled | From a secondary project page; license and original source not confirmed. | Optional self-supervised pretraining | SN |
| **HiRISE DTMs** [S9] | Stereo-derived DTMs + orthoimages from MRO HiRISE, archived in PDS (MRO-M-HIRISE-5-DTM-V1.0) | Post spacing about 4x image pixel (so 1 to 2 m for 0.25 to 0.5 m/px images), vertical precision "tens of centimeters"; built with SOCET SET; documented artifacts: "boxes" (0.5 to 1 m offsets), CCD seams, faceting in bland/shadowed areas, manually interpolated patches. | **Primary DEM for the planning arena** (slope, roughness, step hazards) | F |
| **MOLA-HRSC blended DEM, 200 m** [S10] | Global gap-filled DEM (USGS Astrogeology) | 200 m/px, GeoTIFF about 11 GB; blending "did not always work well", use care. MOLA CC0, HRSC CC BY-SA 3.0 IGO. | Coarse context; also the "degraded planning input" in our sim protocol (section 8.1) | F |
| **CRISM summary products** [S11] | Spectral parameter maps from MRO CRISM (Viviano-Beck et al. 2014, 60 parameters) | Includes olivine/pyroxene indices (OLINDEX, LCPINDEX, HCPINDEX) and hydrated-phase band-depth indices (BD1900, BD2210, BD2350, BD2500, D2300, CINDEX) [per a secondary thesis snippet]. Coverage: targeted observations (not global); AOI coverage must be checked. | Mineral/hydration features for science scoring | SN (abstract/snippets) |
| **SWIM ice maps** [S12] | NASA Subsurface Water Ice Mapping project (neutron, thermal, image, elevation, radar) | About 3 km/pixel ice-consistency maps for depth bins 0-1 m, 1-5 m, >5 m; 60S to 60N; GeoTIFFs on the SWIM site. Too coarse for a 5 km AOI, so use only as a *prior*. | Ice prior for science score | SN |
| **Odyssey neutron/GRS hydrogen** [S13] | Water-equivalent hydrogen from Mars Odyssey Neutron Spectrometer | Resolution improved from 520 to 290 km in reprocessing (SN); IDND quarterly CSVs on PDS. Hundreds-of-km scale, so only a regional prior. | Regional prior / context | SN |
| **SHARAD radar** [S14] | MRO shallow radar, 15-25 MHz | About 15 m vertical resolution in free space, about 8 m in ice; cannot resolve top about 15 m; many regions have no returns. | Sparse evidence for subsurface layers | SN |
| **Dundas et al. 2018** [S15] | Exposed ice scarps at eight mid-latitude sites (HiRISE imagery/topography) | Ice >100 m thick, starting 1 to 2 m below surface; scarps retreating. | Motivates an "ice scarp" AOI/candidate type | F (abstract) |

### 3.2 Models, systems and methods

| Item | What it is / claim | Use in MARS-09 | V |
|---|---|---|---|
| **SPOC** (JPL) [S16] | Soil Property and Object Classification: SPOC-HiRISE (17 classes at 25 cm, "over 90%" overall accuracy vs human labels per project page), SPOC-NAVCAM (ground ops), SPOC-Lite (RAD750-class CPU, outputs sand probability, open source), SPOC-HPSC/SNPE (onboard, GPU). Trained on AI4Mars labels. | Design precedent for ground-vs-onboard model split; SPOC-Lite's "single sand probability" is a good model for a minimal onboard head. We could not verify that SPOC-HiRISE weights/labels are public. | F |
| **Perseverance AutoNav / ENav** [S17, S18] | AutoNav evaluated 88% of 17.7 km in first Mars year (SN); Snowdrift Peak crossing: 520 m straight line, 759 m driven, 6 autonomous sols (F, JPL news). ENav reportedly scans terrain about 15 m ahead, evaluates at the individual-wheel level and honours keep-out areas (secondary news; IEEE T-FR paper by Ono et al. 2025, doc 11265757, not read). | Architectural precedent: terrain-aware local planner with keep-out zones; justifies including hazard keep-outs and a local replanner. We did not read the ENav paper, so no algorithmic details are claimed. | F (JPL news), SN (rest) |
| **MER GESTALT** [S19] | Grid cells about one wheel in size, each assessed as a planar patch for steps/slopes/roughness; scores candidate arcs on hazard avoidance, steering time, goal progress. | Precedent for wheel-scale slope/roughness/step hazard layers and arc-based local planning | SN (JPL chapter surfaced in search) |
| **Ono et al. 2015, risk-aware rover operation** [S20] | ML terrain classification + risk-aware planner based on RRG and A*, demonstrated on Curiosity images. Whether it uses CVaR/chance constraints was not confirmed. | Precedent for coupling classifier output to risk-aware planning | SN |
| **Endo et al., ICRA 2023, arXiv 2303.01169** [S21] | Fuses a terrain classifier (U-Net/ResNet-18, per-pixel softmax) with class-conditioned slip GPs (pitch to slip) into a mixture; edge cost = distance / velocity derived from **CVaR** of slip, A* on 8-neighbour grid; alpha = 0.99. **Simulation only** (96x96 synthetic fractal/Perlin maps at 1 m); metrics solved rate, success rate, traversal time, max slip; baselines single-GP + EV/VaR/CVaR and MGP + EV/VaR. MGP+CVaR best on success (96% on Std, 95% on Ambiguous Appearance). Authors state: no entrapment guarantee, CVaR/VaR planners sometimes find no solution, no real planetary data. | **Closest published template for our proposed planner.** We reuse its structure (class probabilities to mixture slip to CVaR edge cost to A*) but add DEM-derived slope uncertainty and a hazard chance budget. | F |
| **Slip learning** (Cunningham et al. GP slip, thermal-inertia mixtures) [S22] | GP slip vs slope per terrain class; mixtures conditioned on thermal inertia. | Stretch: learned slip model. Only seen via citations in search summaries. | SN |
| **SegFormer** [S23] arXiv 2105.15203; **DeepLabv3+** arXiv 1802.02611 | Standard segmentation backbones | Baselines for the learned classifier | F (titles/authors) |
| **Deep ensembles** 1612.01474; **MC dropout** 1506.02142; **evidential DL** 1806.01768; **calibration (ECE, temperature scaling)** 1706.04599; **conformal prediction** 2107.07511; **conformal risk control** 2208.02814 [S24] | Uncertainty estimation and calibration toolbox | Epistemic uncertainty for the classifier and calibrated risk thresholds | F (titles/authors) |
| **CVaR** (Rockafellar & Uryasev 2000) [S25]; **D\* Lite** (Koenig & Likhachev, AAAI 2002) [S26]; **RRT\*** (Karaman & Frazzoli, arXiv 1105.1186) [S27]; **FMM** (Sethian; cited in `[P2]`) | Risk measure, incremental replanner, asymptotically-optimal sampling planner, eikonal planner | Planner/ risk components | F / SN |
| **AEGIS** (JPL) [S28] | Onboard autonomous science targeting: on Opportunity (software uploaded about 2009-2010, sources differ) and Curiosity ChemCam (routine use since May 2016); reported >93% success selecting desired target material over 2.5 km vs about 24% expected without targeting (secondary snippet). | Precedent that *scientist-specified objectives to ranked onboard target selection* works operationally; justifies a scoring-function design with explicit objectives. | SN |
| "Learning to Drive on Mars", arXiv 2609.24952 (appeared in a search; unread) | Reported to add a learned hazard map to ENav. | Not cited in the design; mentioned so the team can check it. | U |

---

## 4. Recommended end-to-end architecture

```
                       GROUND SEGMENT (heavy)                               ONBOARD (light)
 HiRISE DTM + ortho ─┐                                                    ┌──────────────────────┐
 CTX/MOLA context ───┤  (1) Data prep (co-register, tile, QC)             │ small seg. head      │
 CRISM / SWIM / SHARAD┤                                                   │ (SPOC-Lite-like)     │
 AI4Mars (surface) ──┘                                                    │ local DEM patches    │
          │                                                               │ D* Lite replanner    │
          ▼                                                               │ inflate by σ_loc(d)  │
 (2) Perception: terrain-class probs p_k(x) + epistemic var  ──┐          └─────────▲────────────┘
 (3) DEM layers: slope θ, roughness ρ, step h, σ_θ  ───────────┼─► (4) Cost-map fusion: μ(x), σ²(x), P_haz(x), lethal mask
                                                               │          │
                                                               │          ▼
                                                               │   (5) Planner: CVaR / chance-budget A* (+FMM), corridor ──► uplink: path + corridor + risk report
                                                               │
 Science objectives ──► (6) Candidate generation, features + σ, utility, MC ranking ──► ranked list with rank intervals
```

`[R]` throughout this section unless a tag says otherwise.

### 4.1 Scale decision (important)

AI4Mars and S5Mars are **surface (rover-camera) images** with no DEM. HiRISE DTMs are **orbital** with 1 to 2 m posts. A single model cannot consume both without a bridge, and we found **no verified public orbital terrain-class label set** (SPOC-HiRISE labels/weights not confirmed public). Recommended two-track plan:

- **Track A (main demo, orbital scale):** planning arena = HiRISE DTM + orthoimage for one AOI. Terrain-class probabilities for the arena come from a classifier trained on a *small hand-labelled set of HiRISE ortho tiles* (team labels about 40 to 80 tiles with Label Studio into 4 to 6 classes aligned to AI4Mars: smooth soil, sand/dune, bedrock/outcrop, rock field, plus crater/steep wall from DEM) plus DEM-derived pseudo-labels for self-training. Budget this in the timeline; it is the largest hidden cost.
- **Track B (perception benchmark, surface scale):** train/evaluate SegFormer/DeepLabv3+/U-Net on AI4Mars, report mIoU/ECE/uncertainty. This validates the classifier code, uncertainty methods and onboard-size model. Optional demo of the surface classifier feeding a local-patch cost map for the onboard replanner.
- Do **not** claim the AI4Mars model works on HiRISE imagery without testing; expect a domain gap. Evaluating that gap is a legitimate extra experiment.

### 4.2 Choosing the AOI

Pick 2 or 3 AOIs (about 3x3 to 5x5 km each) that have (i) a HiRISE DTM, (ii) CRISM targeted coverage, (iii) some SHARAD coverage, and one with an ice-relevant setting (e.g. one of the Dundas 2018 scarp sites, which used HiRISE topography [S15]). Coverage must be checked in the PDS/HiRISE catalogs; we did not verify any specific AOI.

---

## 5. Deliverable 1: Terrain / cost map (numbered steps)

1. **Data prep** `[R]`. Ingest with `rasterio`/GDAL; reproject all layers to one equal-area or local projection; resample orthoimage and DEM to a common grid (analysis grid 1 to 2 m; planning grid 2 to 5 m by block-averaging after hazard computation, taking the *max* hazard, not the mean, when aggregating). Mask HiRISE DTM nodata and flag known artifact areas (boxes, CCD seams, faceting, interpolated patches [S9]) as "low-confidence DEM", which raises `sigma_z` there. Store tiles as Cloud-Optimised GeoTIFF/Zarr. Version with DVC or git-lfs. The `[P1]` GeoJSON-AOI idea is a good interface for defining AOI/start/goal.
2. **3D elevation map** `[R]`. Use the HiRISE DTM directly as the primary elevation product (already a stereo-derived surface). Point-cloud inputs (the brief mentions elevation point clouds): grid with IDW/kriging or binning (`scipy`, `PDAL`/`Open3D`) and fill gaps from the MOLA-HRSC blend [S10] with an explicit extra variance term. Stretch: rover stereo pairs for local DEM patches (not verified that AI4Mars provides stereo pairs).
3. **DEM uncertainty** `[R]`. Set `sigma_z` from the documented "tens of centimeters" [S9], inflated in artifact masks. Propagate to slope by Monte Carlo with spatially correlated noise (Gaussian random field, correlation length about 10 to 50 m, a tunable assumption). Do not assume independent per-pixel noise: central-difference slope would then have `sigma_zx = sigma_z / (sqrt(2) * dx)`, which overstates slope noise for correlated errors.
4. **DEM-derived layers** `[R]`. At rover-footprint scale (parameter; smooth DEM with a window of one wheelbase before differencing): slope `theta` (Horn 3x3 via numpy/`gdaldem slope`, avoid `richdem` unless GPL-3.0 is acceptable [S29]); roughness `rho` (std of detrended elevation or TRI in a 3 to 5 m window); step/ledge `h` (max elevation difference inside a wheel-size window); local curvature for crater rims/ridges; optional rock-abundance proxy from high-pass elevation. Output `theta_hat`, `sigma_theta`, `rho_hat`, `h_hat`.
5. **Terrain classification** (see section 7) gives class probabilities `p_k(x)` and an epistemic variance map.
6. **Hazard probability** `[R]`: `P_slope(x) = 1 - Phi((theta_max - theta_hat)/sigma_theta)`; `P_step(x)` and `P_rough(x)` analogously; class hazard `P_cls(x) = sum_k p_k(x) * 1[k in hazard classes]` (big-rock fields, soft sand). Combine as `P_haz = 1 - (1-P_slope)(1-P_step)(1-P_rough)(1-P_cls)` (independence assumption, conservative when errors are positively correlated). The rover limit `theta_max` is a **design parameter**: we did not verify any published rover slope limit, so treat 15 degrees as a placeholder, run a sensitivity sweep (10/15/20/25), and state this clearly in the report.
7. **Cost-map fusion** `[R]`. For each cell:

   ```
   mu(x)      = dx * [ 1 + a*(theta_hat/theta_max)^2 + b*(rho_hat/rho_max) + sum_k p_k(x)*m_k + c*(h_hat/h_max) ]
   sigma^2(x) = dx^2 * [ Var_k(m_k | p) + (a*2*theta_hat/theta_max^2)^2 * sigma_theta^2 + sigma_epi^2(x) ]
   lethal(x)  = 1  if  P_haz(x) >= delta  or  x in keep-out/no-go
   ```
   where `m_k` are class multipliers (design parameters, e.g. soil 0, bedrock 0.2, sand high and slope-dependent, rock-field high), `Var_k` is the class-mixture variance `sum p_k m_k^2 - (sum p_k m_k)^2`, `sigma_epi` is the ensemble/MC-dropout disagreement, and `delta` (e.g. 0.05) is the per-cell hazard tolerance. Weights `a, b, c, m_k` are not fitted from Mars traversal data (none available to us); expose them in one YAML, sweep them, and report sensitivity. Optional slip upgrade: class-conditioned slip `s_k(theta)` (GP, per `[S12]`/`[S22]`) replaces `m_k` in the sand term.
8. **Localization-uncertainty inflation** `[P2]`. Inflate lethal cells by `r(x) = r_geo + eps_track + f(gamma) * sigma_loc(d(x))` with `sigma_loc(d) = sqrt(d/v_m) * sqrt(dT) * sigma_nu` (eq. 8 in `[P2]`, random-walk velocity noise). `d(x)` is the path distance from the *current* start, so this is recomputed per plan (iterate to a fixed point as in Algorithm 1). `[R]` also run a linear-in-distance variant `sigma_loc = k*d` as an ablation since random-walk growth is an assumption.
9. **Outputs** `[R]`: GeoTIFF/Zarr layers `mu`, `sigma`, `P_haz`, `lethal`, `class_probs`, `confidence`; 8-bit quantised tile version for uplink/onboard; a rendered PNG overlay for the deliverable.

---

## 6. Deliverable 2: Planned path with hazards avoided

### 6.1 Baseline planner (see section 9): A*/Dijkstra on a deterministic cost.

### 6.2 Graph and costs `[R]`
8-connected grid. Edge cost between cells `u,v` = `0.5*(mu(u)+mu(v)) * ||u-v||/dx`, infinite if either cell is lethal. A* heuristic = octile distance times the minimum per-cell cost (otherwise the heuristic may be inadmissible; note that `[P1]` adds a raw-elevation cost to an unscaled Euclidean heuristic, which does not guarantee admissibility). Use Dijkstra as an optimality cross-check on every test case.

### 6.3 Risk-aware planners (proposed) `[R]`, building on `[S21]`, `[S25]`, `[P2]`
- **P-CVaR:** replace `mu` by `CVaR_alpha` of the edge cost. For a Gaussian edge cost, `CVaR_alpha = mu + sigma * phi(z_alpha)/(1-alpha)` with `z_alpha = Phi^-1(alpha)`; use Monte Carlo from the ensemble for non-Gaussian mixtures (as `[S21]` does). Sum of per-edge CVaR is a conservative upper bound on the path-sum CVaR (CVaR is subadditive), so report that this is *edge-wise* CVaR and also evaluate the true path-level CVaR by Monte Carlo (section 8). Sweep `alpha` in {0 (expected cost), 0.5, 0.9, 0.95, 0.99}. Note CVaR conventions differ between papers; fix ours in the code docstring.
- **P-Chance:** hazard budget. Minimise cost s.t. `sum_i -log(1 - P_haz(i)) <= -log(1 - Delta)` (probability of crossing a hazard `<= Delta` under independence, conservative under positive correlation). Solve by Lagrangian: edge cost `mu + lambda * (-log(1-P_haz))` and bisect on `lambda`. This is our own formulation; verify on small grids against exhaustive/ILP search.
- **P-Infl:** `[P2]` uncertainty inflation as above, combined with either of the two.
- **FMM variant** `[P2]`: `scikit-fmm` `travel_time(phi, speed=1/cost)` for smooth continuous paths and the distance field used in step 8 and in corridors. The paper notes FMM cannot handle zero/negative costs and is isotropic.
- **Infeasibility handling:** both `[P2]` (99.73% case) and `[S21]` (no solution when the goal is hazardous) report cases with no feasible path; the planner must return "no path at this risk level" plus the lowest-risk path and the minimum achievable `Delta`.

### 6.4 Replanning (onboard) `[R]`
D* Lite [S26] over the same grid: start with the ground-plan cost map, reveal higher-resolution local DEM/class patches within a sensing radius as the simulated rover advances (ENav reportedly looks about 15 m ahead [S18], which is a reasonable value to simulate, flagged as secondary-source), update edge costs, replan incrementally. Compare against A* from scratch for planning time.

### 6.5 Traversable corridor `[R]`
With forward distance `D_s(x)` from start and backward distance `D_g(x)` from goal (two Dijkstra runs), corridor = `{x : D_s(x) + D_g(x) <= (1+tau) * C*}` with `tau` in {2%, 5%, 10%}. Gives a path-independent "safe width" suitable for uplink under comms delay. This replaces the `[P1]` friction/elevation similarity band; compare both.

### 6.6 Other planners to benchmark `[R]`
RRT*/Informed RRT* (OMPL or `PythonRobotics` reference [S30]) on the same cost map as a comparison planner. Expected (hypothesis, not a result): grid A* is faster and deterministic on a raster cost map; RRT* is mainly useful if we add kinematic constraints. `[P2]` also argues FMM paths are shorter/smoother than grid A* and cites RRT* convergence cost.

---

## 7. Deliverable 1 support: terrain classifier and uncertainty (numbered steps)

1. **Label schema** `[R]`: 4 AI4Mars classes (soil, bedrock, sand, big rock) plus an ignore/null label (confirm exact pixel codes in the dataset README; Zenodo states values 0-3, and null handling was not confirmed).
2. **Splits** `[R]`: split AI4Mars by *sol/site/rover* not by random image (neighbouring frames are near-duplicates); keep the 1.5K expert-labelled set as the validation/calibration/test reference. Report per-rover results.
3. **Baseline model:** U-Net or DeepLabv3+ with ResNet-18/34 (`segmentation_models_pytorch`: MIT licence, supports Unet, DeepLabV3+, Segformer, 800+ encoders [S31]). Cross-entropy (class-weighted) + Dice. Expected reference range: mIoU in the high 50s to about 70 on AI4Mars per `[S6]`'s table (their numbers, different protocol).
2b. **Proposed model:** SegFormer-B0/B1 (small, onboard-feasible) fine-tuned, as a *deep ensemble* of 3 to 5 members `[S24]` (ground), with **MC dropout** or a single temperature-scaled model as the cheap onboard variant. Add temperature scaling on the expert set `[S24]` (Guo et al.). Optional: evidential head `[S24]`.
3. **Uncertainty outputs** `[R]`: per-pixel predictive entropy, mutual information (ensemble disagreement = epistemic), and calibrated softmax probabilities. For "guarantees", wrap with **conformal prediction sets / conformal risk control** (`MAPIE`, BSD-3; supports risk control for segmentation [S32]) targeting a bound on the false-negative rate for *hazard classes* (missing big rock/sand is the costly error).
4. **Train-time augmentations** `[R]`: brightness/contrast, dust/haze, shadow, mild blur (illumination varies with time of day), flips. Add S5Mars-style strong augmentation as an ablation only if S5Mars is adopted.
5. **Metrics:** mIoU, per-class IoU, pixel accuracy, hazard-class recall/precision, ECE (15 bins, `torchmetrics.CalibrationError`, `norm='l1'` [S33]), NLL, Brier, reliability diagrams, AUROC of "error vs uncertainty", risk-coverage curve, conformal coverage/set size.
6. **Track A orbital classifier** `[R]`: same architecture, trained on the hand-labelled HiRISE tiles with DEM-derived pseudo-labels; report agreement with a held-out labelled set (mIoU, ECE). Report the AI4Mars-to-orbital domain-gap experiment separately.
7. **Onboard-budget check** `[R]`: export to ONNX, measure parameters, MB, latency on CPU-only (single thread) at the deployment tile size, and accuracy after int8 quantisation. `[S16]` (SPOC-Lite) is a precedent for a very small CPU-friendly model. No numeric compute budget was given in the brief; the team must set one (see open questions).

---

## 8. Deliverable 3: Science targets with uncertainty

### 8.1 Evaluation world (shared with section 10) `[R]`
There is no ground truth for "best science target" or for true hazards on Mars. Create a **truth-vs-input split**: treat the full-resolution HiRISE DTM and the hand labels as "truth"; give the planner a *degraded* view (e.g. 10 to 20 m block-averaged DEM plus noise, ensemble-predicted classes, MOLA-HRSC fill in gaps). Hazards and costs are scored on truth. For science, plant synthetic targets (features sampled with known latent value) in some trials so ranking metrics have an oracle. Be explicit that results are on *simulated* ground truth.

### 8.2 Candidate generation `[R]`
Threshold/segment a composite of CRISM hydration/mineral indices [S11] and geomorphic cues (layered outcrops, scarps, polygonal ground from the ortho classifier or hand mapping) into connected components of 20 to 200 m; each candidate gets polygon, centroid, area.

### 8.3 Features and uncertainty `[R]`
| Feature | Source | Uncertainty model |
|---|---|---|
| Hydration/mineral index (e.g. BD1900, BD2210, D2300, OLINDEX [S11]) | CRISM | Per-pixel noise or per-index spread from neighbouring pixels; flag low coverage |
| Ice prior (consistency, depth bin) | SWIM [S12] | Treated as a Beta prior; coarse, so low weight and wide variance |
| Regional hydrogen | Odyssey NS [S13] | Hundreds of km scale; prior only |
| Subsurface reflector | SHARAD [S14] | Present/absent/no-data (three states); no data does not mean no ice |
| Geomorphic ice indicators (scarps, polygons) | ortho + DEM | Classifier probability |
| **Accessibility cost** | planner | Path-level CVaR to reach the target (from section 6) |
| Safety at target | DEM | `P_haz` at the site; slope/roughness for instrument deployment |

### 8.4 Utility and ranking `[R]`
1. Scalar science utility `U_i = sum_k w_k * s_k(i)` with `s_k` normalised to [0,1]; for evidence-combination alternatives, a naive-Bayes log-odds sum for "P(ice present)". Weights `w_k` come from stated mission objectives, set by the team (document them).
2. Net value: `V_i = E[U_i] - beta * CVaR_alpha(C_access(i))` (science value vs risk/energy). Sweep `beta`; plot the Pareto front of (value, access risk).
3. **Uncertainty on rank:** Monte Carlo (e.g. 2000 samples): resample features from their uncertainty models and the weights from a Dirichlet around `w`; output for each candidate `E[V]`, a 90% interval, `P(rank <= k)` and rank interval. Report a list "ranked by `E[V]`, with ties flagged when intervals overlap".
4. Optional multi-target tour: orienteering-style selection (maximise sum of `V_i` along a path under an energy/time budget) solved greedily or by small ILP. Stretch goal.

### 8.5 Metrics `[R]`
Spearman rho and Kendall tau vs oracle ranking (planted-target trials); NDCG@5/10; top-k precision/recall; rank-interval coverage (does the 90% interval contain the oracle rank about 90% of the time); calibration of "P(ice)" if any labelled sites exist (ECE/Brier); sensitivity of top-3 to weight perturbation (Kendall tau across Dirichlet draws). No labelled real-world resource ground truth is available to us, so we do not claim real-world ranking accuracy.

---

## 9. BASELINE vs PROPOSED

### 9.1 Baseline (B0): simple and reproducible `[R]`, structurally echoing `[P1]`

| Component | B0 definition |
|---|---|
| Data | Same AOI HiRISE DTM at planning resolution; no orthoimage classification |
| DEM layers | Slope from Horn 3x3 on the raw DEM at planning resolution; roughness = local std |
| Cost map | `cost = 1 + (theta/theta_max)^2 + rho/rho_max`; **lethal if `theta > theta_max`** (same `theta_max` as proposed model); no class term, no uncertainty |
| Planner | 8-connected A* (octile heuristic scaled by min cost), checked against Dijkstra. No inflation, no corridor (or a fixed 3-cell dilation) |
| Science | Weighted sum of normalised point-estimate features (same `w_k`); rank by sort; distance-to-target as a crude access penalty; no intervals |
| Reproduction | Seeds fixed; one `make baseline` command; outputs identical schemas to the proposed pipeline |

**B1 (reference reproduction of `[P1]`)**: `cost = z / (friction + eps)` with RGB-threshold friction classes, plain A*. Included so we can state quantitatively *why* the physically-based slope term matters (expected: datum dependence, more slope violations), not to be taken as a competitive baseline.

### 9.2 Proposed model (M)

| Component | M definition |
|---|---|
| Perception | SegFormer deep ensemble + calibration + conformal hazard-class control; DEM Monte Carlo slope uncertainty |
| Cost | Mean+variance cost with class mixture, hazard probability `P_haz`, lethal threshold `delta`, localization inflation `[P2]` |
| Planner | CVaR (edge-wise) and/or chance-budget A*, FMM variant, D* Lite replanning onboard, cost-tolerance corridor |
| Science | Feature uncertainty + MC ranking + CVaR access cost; rank intervals and `P(rank<=k)` |

### 9.3 Ablations `[R]`
A1 slope-only vs +roughness/step layers. A2 +class term (soft probabilities) vs hard argmax classes. A3 classifier: single model vs ensemble vs MC dropout vs temperature-scaled; with/without conformal wrapper. A4 uncertainty in cost: mean-only vs mean+lambda*sigma vs CVaR (alpha sweep) vs chance-budget (Delta sweep). A5 localization inflation on/off; random-walk vs linear drift; confidence gamma sweep (reproduces `[P2]`'s trade-off). A6 planner: A* vs Dijkstra vs FMM vs RRT*; D* Lite vs A* from scratch. A7 corridor: cost-tolerance vs `[P1]` similarity band. A8 DEM degradation level (5/10/20/50 m) and artifact masks. A9 science: with/without uncertainty propagation; with/without access-cost term; weight perturbation. A10 `theta_max` sweep.

---

## 10. Evaluation plan

### 10.1 Protocol `[R]`
- >= 3 AOIs (or >= 3 distinct 3 to 5 km tiles), >= 50 start-goal pairs per AOI sampled so the straight line crosses hazards (otherwise all methods tie). Train/val/test split by AOI/tile for the orbital classifier.
- Each planned path executed in **Monte Carlo** (N >= 100): sample a truth world from the posterior/truth, inject localization drift per `[P2]` (eq. 3 to 8), follow with a pure-pursuit-style tracker with tolerance `eps`.
- Report bootstrap 95% CIs over pairs; paired Wilcoxon (or paired bootstrap) between B0 and M.

### 10.2 Metrics
| Deliverable | Metrics |
|---|---|
| Perception | mIoU, per-class IoU, hazard-class recall/precision, pixel acc, ECE/NLL/Brier, risk-coverage curve, conformal coverage and set size, params/MB/latency/int8 drop |
| DEM/hazard layers | slope RMSE and bias vs truth, hazard-map recall/precision at the chosen `delta`, calibration of `P_haz` (binary ECE/reliability) |
| Cost map | MAE/Spearman between predicted and truth cost; fraction of truth-lethal cells marked lethal (recall; the priority metric) |
| Path | path length ratio vs oracle-on-truth path; total truth cost; **hazard-violation rate** (fraction of executions crossing truth-lethal cells, and fraction of path points); max slope encountered; min clearance to hazards; **success rate** (reach goal with no violation over N runs); mean and CVaR_0.95 of executed truth cost; infeasibility rate; planning time, nodes expanded, memory; replans and replan time |
| Corridor | coverage (fraction of executed tracks inside corridor), corridor width, hazard-free fraction |
| Science | Spearman, Kendall, NDCG@5/10, top-k recall, rank-interval coverage, top-3 stability under weight perturbation, value-per-risk Pareto |
| System | end-to-end ground-segment runtime; onboard replanner latency on a CPU-only budget |

Report the safety/efficiency trade-off as a **curve** (hazard-violation vs path-length increase across `alpha`, `Delta`, `gamma`), mirroring `[P2]`'s confidence-vs-length analysis rather than a single operating point.

---

## 11. Suggested timeline and work split `[R]`

Assumes 4 people and about 5 weeks; scale to the real deadline.

| Week | R1 Data/geo | R2 Perception ML | R3 Planning | R4 Science/UQ/eval/viz |
|---|---|---|---|---|
| 1 | AOI selection and coverage check; download HiRISE DTM/ortho, CRISM, SWIM; QC artifacts | AI4Mars download, splits, U-Net/DeepLabv3+ baseline | Grid/A*/Dijkstra, Horn slope, B0 cost map | Eval harness skeleton, truth-vs-input world, repo/CI/DVC |
| 2 | DEM layers + MC slope uncertainty; orbital label tiles (Label Studio) | SegFormer + ensemble + temperature scaling; ECE reports | B0 end-to-end; Monte Carlo execution with drift `[P2]` | CRISM candidates; B0 science ranking |
| 3 | Co-registration of CRISM/ortho; keep-out masks | Orbital classifier; conformal wrapper; domain-gap test | CVaR/chance-budget planners; FMM; corridors | Science MC ranking; rank intervals |
| 4 | Packaging of tiles/quantised layers | Onboard-size export, latency/int8 | D* Lite replanning; RRT* comparison | Full ablations A1-A10 runs |
| 5 | Buffer / data fixes | Final model cards | Final plots of trade-off curves | Report, figures, demo, failure-case gallery |

Milestones: M1 (end wk 1) baseline B0 runs end-to-end on one AOI; M2 (wk 3) proposed model v1 produces all 3 deliverables; M3 (wk 4) ablation table complete; M4 (wk 5) report.

---

## 12. Tools and libraries

All Python; `[R]` selection, licences as verified where noted.

| Area | Tools |
|---|---|
| Geo/raster | `rasterio`/GDAL (`gdaldem`), `pyproj`, `rioxarray`/`xarray`, `geopandas`/`shapely` (GeoJSON AOI as in `[P1]`), OpenTopography API only for Earth-analogue DEMs |
| Array/vision | `numpy`, `scipy`, `scikit-image`, `OpenCV`; `PDAL`/`Open3D` for point clouds (not verified here) |
| Terrain attributes | own numpy Horn slope or `gdaldem`; `richdem` is available but **GPL-3.0** [S29] |
| ML | `PyTorch`, `segmentation-models-pytorch` (MIT; Unet, DeepLabV3+, Segformer) [S31], Hugging Face `transformers` SegFormer (not verified here), `albumentations`, `torchmetrics` (ECE/MCE) [S33], ONNX/ONNX Runtime for onboard-size tests |
| Uncertainty | `MAPIE` (BSD-3; conformal and risk control incl. segmentation) [S32]; deep ensembles/MC dropout implemented in PyTorch; `scikit-learn` GaussianProcessRegressor or GPyTorch for slip GPs (GPyTorch not verified here) |
| Planning | `scikit-fmm` (BSD; `travel_time` with speed field) [S34]; own A*/Dijkstra/D* Lite (heapq/numba) with `PythonRobotics` (MIT; has Dijkstra, A*, D*, D* Lite, PRM, RRT, RRT*, no Hybrid A*) as a reference [S30]; OMPL for RRT* (not verified here); `networkx` for small-graph cross-checks |
| Labelling | Label Studio (not verified here) |
| Experiment mgmt | DVC or git-lfs, Hydra/YAML config, `pytest`, Weights & Biases or MLflow (optional) |
| Viz | `matplotlib`, `pyvista`/`plotly` for 3D DEM + path, `folium` for AOI picker like `[P1]` |
| Optional stereo/DEM building | NASA Ames Stereo Pipeline or USGS ISIS3 (not verified here; only needed if we build DEMs ourselves rather than use PDS DTMs) |

---

## 13. Risks and open questions

**Risks**
1. **No verified orbital terrain-class labels** (largest risk). Mitigation: small hand-labelled set + DEM pseudo-labels; scope claims to what we measure. Hand labels by students are noisy; report inter-annotator agreement.
2. **Domain gap** AI4Mars (surface) to HiRISE (orbital). Do not mix results; report separately.
3. **Cost-model parameters are assumed** (`a, b, c, m_k, theta_max, rho_max, h_max`, drift model). No Mars traversal data is available to us to fit them. Mitigation: sensitivity sweeps; present conclusions as relative (M vs B0), not absolute rover-safety claims.
4. **Evaluation circularity**: if truth and input derive from the same DEM, results are optimistic. Mitigation: degrade the input independently (resolution, noise, artifact masks) and keep the labelled set out of training.
5. **HiRISE DTM artifacts** (boxes, seams, facets) can look like hazards or hide them [S9]; handle via masks and inflated variance.
6. **Coverage mismatch**: CRISM is targeted (partial) coverage; SWIM/neutron data are far coarser than the AOI; SHARAD often has no returns [S11-S14]. Science scores may rest on thin evidence; show "evidence available" flags in the ranked list.
7. **Over-conservatism**: edge-wise CVaR and independence-based chance budgets are conservative; high `alpha` can make goals unreachable (seen in both `[P2]` and `[S21]`). Provide the minimum-feasible-risk fallback.
8. **Compute**: ensemble + Monte Carlo CVaR may exceed laptop-scale runtimes on large grids; plan resolution/tile caps and report runtime (the `[S21]` paper reports roughly 10 to 15 minutes planning time per its setup).
9. **Source reliability**: several external facts here come from search snippets or secondary pages (marked SN/U). Re-check before putting any number in the final report.
10. **Licences**: `richdem` is GPL-3.0; HRSC part of the blended DEM is CC BY-SA 3.0 IGO; the NASA data portal listing for AI4Mars shows no licence while Zenodo says CC BY 4.0 [S2, S4, S10].

**Open questions for the team/instructors**
- What are the *actual* provided inputs (specific DEM/tile, bands, slope products)? If a dataset is supplied, it overrides section 4.2.
- Is there a stated onboard compute budget (CPU class, RAM, time per replan) and comms-delay model (round-trip time, uplink frequency)?
- Is there a reference rover (slope limit, wheel size, power model) so `theta_max`, footprint and energy cost are not guesses?
- What does "multi-spectral imagery" mean concretely (CRISM cubes, HiRISE colour, Mastcam filters)? That determines the spectral-index route.
- How will judges score "uncertainty shown"? Plan for a visual (rank-interval plot, `sigma` heatmap, risk-length curve).
- Is energy/time a third objective? If so, add a slope-dependent energy term to `mu` and include energy in metrics.

---

## 14. Sources

Verification: F = fetched/read this session; SN = search-result snippet only; U = not verified. Items marked SN may be correct but have not been confirmed against the primary page.

- **[P1]** Brad, S.; Balog, B. *Electronics* 2025, 14, 921. https://doi.org/10.3390/electronics14050921 (attached PDF, F)
- **[P2]** Sanchez-Ibanez, J.R.; Sanchez-Cuevas, P.J.; Olivares-Mendez, M. IROS 2022, DOI 10.1109/IROS47612.2022.9981179 (attached PDF "opt risk aware.pdf", F)
- **[S1]** Swan et al., AI4MARS, CVPRW 2021: https://openaccess.thecvf.com/content/CVPR2021W/AI4Space/papers/Swan_AI4MARS_A_Dataset_for_Terrain-Aware_Autonomous_Driving_on_Mars_CVPRW_2021_paper.pdf (direct fetch returned 403; SN)
- **[S2]** AI4Mars v0.6 on Zenodo: https://zenodo.org/records/15995036 (F)
- **[S3]** NASA NTRS abstract: https://ntrs.nasa.gov/citations/20220008371 (F)
- **[S4]** NASA Open Data: https://data.nasa.gov/dataset/ai4mars-a-dataset-for-terrain-aware-autonomous-driving-on-mars (SN)
- **[S5]** S5Mars: https://arxiv.org/abs/2207.01200 (F, abstract); project page https://jhang2020.github.io/S5Mars.github.io/ (SN)
- **[S6]** Wang et al., Semi-supervised learning for Mars imagery classification and segmentation: https://arxiv.org/abs/2206.02180 (F via ar5iv: https://ar5iv.labs.arxiv.org/html/2206.02180)
- **[S7]** Mars32k: https://shakex.github.io/lsmi-mars32k/ (SN)
- **[S8]** SPOC classes on AI4Mars (4 classes: sand, consolidated soil, bedrock, big rocks per SPOC summary) and [S16] below
- **[S9]** HiRISE DTM: https://www.uahirise.org/dtm/about.php (F); PDS/ODE page https://ode.rsl.wustl.edu/mars/pagehelp/Content/Missions_Instruments/Mars%20Reconnaissance%20Orbiter/HiRISE/HiRISE%20DTM.htm (SN)
- **[S10]** USGS MOLA-HRSC blended DEM: https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m (SN)
- **[S11]** Viviano-Beck et al. 2014, JGR Planets 119, 1403: https://ui.adsabs.harvard.edu/abs/2014JGRE..119.1403V ; PDS formula reference https://pds-geosciences.wustl.edu/missions/mro/crism_summary_parameter_reference.pdf (SN)
- **[S12]** SWIM: https://pubs.usgs.gov/publication/70226786 (Morgan et al. 2021) and https://pubs.usgs.gov/publication/70263883 (SN)
- **[S13]** Odyssey neutron hydrogen: https://www.jpl.nasa.gov/images/pia21848-analysis-sharpens-mars-hydrogen-map-hinting-equatorial-water-ice/ (SN)
- **[S14]** SHARAD: https://kiss.caltech.edu/workshops/marsX/presentations/Putzig.pdf (SN)
- **[S15]** Dundas et al. 2018, Science 359:199: https://pubs.usgs.gov/publication/70195019 (SN)
- **[S16]** SPOC: https://nasa-jpl.github.io/SPOC (F)
- **[S17]** JPL AutoNav news: https://www.jpl.nasa.gov/news/autonomous-systems-help-nasas-perseverance-do-more-science-on-mars/ (F); Verma et al., Science Robotics 2023, DOI 10.1126/scirobotics.adi3099 (SN)
- **[S18]** ENav: NASA release https://www.nasa.gov/missions/mars-2020-perseverance/perseverance-rover/nasas-perseverance-mars-rover-ready-to-roll-for-miles-in-years-ahead ; IEEE Trans. Field Robotics paper, IEEE Xplore doc 11265757 (both SN; paper not read)
- **[S19]** MER surface navigation chapter (GESTALT): https://www-robotics.jpl.nasa.gov/media/documents/05_Chapter3_final.pdf (SN)
- **[S20]** Ono et al., Risk-aware planetary rover operation, NTRS: https://ntrs.nasa.gov/citations/20160008261 (SN)
- **[S21]** Endo et al., ICRA 2023: https://arxiv.org/abs/2303.01169 (F via ar5iv)
- **[S22]** GP slip work (e.g. Cunningham et al. 2017; thermal-inertia mixtures): seen only via search-summary citations (U); see https://arxiv.org/pdf/2103.07587 and https://resolver.caltech.edu/CaltechAUTHORS:20110120-094149191 for related slip-learning papers (SN)
- **[S23]** SegFormer https://arxiv.org/abs/2105.15203 ; DeepLabv3+ https://arxiv.org/abs/1802.02611 (F)
- **[S24]** Deep ensembles https://arxiv.org/abs/1612.01474 ; MC dropout https://arxiv.org/abs/1506.02142 ; Evidential DL https://arxiv.org/abs/1806.01768 ; Calibration https://arxiv.org/abs/1706.04599 ; Conformal intro https://arxiv.org/abs/2107.07511 ; Conformal risk control https://arxiv.org/abs/2208.02814 (titles/authors F; contents not re-read)
- **[S25]** Rockafellar & Uryasev, Optimization of CVaR, J. Risk 2000: https://risk.net/journal-risk/2161159/optimization-conditional-value-risk (SN)
- **[S26]** Koenig & Likhachev, D* Lite, AAAI 2002: https://www.ri.cmu.edu/publications/d-lite (SN)
- **[S27]** Karaman & Frazzoli, RRT*: https://arxiv.org/abs/1105.1186 (F, title/authors)
- **[S28]** AEGIS: https://ai.jpl.nasa.gov/public/papers/estlin-isairas2010-aegis.pdf and related pages (SN)
- **[S29]** RichDEM: https://github.com/r-barnes/richdem (F)
- **[S30]** PythonRobotics: https://github.com/AtsushiSakai/PythonRobotics (F)
- **[S31]** segmentation_models.pytorch: https://github.com/qubvel-org/segmentation_models.pytorch (F)
- **[S32]** MAPIE: https://github.com/scikit-learn-contrib/MAPIE (F)
- **[S33]** TorchMetrics CalibrationError: https://lightning.ai/docs/torchmetrics/stable/classification/calibration_error.html (F)
- **[S34]** scikit-fmm: https://github.com/scikit-fmm/scikit-fmm (F)

**Not verified / not done:** rover slope limits; MSL/Mars 2020 wheel geometry; AI4Mars class-code mapping and null value; SPOC-HiRISE public availability; ENav and Science Robotics paper contents; availability of CRISM/SHARAD/HiRISE DTM coverage for any specific AOI; CTX DEM availability; GPyTorch/OMPL/Label Studio/PDAL/Open3D/ASP/ISIS3 documentation; original Mars32k release and licence.
