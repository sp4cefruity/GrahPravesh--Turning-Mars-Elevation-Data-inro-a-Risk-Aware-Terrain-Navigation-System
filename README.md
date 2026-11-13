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
3. **Planning** (Udit): cost map, A* with Dijkstra as a baseline, a hard safety rule, and a cautious mode that penalises uncertain cells.
4. **Science** (Saptarshi): rank candidate formations by value divided by cost, with confidence bands and a written evidence trail.
5. **Dashboard** (Disha): interactive view of all of the above.

## Architecture

See `docs/ARCHITECTURE.md`.

## Data and assumptions

- Real elevation data: TODO (Saptarshi, source and licence).
- Simulated: spectral bands, ice signal, sensor noise, missing data patches.
- Single tile, single rover, static map.

### Modelling assumptions

None of these numbers is fitted to rover data. Every one is a working assumption unless `docs/RESEARCH_NOTES.md` cites it.

- **Terrain classes are rule-derived pseudo-labels.** There is no labelled Mars terrain data in this project. Perception first labels each cell with hand-set rules on slope, roughness and crater rims (5 classes). A Random Forest is then trained on those labels. Its tree votes give the class probabilities and the epistemic spread. Because it learns the rules it was given, it agrees with them by construction. It is not an independent check on the rules.
- **Perception thresholds are assumptions.** This covers the slope centre (20 degrees), the roughness scale (0.25 m), the rim rule, the DEM noise (0.3 m) and the noise correlation length (20 m). They live in `src/odyssey/perception/params.py` and can be overridden through the `perception` field of `PipelineConfig`.
- **Science value is a documented score, not science.** All spectral bands are simulated, so nothing here is a claim about real ice or minerals. The formulas are in `src/odyssey/science/model.py`, all on a 0 to 1 scale:
  - Ice value is the simulated ice band, scaled from its 2nd percentile to its maximum over valid cells.
  - Geology value is distinctness times slope-free access. Distinctness is the mean of class rarity (from the terrain class probabilities) and the scaled mineral band, when present. Slope-free access is `1 - slope / hard_block_slope_deg`, clipped to 0 to 1.
  - Ranking divides value by the cautious path cost to the target.
- **Value uncertainty is built from four terms added in quadrature:** sensor noise, classifier disagreement, the share of missing data nearby, and an ice versus thermal conflict. The gains (0.05, 0.5, 0.30, 0.25) and the 0.2 lognormal spread on the target kind weights are assumptions set in `model.py`. Intervals are 90 percent.
- **The thermal conflict rule assumes a band whose name contains "thermal", where a high value means ice-consistent.** This follows `specs/05-data.md` and is unconfirmed until the data stage exists.

## Known limitations

TODO (all, by 8:45 AM). Be specific and honest.

## How this maps to the judging criteria

See `docs/EVALUATION_MAP.md`.

## Team

Udit Arun Nath, Disha, Saptarshi.

## Libraries and external resources

TODO: list every dataset, library and API used.
