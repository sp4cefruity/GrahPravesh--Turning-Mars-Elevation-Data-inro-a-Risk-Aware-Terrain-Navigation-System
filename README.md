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

## Known limitations

TODO (all, by 8:45 AM). Be specific and honest.

## How this maps to the judging criteria

See `docs/EVALUATION_MAP.md`.

## Team

Udit Arun Nath, Disha, Saptarshi.

## Libraries and external resources

TODO: list every dataset, library and API used.
