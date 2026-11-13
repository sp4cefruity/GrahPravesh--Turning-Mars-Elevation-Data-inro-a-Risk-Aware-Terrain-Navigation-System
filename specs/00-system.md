# Spec 00: System

Status: draft
Owner: Udit
Reviewer: Saptarshi
Serves criteria: all

## Purpose

One command runs the full pipeline on the demo scene and the dashboard shows the result: a cost map, a safe path, and ranked science targets with uncertainty.

## Requirements

1. `pipeline.py` runs data, perception, uncertainty, planning and science in order and returns a `PipelineResult`.
2. Runs are reproducible from a config with fixed seeds.
3. The demo scene includes noise, missing patches and at least one conflicting sensor reading.
4. A path safety check confirms the final path never crosses a hard-blocked cell.
5. The repo runs from a clean checkout using the README steps.

## Acceptance checks

- [ ] Two runs with the same seed give identical output
- [ ] Safety check fails loudly if a path crosses a blocked cell (tested with a forced bad path)
- [ ] Clean-clone run works on a second laptop
- [ ] All five items in the Track A showcase list appear in the dashboard

## Out of scope

Wheel slip, power budget, multi-rover, real-time sensor streaming.

## Open questions

- Flow may change after Disha's research. Re-check this spec when `docs/RESEARCH_NOTES.md` gets entries.
