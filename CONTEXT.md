# Context: MARS-09 Odyssey (Track A)

Hackathon: HackInnovision 2026, November 14, 2026, 12:00 AM to 12:00 PM (12 hours).
Track: A, Planetary Reconnaissance and Autonomous Navigation (Odyssey).
Team: Udit (architecture, planner, integration), Disha (research, perception, data), Saptarshi (uncertainty, science ranking, dashboard).

## The problem in one paragraph

A rover, MARS-09, lands in an unexplored, risky region of Mars. Radio delay is long and onboard compute is small, so it cannot ask Earth for every move. From imagery, a Digital Elevation Model (DEM), slope data and science goals, it must build a map of its surroundings, pick a safe route, and choose which geological features are worth visiting. It must also say how sure it is.

## Key technical objectives (from the brief)

1. **Perception and terrain intelligence.** Classify terrain, flag hazards, build 3D elevation maps from multispectral images and elevation data.
2. **Path planning and cost mapping.** Use A*, Dijkstra or RRT to find traversable corridors, compute movement costs, avoid hazards.
3. **Scientific discovery and uncertainty.** Rank candidate formations, flag possible resources such as subsurface water ice, and quantify uncertainty in sensors and model predictions.

## What judges score

| Criterion | Our short answer |
|---|---|
| Technical depth | Hybrid rule and ML perception, A* with Dijkstra baseline, Monte Carlo uncertainty |
| Investigation and reasoning | Each science target comes with a written chain of evidence |
| Uncertainty and robustness | Noisy, missing and conflicting data in the demo scene, confidence bands everywhere |
| Execution and explainability | Every cell, path segment and rank traces back to inputs |
| Innovation and usability | Interactive dashboard, cautious versus bold rover toggle |

Full mapping: `docs/EVALUATION_MAP.md`.

## Decisions made so far

- Real DEM tile (for example Jezero crater, public USGS or NASA data) cropped to about 512 by 512. Spectral bands, ice signal and sensor noise are simulated and labelled as such.
- Interactive dashboard (Streamlit with Plotly is the working choice).
- Perception: rule-based hazards first. A CNN for terrain classes is an experiment. We try it early and keep it only if it works and stays explainable. Fallback is Random Forest.
- Planner: A* main, Dijkstra as baseline. RRT not planned.
- Uncertainty: Monte Carlo (about 50 to 100 samples) over DEM and sensor noise.
- Science ranking: expected value divided by traversal cost, with a confidence band.
- Overall flow is not locked. Disha is researching and will add gaps and ideas to `docs/RESEARCH_NOTES.md`. Specs stay in `draft` until that lands.

## Glossary

- **DEM**: Digital Elevation Model. A grid of heights.
- **Slope**: steepness per cell, in degrees, derived from the DEM.
- **Roughness**: local height variation, a proxy for rocks and broken ground.
- **Hazard map**: per-cell flag or probability for dangerous ground (steep, rough, crater rim, loose sand).
- **Cost map**: per-cell price of driving through. Higher means riskier or more costly.
- **Traversable corridor**: connected set of cells the rover may drive through.
- **Science target**: a candidate formation worth visiting, with a value score and a confidence band.
- **Ice signal**: simulated spectral and thermal hint of subsurface water ice.
- **Uncertainty**: spread of a result across Monte Carlo runs, shown as mean and standard deviation or interval.
- **Cautious mode**: planner variant that penalises uncertain cells more heavily.
- **Evidence string**: short human-readable reason attached to a result.

## Deliverables

Core: working prototype, source code (built in the window), README write-up, live demo within the 8 + 4 minute slot.
Track A extras: a terrain or cost map, a planned path with hazards avoided, a ranked list of science targets with uncertainty shown.

## Key dates

Final deliverables ready by 9:15 AM. Submission window 9:30 to 10:00 AM. Top 10 presentations 10:00 AM to 12:00 PM. Schedule detail in `docs/TIMELINE.md`.
