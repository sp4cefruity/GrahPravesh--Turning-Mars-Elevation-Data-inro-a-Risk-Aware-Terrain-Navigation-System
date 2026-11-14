# Research Notes (owner: Disha)

Disha adds ideas, gaps and findings here. Agents read this before touching a spec. Anything that changes the flow gets a dated entry and a note on which spec it affects.

## How to add an entry

```
### <short title> (time, author)
What we learned:
Why it matters for the build:
Specs affected:
Status: proposed | accepted | rejected
```

## Open research questions

- Which public DEM tile to use (Jezero or another) and where to download it quickly.
- How to simulate multispectral bands and an ice signal in a way that is defensible.
- Answered: Random Forest is enough for terrain classes. See the CNN entry below.
- What slope and roughness thresholds are used in real rover practice, so our hazard rules are cited, not guessed.
- Sensible cost function weights, and how to justify them.

## Entries

### Model and baseline plan from papers and literature (2026-11-14, Disha via Claude research agent)
What we learned: Full survey and design plan in `docs/MODEL_AND_BASELINE_PLAN.md`. Covers the two reference papers, datasets (AI4Mars, HiRISE DTM), baseline (slope-threshold cost, A*/Dijkstra, weighted science score) versus proposed model (ensemble segmentation, mean-plus-variance cost, CVaR or chance-budget planning, Monte Carlo science ranking with rank intervals), metrics, ablations. No verified public orbital terrain labels were found, so a small hand-labelled classifier is the main risk. Rover slope limits and AI4Mars class codes are unverified.
Why it matters for the build: Gives cited candidates for hazard thresholds, cost weights and the uncertainty approach. Its 5-week timeline does not fit the hackathon; use `docs/TIMELINE.md`.
Specs affected: 01-perception, 02-planning, 03-uncertainty-science (reconciled into the specs and `docs/ARCHITECTURE.md`).
Status: accepted (Udit, after talking with Disha)

### DEM noise model for the Monte Carlo (2026-11-14, Disha)
What we learned: HiRISE DTMs are documented with vertical precision of "tens of centimeters" and artifacts such as boxes and faceting (source S9 in `docs/MODEL_AND_BASELINE_PLAN.md`, tagged F there, not re-checked by us). `docs/MODEL_AND_BASELINE_PLAN.md` section 5 also says DEM errors are spatially correlated, with a correlation length of about 10 to 50 m, and that independent per-pixel noise overstates slope noise.
Model implemented in `src/odyssey/uncertainty/montecarlo.py`: each draw adds a Gaussian random field to the DEM (white noise, Gaussian filter, rescaled to std `sigma_z`). `sigma_z = noise_level * 0.3 m` and the correlation length is 20 m. Both 0.3 m and 20 m are ASSUMPTIONS picked inside the quoted ranges, not fitted. 50 draws by default (`n_dem_draws`), seeded by `seeds.uncertainty`. Only the running mean and std are kept. The noise is the same over the whole tile, so it does not model local artifact masks. The real DTM error is unverified for our tile.
Why it matters for the build: gives `slope_std_deg`, which feeds `cost_std` in the planner. `noise_level` is the single dial the dashboard changes.
Specs affected: 01-perception.
Status: accepted for the demo, labelled assumption.

### Perception thresholds, status (2026-11-14, Disha)
What we learned: no published rover slope limit was verified (`docs/MODEL_AND_BASELINE_PLAN.md` says so). Nothing below is cited. All values live in `src/odyssey/perception/params.py` or `PipelineConfig`.
- Hard block slope 25 deg and `hazard_delta` 0.9: working values from `docs/ARCHITECTURE.md`, assumptions.
- P_slope is a normal CDF centred at 20 deg with a 3 deg spread. Assumption, chosen between the 15 deg soft scale and the 25 deg limit.
- P_rough is a normal CDF centred at 0.25 m roughness (plane-fit residual std, 3 by 3 window) with a 0.10 m spread. Assumption. The idea is that a bump near half a wheel diameter matters, but the wheel size is unverified.
- Crater rim rule: convexity above 0.05 per m with slope above 10 deg within two cells. Assumption, tuned only on a synthetic ring.
- Terrain classes come from the rules above (pseudo-labels), so the Random Forest agrees with the rules by construction. It shows how stable the rule boundaries are and gives vote spread as `epistemic_std`. It is not an independent check.
- Cells next to a missing patch use heights copied from the nearest valid cell inside the kernels, so their slope is less reliable. They are not flagged separately yet.
Why it matters for the build: judges can see which numbers are assumptions. A sensitivity sweep (hard limit 10, 15, 20, 25) is still to do.
Specs affected: 01-perception (open question on cited thresholds stays open).
Status: proposed, citations still needed.

### CNN versus Random Forest for terrain classes (2026-11-14, Udit)
What we learned: A small 3-layer CNN with a 3-member ensemble, trained on the same rule pseudo-labels, scored held-out macro F1 0.130 against 0.793 for the Random Forest on tiles T4 and T5 (train on T1 to T3). Calibration was also worse (ECE 0.127 against 0.010). Full table in `specs/01-perception.md` and `outputs/cnn_eval.md`. Scores measure imitation of the rules, not accuracy on real terrain. Not tried: more training steps, step and convexity channels, rare-class patch sampling.
Why it matters for the build: The forest stays the default. The CNN is kept behind `classifier="cnn"` as an optional experiment. torch is an optional dependency.
Specs affected: 01-perception.
Status: accepted

### Loop guard for snapping and replanning (2026-11-14, Udit)
What we learned: Moving a goal to a "safer" cell or replanning can oscillate between near equal options. A deterministic snap, a switch margin and revisit and replan limits prevent that.
Why it matters for the build: The planner is one shot today, so it cannot loop. The guard is wired in for goals inside the drift margin and is off by default (`snap_goal_radius_cells = 0`).
Specs affected: 02-planning (requirement 14).
Status: accepted
