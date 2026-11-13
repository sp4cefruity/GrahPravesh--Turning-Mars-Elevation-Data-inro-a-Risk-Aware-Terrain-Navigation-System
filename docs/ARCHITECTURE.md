# Architecture (draft, owner: Udit)

Status: draft. Disha's research may change the flow. Contracts below are the proposed starting point and freeze at 2:15 AM.

## Data flow

```
raw DEM tile + simulated spectral bands + noise
        |
   [perception]  slope, roughness, aspect, terrain classes, hazard map
        |
   [uncertainty] Monte Carlo over DEM and sensor noise -> mean and std per cell
        |
   [planning]    cost map -> A* (and Dijkstra baseline) -> path, risk score
        |
   [science]     candidate formations -> value / cost -> ranked list with intervals
        |
   [dashboard]   maps, path, targets, traces, cautious toggle
```

`pipeline.py` runs the stages in order and returns one result object the dashboard reads.

## Modules

| Module | Folder | Job |
|---|---|---|
| data | `src/odyssey/data/` | Load the DEM tile, generate simulated bands, noise and missing patches |
| perception | `src/odyssey/perception/` | Derive terrain features and classify hazards |
| uncertainty | `src/odyssey/uncertainty/` | Monte Carlo sampling, per-cell statistics |
| planning | `src/odyssey/planning/` | Cost map, A*, Dijkstra, path safety check |
| science | `src/odyssey/science/` | Detect and rank candidate targets, ice signal |
| dashboard | `src/odyssey/dashboard/` | Interactive UI |

## Contracts (proposed)

All grids are NumPy arrays of shape (H, W), same orientation, same cell size in meters.

- `TerrainGrid`: `dem`, `slope_deg`, `roughness`, `aspect`, `bands` (dict of simulated spectral arrays), `valid_mask` (False where data is missing), `cell_size_m`
- `HazardMap`: `hazard_prob` (0 to 1), `terrain_class` (int labels), `hard_block` (bool, steep or crater rim), `evidence` (per-class rule or model note)
- `CostMap`: `cost_mean`, `cost_std`, `blocked` (bool)
- `PathResult`: `cells` (list of (row, col)), `total_cost`, `risk_score`, `max_slope_on_path`, `safe` (bool from verification), `planner` ("astar" or "dijkstra"), `mode` ("bold" or "cautious")
- `ScienceTarget`: `id`, `location`, `value_mean`, `value_ci` (low, high), `path_cost`, `score`, `score_ci`, `evidence` (string), `kind` ("ice" or "geology")
- `PipelineResult`: all of the above plus `config` (seeds, weights, thresholds) so a run can be reproduced

## Design principles

- Deterministic runs: every random step takes a seed from config.
- Uncertainty is part of every type, not an add-on.
- Hard safety rules (for example slope above about 25 degrees is blocked) are separate from soft cost weights, so a bad weight can never produce an unsafe path.
- Simulated inputs are tagged in the data so the UI and README can say so.

## Assumptions and limits (carry into README)

- One DEM tile, one rover, static map, no wheel slip or power model.
- Spectral and ice layers are simulated, not real CRISM data.
- Thresholds come from `docs/RESEARCH_NOTES.md` once Disha confirms them.
