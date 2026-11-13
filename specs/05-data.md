# Spec 05: Data

Status: draft
Owner: Saptarshi
Reviewer: Disha
Serves criteria: uncertainty, technical depth, explainability

## Purpose

Provide the input scene: a real DEM tile plus simulated spectral bands, noise and missing data, all reproducible from a seed. Also provide a separate truth record so evaluation is scored on data the planner never saw.

## Inputs and outputs

In: `tile_id`, noise settings, seed. Out: the raw part of `TerrainGrid` (`dem`, `bands`, `valid_mask`, `cell_size_m`). Perception adds slope, roughness and aspect on top. See `docs/ARCHITECTURE.md`.

Also out (proposed, needs Udit): `SceneTruth` with the full resolution truth DEM, planted science targets (location, kind, latent value), the conflict zone mask and the active data source. Used only by evaluation, never by the planner.

## Dataset

| Tile | Source | Role |
|---|---|---|
| T1 | DTM A, Jezero HiRISE `DTEEC_023524_1985_023379_1985_U01` | Demo scene. All tuning happens here only |
| T2 | DTM A | Held out, different texture, same site |
| T3 | DTM A | Stress, steepest crop (scarp or crater wall) |
| T4 | DTM B, second HiRISE DTM, product id to be chosen | Held out, new site |
| T5 | DTM B | Optional, only if T1 to T4 are done by 2:15 AM |

Each tile is a 512 by 512 crop resampled to about 1 m cells. Source product, pixel window and licence note for each tile live in `src/odyssey/data/tiles.yaml`. Terrain coverage of both DTMs is unverified until we look at them. Cut order if late: T5, then T4.

## Requirements

1. Load and crop each tile listed in `tiles.yaml`. Try a windowed HTTP read first, then a full download, then a bundled crop, then a synthetic DEM. Record source and licence for the README.
2. Build a truth and input pair per tile. Truth is the 1 m DEM. Input is block averaged to 2 m plus spatially correlated noise. The planner gets the input only.
3. Generate 5 simulated spectral bands by linear mixing of 4 endmembers (basalt, hydrated clay, dust or sand, ice) over a latent material map tied to slope, curvature and elevation. Add a simulated ice band and a thermal proxy band. Tag every simulated layer as simulated.
4. Plant 8 to 12 science targets per tile with a known latent value, so ranking quality can be measured against an oracle.
5. Inject configurable sensor noise, missing data patches (random blocks plus one seam stripe) and one conflict zone where the ice band reads high and the thermal band reads low.
6. Flag likely DTM artifacts (nodata, very flat interpolated patches, sharp step lines). Nodata goes to `valid_mask`. Flagged cells get a larger elevation sigma (base 0.3 m). Never fill silently.
7. Same seed gives the same scene. Noise level is a single config value so the dashboard can change it.
8. Cache the processed tile so reloads are fast. Simulated layers are regenerated from `(tile_id, seed, noise_level)`, not stored.

## Acceptance checks

- [ ] Two loads with the same seed are identical
- [ ] Missing patches show as `valid_mask = False`
- [ ] Simulated layers carry a visible tag the dashboard can read
- [ ] Tile loads in a few seconds from cache
- [ ] Every tile in `tiles.yaml` loads, or reports which fallback it used
- [ ] Input slope differs from truth slope, and the gap grows with noise level
- [ ] Planted targets all sit on valid cells

## Uncertainty and failure handling

If the download fails, fall back to a bundled copy of the tile or a synthetic terrain, and say so in the output. Each tile carries its own elevation sigma from its DTM's documentation. Results are reported per tile and per site, never pooled, so a site difference cannot hide as noise.

## Out of scope

- Real CRISM or other multispectral products.
- AI4Mars and any surface camera imagery. The SegFormer side track is dropped (decided 2026-11-14).
- Claims about real ice at Jezero (about 18 N). The ice signal is a test scenario for the method.

## Open questions

- Udit: add `tile_id` to the run config, and approve the `SceneTruth` object for evaluation data. Also update "One DEM tile" in ARCHITECTURE assumptions to "one tile per run, 4 to 5 tiles from two DTMs".
- Disha: sign off on the ice and material simulation model above. Decide whether the dashboard gets a tile selector or a results table for T2 to T4.
- Saptarshi: choose the DTM B product id from the HiRISE catalog (prefer a smaller file with dunes or an ice scarp). Confirm the HiRISE DTM licence before committing crops.
- Does the HiRISE server allow HTTP range reads? Test first, 15 minutes max. If no real tile is usable within about 30 minutes, switch to the seeded synthetic DEM so nobody is blocked, and say so in the output.
- Publish a synthetic DEM and a small sample `TerrainGrid` first, so perception and the dashboard can build against it right away.
