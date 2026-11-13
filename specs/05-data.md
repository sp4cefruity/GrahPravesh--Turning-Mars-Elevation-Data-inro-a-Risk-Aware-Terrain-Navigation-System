# Spec 05: Data

Status: approved
Revised: 2026-11-14, to match the implementation (2 m input grid, windowed reads, band names, pipeline entry point). Disha to re-check.
Owner: Saptarshi
Reviewer: Disha
Serves criteria: uncertainty, technical depth, explainability

## Purpose

Provide the input scene: a real DEM tile plus simulated spectral bands, noise and missing data, all reproducible from a seed. Also provide a separate truth record so evaluation is scored on data the planner never saw.

## Inputs and outputs

The pipeline calls `odyssey.data.load_terrain(config)` (see `pipeline.STAGES`). It reads `config.seeds.data` and `config.noise_level`. The tile comes from `config.tile_id` if that field exists, else `odyssey.data.DEFAULT_TILE` ("T1"). `PipelineConfig` has no `tile_id` yet, see Open questions.

Out of `load_terrain`: a `TerrainGrid` (raw part, perception adds slope, roughness and aspect):

- `dem`: float32, 256 by 256, NaN where missing. Real elevation, degraded to 2 m cells plus simulated correlated noise (see Requirement 2).
- `valid_mask`: bool, False where data is missing. Matches the NaN cells of `dem` and of every band.
- `cell_size_m`: about 2.0 (twice the source cell size of the tile).
- `bands`: dict of float32 arrays, 256 by 256, NaN where missing. All simulated. Names are fixed by `science/model.py`: `ice_simulated`, `thermal_simulated` (high means ice consistent), `mineral_simulated`, plus spectral bands `b1` to `b5`.
- `simulated_layers`: list of the band names above. `dem` is not listed, because the elevation is real. The noise added to it is simulated and `source` says so.
- `source`: a string naming the DTM product, the tile, whether it came from cache or a window read, and the degradation.

`odyssey.data.load_scene(config)` returns `(TerrainGrid, SceneTruth)`. `SceneTruth` is for evaluation only and must never reach the planner:

- `dem_truth`: the 512 by 512 source crop at about 1 m, NaN where missing.
- `targets`: planted targets, each `{id, row, col, kind, value}` with id `P0` and up, kind `ice` or `geology`, value 0.2 to 1.0. Rows and columns are on the 256 grid.
- `conflict_zone`: bool mask where the ice and thermal bands disagree.
- `gap_mask`: bool mask of injected missing patches.

## Dataset

Source tiles are 512 by 512 crops at about 1 m, read straight from the PDS archive with no resampling. Each tile keeps its product's own cell size. The windows, URLs, file layout and label constants live in `src/odyssey/data/tiles.yaml`.

| Tile | Product | Window (row, col) | What it is | Role |
|---|---|---|---|---|
| T1 | A | 7700, 3600 | Two overlapping craters with a rim, mixed ground | Demo scene. All tuning happens here only |
| T2 | A | 10900, 5500 | Rolling, featureless ground | Held out, same site |
| T3 | A | 4600, 5500 | Flat with one small, very steep crater | Stress |
| T4 | B | 2600, 1250 | Large scarp, 110 m of relief, 23 percent of cells over 25 degrees | Held out, new site, steep stress |
| T5 | B | 5400, 2500 | Moderately steep slope field | Optional, new site |

- Product A: `DTEEC_023524_1985_023379_1985_U01`, Jezero crater, 8235 by 21258 cells, 1.0097 m per cell, about 700 MB.
- Product B: `DTEEC_021466_1230_021954_1230_A01`, Promethei Terra ice scarp area at about 56.6 S, 6053 by 8223 cells, 0.9954 m per cell, about 199 MB. It is not confirmed to be the exact product used in Dundas et al. 2018.
- Windows were chosen from a 64 pixel scout grid (14 by 5 on A, 12 by 5 on B), not an exhaustive search.
- Licence of both products is unverified. Cached crops (`data/tiles/*.npz`) stay out of git until it is confirmed.

## Requirements

1. Load each tile with HTTP range requests, about 1 MB and 10 seconds per tile. A full download is dropped: the measured throughput was 0.36 MB/s, so product A would take about 33 minutes. The crop is cached to `data/tiles/<tile_id>.npz` and reused. Missing cells (the label's no-data bit pattern) become NaN and `valid_mask = False`. Nothing is filled.
2. Build the planner input. Block mean the 512 truth to 256 at 2 m (a cell with any missing source cell is missing). Add spatially correlated Gaussian noise with std `sigma_z_m * noise_level` (0.3 m at level 1, an assumption, not measured) and a correlation length of 8 cells (16 m).
3. Simulate the material mix per cell (basalt, clay, dust, ice) as a softmax of a terrain term and correlated random patches. Basalt follows slope, clay and ice follow low ground, dust follows flat ground. Ice is kept rare on purpose (score bias 2.5, about 7 percent background) so planted ice targets stand out. The coupling to terrain is our assumption, not physics.
4. Generate the bands by linear mixing of 4 invented endmember spectra into `b1` to `b5`. `ice_simulated` and `thermal_simulated` both start from the ice fraction. `mineral_simulated` is the clay fraction.
5. Plant 10 targets per tile on valid cells (at least 10 cells from the edge), each a Gaussian blob of radius 6 cells added to its material (ice for `ice`, clay for `geology`). Signal strength follows the target value.
6. Corrupt the scene. Band noise is independent per cell with std `0.03 * noise_level`. Missing data is 6 random blocks (8 to 30 cells) plus one partial seam stripe (90 by 3 cells, partial so it cannot wall off the map). One conflict zone (radius 10 cells) sets `ice_simulated` to 0.9 and `thermal_simulated` to 0.1.
7. Same seed gives the same scene. Each component (DEM noise, materials, gaps, targets, band noise) has its own random stream, so the noise level changes amplitude only and never moves the gaps or targets. Noise level is one config value.
8. Only the raw crop is cached. Simulated layers are regenerated from `(tile_id, seed, noise_level)`, about 0.15 s.

## Acceptance checks

Checked by `tests/test_data.py` (16 tests, 5 of them on the real tiles T1 to T5) unless noted.

- [x] Two loads with the same seed are identical
- [x] The noise level changes amplitude only, not gaps or targets
- [x] Missing patches show as `valid_mask = False`, and as NaN in the DEM and every band
- [x] Simulated layers are listed in `simulated_layers`
- [x] A tile loads from cache in under 3 seconds
- [x] Every tile T1 to T5 loads and its elevations sit inside the label's valid range
- [x] The input DEM differs from truth, and the gap grows with the noise level
- [x] Planted targets all sit on valid cells
- [x] The conflict zone has ice high and thermal low
- [x] The full pipeline completes on T1 to T5 with every stage real (run by hand, not in pytest)

## Uncertainty and failure handling

- Each product carries a vertical error `sigma_z_m` (0.3 m, an assumption based on the HiRISE statement of tens of centimetres), used for the input noise.
- If a window read fails, `load_tile` raises with the reason. There is no silent fallback.
- Not built yet: the synthetic DEM fallback (a missing data stage now stops the run), flagging likely DTM artifacts (seams, interpolated patches) and giving flagged cells a larger sigma. Only nodata is handled today.
- Results are reported per tile and per site, never pooled.

## Out of scope

- Real CRISM or other multispectral products.
- AI4Mars and any surface camera imagery. The SegFormer side track is dropped (decided 2026-11-14).
- Claims about real ice at Jezero (about 18 N). The ice signal is a test scenario for the method.

## Findings that affect other roles

- Slope at the native 1 m is mostly pixel noise. Nearly flat Jezero patches (1 to 2 m of relief in 64 m) show 8 to 15 degrees at the 95th percentile. The 2 m input reduces this, and the slope kernel should still smooth first.
- Tile T4 has a wall of steep ground across the whole tile. Routes that cross it can have no safe path, which exercises the "no safe path" result. For a normal demo pick start and goal on the same side.

## Open questions

- Udit: add `tile_id` (default "T1") to `PipelineConfig`. Until then the tile is `odyssey.data.DEFAULT_TILE`.
- Udit: `docs/ARCHITECTURE.md` and `README.md` still say one tile, a 512 by 512 crop and a 700 MB download, and list the SegFormer side track.
- Saptarshi: `find_candidates` takes the highest few peaks of the whole ice and geology map (about 3 ice and 2 geology by default), so it mostly misses the planted targets. On T1 and T3 at most 2 of 10 were found, even with the planted signal made 5 times stronger. Options: score against the clean material fields instead of the planted blobs (add them to `SceneTruth`), or raise `n_candidates` for evaluation runs.
- Saptarshi: confirm the licence of both products before committing any crops.
- Saptarshi: build the synthetic DEM fallback and the artifact flags, or cut them from the spec.
- Disha: perception received NaN in `dem` without crashing on all five tiles. Confirm that is the behaviour you want.
