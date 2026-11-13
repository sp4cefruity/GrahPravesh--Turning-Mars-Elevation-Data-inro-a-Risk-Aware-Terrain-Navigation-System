# Spec 01: Perception and Data

Status: draft
Owner: Disha
Reviewer: Udit
Serves criteria: technical depth, uncertainty, explainability

## Purpose

Turn a real DEM tile plus simulated spectral bands into slope, roughness, terrain classes and a hazard map.

## Inputs and outputs

In: DEM tile (about 512 by 512), simulated bands, noise settings.
Out: `TerrainGrid` and `HazardMap` (see `docs/ARCHITECTURE.md`).

## Requirements

1. Load and crop the DEM, record source and licence.
2. Derive slope, roughness and aspect.
3. Generate simulated spectral bands, a simulated ice signal, noise and missing-data patches. Tag them as simulated.
4. Rule-based hazards first: steep slope, high roughness, crater rim. Thresholds come from cited sources in `docs/RESEARCH_NOTES.md`.
5. Terrain classes: Random Forest baseline. CNN is an experiment, kept only if it beats the baseline and we can still explain its output.
6. Every hazard cell carries an evidence note (which rule or model fired).

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

- Which tile? Disha to confirm by 1:00 AM.
