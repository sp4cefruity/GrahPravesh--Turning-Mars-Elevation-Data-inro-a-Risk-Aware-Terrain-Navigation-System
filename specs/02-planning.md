# Spec 02: Planning and Cost Mapping

Status: draft
Owner: Udit
Reviewer: Disha
Serves criteria: technical depth, explainability, uncertainty

## Purpose

Build a cost map and find a safe, cheap route between a start and a goal.

## Inputs and outputs

In: `HazardMap`, `TerrainGrid`, per-cell uncertainty. Out: `CostMap`, `PathResult`.

## Requirements

1. Cost per cell is a weighted sum of slope, roughness, hazard probability and uncertainty. Weights live in config.
2. Hard blocks (slope above about 25 degrees, crater rim, invalid cells) are separate from soft cost. A weight change can never make a blocked cell passable.
3. A* is the main planner. Dijkstra runs as a baseline and the two are compared on cost and nodes expanded.
4. Bold mode uses mean cost. Cautious mode adds a penalty on cost standard deviation.
5. Safety check: the final path is verified against the hard-block mask and reports max slope and total risk.
6. Each path segment can report its cost breakdown for the dashboard trace.

## Acceptance checks

- [ ] A* and Dijkstra agree on optimal cost on a test grid
- [ ] Forced bad path is rejected by the safety check
- [ ] Cautious mode produces a different, lower-risk path on the demo scene
- [ ] Planning on the full tile finishes in a few seconds

## Uncertainty and failure handling

If no safe path exists, return a clear "no safe path" result with the reason, never a risky path.

## Out of scope

RRT, dynamic replanning, wheel slip.

## Open questions

- Weight values and thresholds pending Disha's research.
