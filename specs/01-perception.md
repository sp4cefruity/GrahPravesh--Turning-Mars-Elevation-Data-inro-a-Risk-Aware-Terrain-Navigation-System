# Spec 01: Perception

Status: draft
Owner: Disha
Reviewer: Udit
Serves criteria: technical depth, uncertainty, explainability

## Purpose

Turn the raw scene from `specs/05-data.md` into slope, roughness, terrain classes and a hazard map.

## Inputs and outputs

In: raw `TerrainGrid` from the data module (DEM, simulated bands, valid mask).
Out: full `TerrainGrid` and `HazardMap` (see `docs/ARCHITECTURE.md`).

## Requirements

1. Derive slope, roughness and aspect from the DEM.
2. Rule-based hazards first: steep slope, high roughness, crater rim. Thresholds come from cited sources in `docs/RESEARCH_NOTES.md`.
3. Terrain classes: Random Forest baseline. CNN is an experiment, kept only if it beats the baseline and we can still explain its output.
4. Every hazard cell carries an evidence note (which rule or model fired).

## Acceptance checks

- [ ] Slope map visually matches the DEM relief
- [ ] Missing patches show up as `valid_mask = False`, not as zeros
- [ ] Hazard map for the demo scene is reviewed by a teammate
- [ ] CNN versus baseline comparison written down in the research notes (even if CNN is dropped)

## Uncertainty and failure handling

Missing cells are flagged, never silently filled. Noise level is configurable so the demo can raise it.

## Out of scope

Real multispectral products, atmospheric correction.

## Open questions

- Tile choice is owned by Saptarshi in `specs/05-data.md`. Disha confirms it by 1:00 AM.
