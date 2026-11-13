# Spec 02: Planning and Cost Mapping

Status: approved
Owner: Udit
Reviewer: Disha
Serves criteria: technical depth, explainability, uncertainty

## Purpose

Build the cost map and find a safe, cheap route from a start to each science candidate.

## Inputs and outputs

In: `TerrainGrid`, complete `HazardMap` (including `hard_block`, `slope_std_deg`, `epistemic_std`), candidate locations from science. Out: `CostMap`, one `PathResult` per candidate and mode, risk curve, baseline paths.

## Requirements

1. Cost map: `cost_mean` is a weighted sum of normalised slope, roughness and `hazard_prob`. `cost_std` comes from first order propagation of `slope_std_deg` and `epistemic_std` through the same weights. Weights live in config and are labelled assumptions.
2. `blocked` = `hard_block` OR `~valid_mask`. Hard blocks are separate from soft cost. A weight change can never make a blocked cell passable.
3. A* (8-connected, numba) is the main planner. Dijkstra is the optimality check, compared on cost and nodes expanded.
4. Edge cost is Gaussian CVaR: `mean + std * phi(z_alpha) / (1 - alpha)`. Bold is `alpha = 0`, cautious is `alpha = 0.95`. One dial.
5. Blocked cells are inflated with a distance-growing margin to model localization drift.
6. Corridor is the set of cells where `D_start + D_goal <= (1 + tau) * best cost`.
7. Safety check: the final path is verified against the blocked mask on the true (uninflated) hazards. Report max slope and total risk. Fail loudly on a violation.
8. One path per candidate in bold and cautious mode. Each segment can report its cost breakdown for the dashboard trace.
9. Baselines B0 (slope threshold plus A*) and B1 (Electronics-paper style cost) run beside the proposed planner for the default goal.
10. Risk-versus-length curve over alpha. When no safe path exists, return "no safe path" with the reason and `min_feasible_risk`. Never return a risky path.
11. Use numba, or plan on a 256 by 256 grid, so sweeps take seconds.
12. Build order: tiny test grid with A* and Dijkstra, safety check, cost map on dummy hazards, alpha dial, then corridor, inflation, curve, B0 and B1.

## Acceptance checks

- [ ] A* and Dijkstra agree on optimal cost on a test grid
- [ ] Forced bad path is rejected by the safety check
- [ ] Changing a weight never unblocks a blocked cell (tested)
- [ ] Cautious mode produces a different, lower-risk path on the demo scene
- [ ] No safe path case returns the reason and `min_feasible_risk`
- [ ] Planning on the full tile finishes in a few seconds

## Uncertainty and failure handling

If no safe path exists, return a clear "no safe path" result with the reason, never a risky path. Cells with `valid_mask = False` are blocked.

## Out of scope

RRT, dynamic replanning, wheel slip.

## Open questions

- Weight values and thresholds: use the working values in `docs/ARCHITECTURE.md` until Disha cites better ones.
