# Spec 05: Data

Status: draft
Owner: Saptarshi
Reviewer: Disha
Serves criteria: uncertainty, technical depth, explainability

## Purpose

Provide the input scene: a real DEM tile plus simulated spectral bands, noise and missing data, all reproducible from a seed.

## Inputs and outputs

In: DEM source, noise settings, seed. Out: the raw part of `TerrainGrid` (`dem`, `bands`, `valid_mask`, `cell_size_m`). Perception adds slope, roughness and aspect on top. See `docs/ARCHITECTURE.md`.

## Requirements

1. Load and crop the DEM to about 512 by 512. Record the source and licence for the README.
2. Generate simulated spectral bands and a simulated ice signal. Tag every simulated layer as simulated.
3. Inject configurable sensor noise, missing-data patches and at least one conflicting reading between two bands.
4. Same seed gives the same scene. Noise level is a single config value so the dashboard can change it.
5. Cache the processed tile so reloads are fast.

## Acceptance checks

- [ ] Two loads with the same seed are identical
- [ ] Missing patches show as `valid_mask = False`
- [ ] Simulated layers carry a visible tag the dashboard can read
- [ ] Tile loads in a few seconds from cache

## Uncertainty and failure handling

If the download fails, fall back to a bundled copy of the tile or a synthetic terrain, and say so in the output.

## Out of scope

Real CRISM or other multispectral products.

## Open questions

- Which tile? Saptarshi to confirm with Disha by 1:00 AM.
- Simulation model for the ice signal, pending Disha's research.
