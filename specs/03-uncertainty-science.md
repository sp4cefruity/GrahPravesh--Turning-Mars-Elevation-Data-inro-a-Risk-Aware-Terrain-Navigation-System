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
- [ ] Works with a stub path cost, before the real planner lands

## Uncertainty and failure handling

Missing data raises uncertainty in that region. Conflicting bands widen the interval.

## Out of scope

Bayesian deep models, real spectral unmixing, tour planning across targets.

## Open questions

- Ice signal model is shared with `specs/05-data.md`. Saptarshi owns both, so decide it there.
