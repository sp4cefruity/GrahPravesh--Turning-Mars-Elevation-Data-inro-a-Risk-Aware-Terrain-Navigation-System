# Evaluation Map

How each judging criterion shows up in the build and in the demo. Check this before every spec approval and before the final rehearsal.

| Criterion | What judges look for | Our feature | Where in the demo | Owner |
|---|---|---|---|---|
| Technical depth and sophistication | Rigor of algorithms and system design | Slope and roughness derivation, hybrid hazard classification, A* with Dijkstra baseline, Monte Carlo uncertainty propagation, clear module contracts | Architecture slide, planner comparison panel | U, D |
| Investigation and reasoning quality | Fragmented clues into a defensible story | Each science target has an evidence string combining spectral signal, slope access and path cost. Ranking explained as value divided by cost | Target detail panel | S, D |
| Uncertainty and robustness | Noisy, missing or conflicting data, confidence limits stated | Simulated noise, missing patches and conflicting sensor readings in the scene. Per-cell mean and standard deviation. Confidence bands on target ranks. Cautious mode | Toggle noise level, show path and ranks shift | S |
| Execution and explainability | Traceability to evidence, safe and verified execution | Click any cell or path segment to see its inputs and cost breakdown. Hard-block rule on steep slopes. Verification check that the final path never crosses a hard hazard | Click-through trace, path safety check | U, D |
| Innovation and usability | Original approach, clear interface, effective live demo | Uncertainty-aware planning with a cautious versus bold toggle. One-screen dashboard. Rehearsed 8 minute story plus backup video | Whole presentation | D, all |

## Track A showcase items (from the brief)

- [ ] Terrain or cost map
- [ ] Planned path with hazards avoided
- [ ] Ranked list of science targets with uncertainty shown

## Core deliverables checklist

- [ ] Working end-to-end prototype
- [ ] Source code in repo, built during the window
- [ ] README with approach, architecture, assumptions, known limitations
- [ ] Live demo ready for the 8 + 4 minute slot
- [ ] Backup demo recording
