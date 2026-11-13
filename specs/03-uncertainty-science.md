# Spec 03: Uncertainty and Science Ranking

Status: draft
Owner: Saptarshi
Reviewer: Disha
Serves criteria: uncertainty, reasoning, explainability

## Purpose

Quantify how sure we are about the map, then rank science targets with confidence bands.

## Inputs and outputs

In: `TerrainGrid`, `HazardMap`. Out: per-cell mean and standard deviation, a list of `ScienceTarget`.

## Requirements

1. Monte Carlo with about 50 to 100 samples, perturbing DEM and sensor values with a documented noise model and seed.
2. Report per-cell hazard probability, cost mean and cost standard deviation.
3. Detect candidate targets (for example ice signal peaks and geologically distinct features) from the simulated bands and terrain classes.
4. Score each target as expected value divided by traversal cost, with a confidence interval from the Monte Carlo runs.
5. Each target carries a plain-language evidence string: which signals, how reachable, how sure.
6. Handle conflicting sensor readings by widening the interval, and say so in the evidence string.
7. DEM Monte Carlo uses spatially correlated noise (Gaussian-filtered white noise) and calls Disha's slope kernel. Store only mean and std. Fill `slope_std_deg`, `cost_mean` and `cost_std`.
8. Science ranking uses 1000 Monte Carlo draws over feature noise and weights. Output `rank_interval` and `p_top3` per target. Access cost is the path CVaR from the planner.
9. Run the SegFormer fine-tune on the RTX 3050 if the side track is on (script from Disha). Drop at 4:00 AM if it is not working.

## Acceptance checks

- [ ] More noise gives wider intervals (checked on two noise levels)
- [ ] Rank order can change when uncertainty is high, and the UI shows overlapping bands
- [ ] Every target has a non-empty evidence string
- [ ] Same seed gives the same ranking

## Uncertainty and failure handling

Missing data raises uncertainty in that region. Targets in missing regions are listed with low confidence, not dropped.

## Out of scope

Bayesian deep models, real spectral unmixing.

## Open questions

- Noise model details after Disha's research.
- Value function for "geological interest" (needs a defensible definition).
