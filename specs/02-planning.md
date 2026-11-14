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
3. A* (8-connected) is the main planner. Dijkstra is the optimality check, compared on cost and nodes expanded.
4. Edge cost is Gaussian CVaR: `mean + std * phi(z_alpha) / (1 - alpha)`. Bold is `alpha = 0`, cautious is `alpha = 0.95`. One dial.
5. Blocked cells are inflated with a distance-growing margin to model localization drift. The margin is `inflate_r0 + inflate_growth * distance from start`, in cells. `PipelineConfig.drift_margin_cells(shape)` returns its largest value for a grid, so other stages can read it.
6. Corridor is the set of cells where `D_start + D_goal <= (1 + tau) * best cost`.
7. Safety check: the final path is verified against the blocked mask on the true (uninflated) hazards. Report max slope and total risk. Fail loudly on a violation.
8. One path per candidate in bold and cautious mode. Each segment can report its cost breakdown for the dashboard trace.
9. Baselines B0 and B1 run beside the proposed planner for the default goal (pipeline step 8, `planning_extras`).
   - B0: shortest path with A* where cells steeper than `b0_slope_limit_deg` are blocked.
   - B1: reference reproduction of Brad and Balog, Electronics 2025, 14(5), 921 (see `docs/MODEL_AND_BASELINE_PLAN.md` sections 2.1 and 8). `cost = z / (friction + eps)` with plain A*, no slope limit, no `hazard_prob`, no uncertainty. `z` is terrain elevation shifted to be positive (`dem - min(dem) + b1_z_offset_m`). Friction comes from `b1_friction_by_class`, indexed by `terrain_class`, in the paper's 0.1 to 0.9 style. Unknown class labels, or a missing class map, use `b1_friction_fallback`. The paper classifies by RGB thresholds and we use our terrain classes, so this reproduces the cost form, not the exact friction map. All values are assumptions.
   - Baselines may cross true blocked cells. That is reported (`safe` False with a reason), not raised, because it is the comparison.
10. Risk-versus-length curve over alpha. When no safe path exists, return "no safe path" with the reason and `min_feasible_risk`. Never return a risky path.
11. Plan on at most `planning_grid_size` (default 256) cells per side, so sweeps take seconds. numba is optional, not required. A grid at or below that size is planned as is. Above it, with block size `f = ceil(max side / planning_grid_size)`:
    - `res.terrain`, `res.hazards` and `res.cost_map` stay full resolution. Planning builds a coarse copy inside `plan_paths` and `plan_extras` (`planning/coarse.py`). The contracts and stage signatures do not change.
    - Block reduction: mean for continuous fields and the cost map, any for `hard_block` and `blocked`, all for `valid_mask`, most frequent label for `terrain_class` and `evidence_code`. The coarse cost map is reduced from the full one, not rebuilt, so weights and the roughness scale stay identical.
    - The start and each candidate map to their block. Their blocks are opened on the coarse grid, because the real cells are checked at full resolution.
    - The drift margin keeps its size in metres: `inflate_r0 / f` on the coarse grid, same `inflate_growth`. At full resolution the refinement uses the exact margin from requirement 5.
    - The coarse route is refined with A* at full resolution inside the blocks it crosses (then those blocks grown by one block). Returned cells are full resolution, start and goal are the exact cells. If refinement fails the result is "no safe path" with a reason.
    - `total_cost` is the full resolution CVaR cost of the refined path. It is near optimal, not guaranteed optimal (on a 512 by 512 synthetic test scene it was within about 1.5 percent of full resolution A*). The Dijkstra check runs on the coarse search and on the refinement.
    - A blocked block can hide an open cell, so a goal reachable only through a one cell gap can come back as "no safe path". This is conservative.
    - The final safety check in the pipeline always uses the true full resolution blocked mask. The pipeline adds a note when the coarse grid was used.
12. Metric definitions (used by the risk curve, `PathResult` and the dashboard):
    - `risk_score` = sum of `p_haz` over the cells of the path. `inf` when there is no safe path.
    - `hazard_violation_rate` = share of path cells whose `p_haz` is above `violation_p_haz` (default 0.5, an assumption), in 0 to 1. NaN when there is no safe path.
    - `max_slope_on_path` = largest `slope_deg` over the path cells.
13. Build order: tiny test grid with A* and Dijkstra, safety check, cost map on dummy hazards, alpha dial, then corridor, inflation, curve, B0 and B1.
14. Loop guard (no "safer position" oscillation). Today the planner is one shot and never relocates the rover, so it cannot loop. Any step that moves a start or goal to a safer cell, or re-plans after the map changes, must use `planning/progress.py`:
    - `snap_to_safe(passable, cell, max_radius)`: nearest passable cell by Euclidean distance, ties broken by (row, col). Deterministic, so the same input always gives the same cell. Returns None when nothing is within `max_radius`, and the caller reports "no safe path" with that reason.
    - A snap is picked once and committed. It is not re-picked on later passes.
    - `ProgressGuard` tracks the cells visited and the replans used. `allow_switch(old_cost, new_cost)` accepts a new route only if it is cheaper by more than `switch_margin` (relative, default 0.05, an assumption), so two near equal routes cannot alternate.
    - `ProgressGuard.visit(cell)` raises `NoProgress` when a cell is entered more than `max_revisits` times (default 2, an assumption). `ProgressGuard.replan()` raises `NoProgress` after `max_replans` (default 10, an assumption).
    - `NoProgress` fails loudly with a reason, like the safety check. The result is "no safe path", never a risky path.
    - Dynamic replanning itself stays out of scope. This requirement only makes sure that when it is added, it cannot loop.

## Acceptance checks

- [ ] A* and Dijkstra agree on optimal cost on a test grid
- [ ] Forced bad path is rejected by the safety check
- [ ] Changing a weight never unblocks a blocked cell (tested)
- [ ] Cautious mode produces a different, lower-risk path on the demo scene
- [ ] No safe path case returns the reason and `min_feasible_risk`
- [ ] Planning on the full tile finishes in a few seconds (512 input, 5 candidates: about 4.5 s, tested safe against the full resolution mask)
- [ ] Grid at or below `planning_grid_size` is planned unchanged (tested)
- [ ] `snap_to_safe` is deterministic, breaks ties by (row, col), and returns None past `max_radius` (tested)
- [ ] A forced two cell oscillation raises `NoProgress` (tested)
- [ ] A near equal replacement route is rejected by the switch margin (tested)

## Uncertainty and failure handling

If no safe path exists, return a clear "no safe path" result with the reason, never a risky path. Cells with `valid_mask = False` are blocked.

## Out of scope

RRT, dynamic replanning, wheel slip.

## Open questions

- Weight values and thresholds: use the working values in `docs/ARCHITECTURE.md` until Disha cites better ones.
