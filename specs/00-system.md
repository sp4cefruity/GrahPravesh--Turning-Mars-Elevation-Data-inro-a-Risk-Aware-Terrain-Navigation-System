# Spec 00: System

Status: approved
Owner: Udit
Reviewer: Saptarshi
Serves criteria: all

## Purpose

One command runs the full pipeline on the demo scene and the dashboard shows the result: a cost map, a safe path, and ranked science targets with uncertainty.

## Inputs and outputs

In: one config file (seeds, weights, thresholds, noise level). Out: one serialised `PipelineResult` (see `docs/ARCHITECTURE.md`).

## Requirements

1. `pipeline.py` runs the stages in this fixed order and returns a `PipelineResult`:
   1. data (Saptarshi)
   2. perception, including `hard_block` (Disha)
   3. uncertainty, the DEM Monte Carlo that fills `slope_std_deg` (Disha)
   4. cost map (Udit)
   5. science candidates, value only, no path cost yet (Saptarshi)
   6. planning, one path per candidate in bold and cautious mode (Udit)
   7. science ranking, using path CVaR as access cost (Saptarshi)
   8. planning extras (Udit): baselines B0 and B1 and the risk-versus-length curve, for the default goal. This runs last because the default goal is the top ranked target, which is only known after step 7.
2. The default displayed path goes to the top ranked target. The dashboard can show any precomputed candidate path.
3. The start cell is `config.start`, default (8, 8). Every path and every baseline starts there. The run fails at the data stage if it lies outside the grid, and at the cost map stage if it is blocked.
4. Runs are reproducible from a config with fixed seeds.
5. The demo scene includes noise, missing patches and at least one conflicting sensor reading.
6. A path safety check confirms the final path never crosses a blocked cell.
7. The result is serialised once per config so the dashboard loads it without recomputing.
8. Until a stage lands, `pipeline.py` uses a stub that returns dummy output in the contract shape, so the pipeline always runs end to end.
9. The repo runs from a clean checkout using the README steps.

## Acceptance checks

- [ ] Two runs with the same seed give identical output
- [ ] Safety check fails loudly if a path crosses a blocked cell (tested with a forced bad path)
- [ ] Pipeline runs end to end with all stubs, before any real stage exists
- [ ] Clean-clone run works on a second laptop
- [ ] All three Track A showcase items appear in the dashboard

## Uncertainty and failure handling

If a stage raises, the pipeline records the stage name and reason in the result and stops. The dashboard shows that reason. It never shows partial output as if it were complete.

## Out of scope

Wheel slip, power budget, multi-rover, real-time sensor streaming.

## Open questions

- None blocking. Re-check this spec if `docs/RESEARCH_NOTES.md` changes a requirement.
