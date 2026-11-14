# Spec 03: Science Ranking

Status: approved
Owner: Saptarshi
Reviewer: Disha
Serves criteria: uncertainty, reasoning, explainability

The DEM Monte Carlo that used to live here moved to `specs/01-perception.md` (owner Disha). This spec keeps the filename so links still work.

## Purpose

Find candidate science targets and rank them with confidence bands.

## Inputs and outputs

In: `TerrainGrid` (simulated bands, `valid_mask`), complete `HazardMap`, and later the path CVaR from the planner. Out: a candidate list (step 1), then `ScienceTarget[]` (step 2). See `docs/ARCHITECTURE.md`.

## Requirements

1. Step 1, candidates: detect candidates (ice signal peaks and geologically distinct features) from the simulated bands and terrain classes. Compute value with feature noise. No path cost yet. Hand the locations to the planner as a `list[Candidate]` (`id, location, kind, value_mean, value_ci, evidence`, see `docs/ARCHITECTURE.md`). Skip cells closer to a hard block than the planner's inflation margin, read from `config.drift_margin_cells(shape)`, so no candidate sits where the planner can never reach it.
2. Step 2, ranking: access cost is the path CVaR from the planner. Score = value divided by access cost.
3. Ranking Monte Carlo: 1000 draws over feature noise and weights, seeded. Output `value_ci`, `score_ci`, `rank_interval` and `p_top3` per target.
4. Each target carries a plain-language evidence string: which signals, how reachable, how sure.
5. Conflicting sensor readings widen the interval, and the evidence string says so.
6. Targets in missing regions are listed with low confidence, not dropped.
7. Value for "geological interest" is a simple documented score (for example terrain class distinctness times slope-free access). Write the formula in the module docstring and the README. It is an assumption, not science.
8. Run the SegFormer fine-tune on the RTX 3050 if the side track is on (script from Disha). Drop at 4:00 AM if it is not working.

## Acceptance checks

- [ ] More noise gives wider intervals (checked on two noise levels)
- [ ] Rank order can change when uncertainty is high, and the UI shows overlapping bands
- [ ] Every target has a non-empty evidence string
- [ ] Same seed gives the same ranking
- [ ] Works with fabricated path costs, so it can be tested without the planner

## Uncertainty and failure handling

Missing data raises uncertainty in that region. Conflicting bands widen the interval.

## Evaluation against the answer key

`python -m odyssey.science.evaluate --tiles T1,T2,T3,T4,T5 --seeds 0,1,2 --noise 0.5,1,2 --candidates 5,10` builds scenes, runs the real pipeline and scores the science stage. The truth value of a target is what `compute_fields` gives on `SceneTruth.clean_bands` (no sensor noise, no gaps, no conflict fault), so the only difference from the real run is the trouble we injected. Targets in a missing patch are left out of the value metrics.

Result of 90 scenes on 2026-11-14 (details in the table by tile):
- The stated 90 percent value interval holds the true value in about 74 percent of cases (0.67 to 0.87 by tile).
- The stated rank interval holds the true rank in about 75 percent of cases.
- The truly best target is inside the estimated top 3 in 80 percent of runs.
- Rank order agreement (Spearman) averages 0.26: 0.75 on T4, 0.54 on T3, 0.21 on T1, 0.14 on T2 and 0.08 on T5.
- Planted targets are found in about 3 percent of runs, so they are a diagnostic only.

Only 3 seeds per setting, so differences of a few points between runs are noise. Changing the scene of one seed (seed 1, see spec 05) moved T5's best-in-top-3 from 1.00 to 0.67. The study itself is reproducible: two separate runs gave identical tables.

The intervals are narrower than they claim. This is a finding, not a fix: no change has been made to the model.

## Out of scope

Bayesian deep models, real spectral unmixing, tour planning across targets.

## Open questions

- Ice signal model is shared with `specs/05-data.md`. Saptarshi owns both, so decide it there.
- Decided 2026-11-14: the intervals cover the truth about 74 percent of the time against the 90 percent they state. State the measured coverage now (done in the README and above). Calibrate only if time remains: fit one scale factor on T1, the tuning tile, and check it on the held-out tiles T2 to T5 with `python -m odyssey.science.evaluate`. No change has been made to the model.
- Saptarshi: on the synthetic test scene the injected conflict zone is the brightest ice peak, so the top ice candidates sat inside it (estimated 1.0 where the truth was about 0.03). This was seen on the synthetic scene only and not measured on the real tiles.
