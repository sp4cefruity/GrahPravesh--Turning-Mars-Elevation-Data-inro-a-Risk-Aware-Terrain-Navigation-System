# Spec 01: Perception and DEM Monte Carlo

Status: approved
Owner: Disha
Reviewer: Udit
Serves criteria: technical depth, uncertainty, explainability

## Purpose

Turn the raw scene from `specs/05-data.md` into slope, roughness, terrain classes, a hazard map with hard blocks, and a per-cell slope uncertainty from a DEM Monte Carlo.

## Inputs and outputs

In: raw `TerrainGrid` from the data module (DEM, simulated bands, valid mask).
Out: full `TerrainGrid` and a complete `HazardMap`, including `hard_block` and `slope_std_deg` (see `docs/ARCHITECTURE.md`).

## Requirements

1. Derive slope, roughness, step height and aspect from the DEM with our own numpy Horn kernel (no GPL dependency).
2. Rule-based hazards first: steep slope, high roughness, crater rim. Thresholds come from cited sources in `docs/RESEARCH_NOTES.md`. Until cited, use the working values in `docs/ARCHITECTURE.md` (hard block at 25 degrees) and label them assumptions.
3. Terrain classes: Random Forest. Tree votes give `class_probs` and `epistemic_std`. Combine into `hazard_prob = 1 - (1 - P_slope)(1 - P_rough)(1 - P_class)`. Labels come from the rules (pseudo-labels), and the README says so.
4. `hard_block` (bool) is `slope > limit` OR crater rim OR `hazard_prob > delta`. `limit` and `delta` are config values. `delta` is an assumption until tuned. Invalid cells are not handled here, the planner adds `~valid_mask`.
5. Every hazard cell carries an evidence note (which rule or model fired).
6. DEM Monte Carlo (module `src/odyssey/uncertainty/`): 50 to 100 draws, spatially correlated noise (Gaussian-filtered white noise), seeded, calling the slope kernel. Store only mean and std. Fill `slope_std_deg`. Document the noise model in `docs/RESEARCH_NOTES.md`.
7. Noise level is one config value that the dashboard can change.
8. Side track (optional, dropped at 4:00 AM if not working): write the SegFormer-B0 fine-tune script for the AI4Mars subset. It runs on Saptarshi's GPU. A CNN on the DEM is not planned.

## Acceptance checks

- [ ] Slope map visually matches the DEM relief
- [ ] Missing patches show up as `valid_mask = False`, not as zeros
- [ ] `slope_std_deg` is larger at higher noise (two noise levels checked)
- [ ] Same seed gives the same `slope_std_deg`
- [ ] A forced steep patch is marked `hard_block = True`
- [ ] Hazard map for the demo scene is reviewed by a teammate

## Uncertainty and failure handling

Missing cells are flagged, never silently filled. Noise level is configurable so the demo can raise it.

## Out of scope

Real multispectral products, atmospheric correction, a CNN on the orbital tile.

## Open questions

- Tile choice is owned by Saptarshi in `specs/05-data.md`. Disha confirms it as soon as it is picked.
- Cited slope and roughness thresholds, pending research notes.
- DECIDED (dev): option (b). `HazardMap.evidence_code` is an (H, W) int array and `evidence` is the legend `dict[int, str]` from code to note. Every code in the array must have a legend entry (the pipeline checks this). Disha to confirm.
