# MARS-09 Odyssey

HackInnovision 2026, Track A: Planetary Reconnaissance and Autonomous Navigation.

An uncertainty-aware planner for a Mars rover. It reads terrain data, builds a hazard and cost map, plans a safe route, and ranks science targets while showing how sure it is.

> Status: scaffolding. This README is the final write-up deliverable and gets filled in as we build. Sections marked TODO are filled by the owner named next to them.

## What it does

TODO (Udit, by 8:45 AM): three sentences on the finished behaviour.

## Quick start

TODO (Udit): install and run steps. Must work from a clean checkout.

## Approach

0. **Data** (Saptarshi): load the real DEM tile and generate the simulated spectral bands, noise and missing patches.
1. **Perception** (Disha): derive slope, roughness and aspect from the DEM, classify terrain, build a hazard map.
2. **Uncertainty** (Saptarshi): Monte Carlo over DEM and sensor noise gives a mean and spread for every cell.
3. **Planning** (Udit): cost map, A* with Dijkstra as a baseline, a hard safety rule, a cautious mode that penalises uncertain cells, and a loop guard so snapping a goal to a safer cell or replanning cannot oscillate (off by default).
4. **Science** (Saptarshi): rank candidate formations by value divided by cost, with confidence bands and a written evidence trail.
5. **Dashboard** (Disha): interactive view of all of the above.

## Architecture

See `docs/ARCHITECTURE.md`. The pipeline as a diagram, with the source lines behind each box: `docs/architecture-diagram.html` (open it in a browser).

## Data and assumptions

- Real elevation data: two HiRISE digital terrain models from the NASA Planetary Data System, cropped to five 512 by 512 tiles (T1 to T5) at about 1 m per cell. Credit: NASA/JPL/University of Arizona. HiRISE states its images are public domain. No licence is stated for the DTMs themselves.
  - Product A, `DTEEC_023524_1985_023379_1985_U01`, Jezero crater (tiles T1 to T3).
  - Product B, `DTEEC_021466_1230_021954_1230_A01`, Promethei Terra (tiles T4 and T5).
  - Tile windows and source details are in `src/odyssey/data/tiles.yaml`. The cropped tiles are in `data/tiles/`.
- Simulated: spectral bands, ice signal, sensor noise, missing data patches.
- Results per tile, never pooled across sites: `docs/TILE_RESULTS.md`. Regenerate with `python -m odyssey.data.tile_report --doc docs/TILE_RESULTS.md`.
- The science stage is scored against the simulated truth with `python -m odyssey.science.evaluate`. Its stated 90 percent intervals hold the truth about 74 percent of the time (see `specs/03-uncertainty-science.md`).
- One tile per run (256 by 256 at 2 m, reduced from the 512 by 512 crop with simulated noise added), single rover, static map.

### Modelling assumptions

None of these numbers is fitted to rover data. Every one is a working assumption unless `docs/RESEARCH_NOTES.md` cites it.

- **Terrain classes are rule-derived pseudo-labels.** There is no labelled Mars terrain data in this project. Perception first labels each cell with hand-set rules on slope, roughness and crater rims (5 classes). A Random Forest is then trained on those labels. Its tree votes give the class probabilities and the epistemic spread. Because it learns the rules it was given, it agrees with them by construction. It is not an independent check on the rules. An optional small CNN (`classifier="cnn"`, needs torch) was tried in the same role. It did not match the forest on held-out tiles (macro F1 0.13 against 0.79, see `specs/01-perception.md`), so the forest is the default and the CNN is an experiment only.
- **Perception thresholds are assumptions.** This covers the slope centre (20 degrees), the roughness scale (0.25 m), the rim rule, the DEM noise (0.3 m) and the noise correlation length (20 m). They live in `src/odyssey/perception/params.py` and can be overridden through the `perception` field of `PipelineConfig`.
- **Science value is a documented score, not science.** All spectral bands are simulated, so nothing here is a claim about real ice or minerals. The formulas are in `src/odyssey/science/model.py`, all on a 0 to 1 scale:
  - Ice value is the simulated ice band, scaled from its 2nd percentile to its maximum over valid cells.
  - Geology value is distinctness times slope-free access. Distinctness is the mean of class rarity (from the terrain class probabilities) and the scaled mineral band, when present. Slope-free access is `1 - slope / hard_block_slope_deg`, clipped to 0 to 1.
  - Ranking divides value by the cautious path cost to the target.
- **Value uncertainty is built from four terms added in quadrature:** sensor noise, classifier disagreement, the share of missing data nearby, and an ice versus thermal conflict. The gains (0.05, 0.5, 0.30, 0.25) and the 0.2 lognormal spread on the target kind weights are assumptions set in `model.py`. Intervals are 90 percent.
- **The thermal conflict rule assumes a band whose name contains "thermal", where a high value means ice-consistent.** The data stage follows this convention (`thermal_simulated`, see `specs/05-data.md`).

## Known limitations

Data and science (the planner and dashboard limits are for Udit and Disha to add):

- **Only the elevation is real.** The spectral, ice, thermal and mineral bands, the noise, the gaps and the sensor conflict are simulated, so the science ranking says nothing about real ice or minerals.
- **Thermal inertia is simulated.** Real THEMIS thermal inertia (a 1.7 MB Jezero map, CC BY 4.0, and published Perseverance values of 180 to 605) has been checked as a source but is not integrated yet. It is the next priority.
- **The stated 90 percent confidence intervals are too narrow.** Measured against the simulated truth on 90 scenes, they hold the true value about 74 percent of the time and the true rank about 75 percent. They have not been calibrated yet, and the measurement is against our own simulation.
- **Terrain classes are not an independent check.** The Random Forest learns labels made by our own rules.
- **A small area, one rover, a static map.** Each run covers about 0.5 km square on a 256 by 256 grid at about 2 m, with no wheel slip or power model.
- **Two sites, five tiles, one seed each in the results table.** `docs/TILE_RESULTS.md` is a snapshot, not an average, and sites are never pooled.
- **Planted targets are not a detection test.** The science stage finds about 3 percent of them, so they are a diagnostic only.
- **Not built:** the synthetic elevation fallback and the flags for stereo artifacts in the elevation model.
- **Licence:** no licence is stated for the elevation models themselves. HiRISE images are public domain and credit is given.

## How this maps to the judging criteria

See `docs/EVALUATION_MAP.md`.

## Team

Udit Arun Nath, Disha, Saptarshi.

## Libraries and external resources

TODO: list every dataset, library and API used.

- PyTorch (`torch`, optional): only for the CNN terrain classifier experiment. The pipeline runs without it.
