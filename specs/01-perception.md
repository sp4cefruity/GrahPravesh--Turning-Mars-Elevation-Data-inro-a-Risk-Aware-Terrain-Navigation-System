# Spec 01: Perception and DEM Monte Carlo

Status: approved
Owner: Disha
Reviewer: Udit
Serves criteria: technical depth, uncertainty, explainability

## Purpose

Turn the raw scene from `specs/05-data.md` into slope, roughness, terrain classes, a hazard map with hard blocks, and a per-cell slope uncertainty from a DEM Monte Carlo.

## Inputs and outputs

In: raw `TerrainGrid` from the data module (DEM, simulated bands, valid mask).
Out: full `TerrainGrid` and a complete `HazardMap`, including `hard_block` and `slope_std_deg` (see `docs/ARCHITECTURE.md`).

## Requirements

1. Derive slope, roughness, step height and aspect from the DEM with our own numpy Horn kernel (no GPL dependency).
2. Rule-based hazards first: steep slope, high roughness, crater rim. Thresholds come from cited sources in `docs/RESEARCH_NOTES.md`. Until cited, use the working values in `docs/ARCHITECTURE.md` (hard block at 25 degrees) and label them assumptions.
3. Terrain classes: Random Forest. Tree votes give `class_probs` and `epistemic_std`. Combine into `hazard_prob = 1 - (1 - P_slope)(1 - P_rough)(1 - P_class)`. Labels come from the rules (pseudo-labels), and the README says so.
4. `hard_block` (bool) is `slope > limit` OR crater rim OR `hazard_prob > delta`. `limit` and `delta` are config values. `delta` is an assumption until tuned. Invalid cells are not handled here, the planner adds `~valid_mask`.
5. Every hazard cell carries an evidence note (which rule or model fired).
6. DEM Monte Carlo (module `src/odyssey/uncertainty/`): 50 to 100 draws, spatially correlated noise (Gaussian-filtered white noise), seeded, calling the slope kernel. Store only mean and std. Fill `slope_std_deg`. Document the noise model in `docs/RESEARCH_NOTES.md`.
7. Noise level is one config value that the dashboard can change.
8. Side track (optional, dropped at 4:00 AM if not working): write the SegFormer-B0 fine-tune script for the AI4Mars subset. It runs on Saptarshi's GPU. A CNN on the DEM is an experiment, see "CNN experiment" below.

## CNN experiment

Status: approved by Udit and Disha. Built and measured, outcome below. Udit asked for this experiment. It sits in Disha's lane. Time box about 45 minutes. It is the first item on the cut list in `docs/TIMELINE.md`, so dropping it is a valid outcome.

Goal: try a small CNN as an alternative to the Random Forest in requirement 3. Keep it only if it works and stays explainable. The Random Forest remains the default and the fallback.

Inputs: 32 by 32 patches cut from the 256 by 256 grid. Channels are DEM (minus patch mean), slope, roughness, and the bands b1 to b5. Simulated bands (ice, thermal, mineral) stay out of the first version, so the net only sees what the Random Forest sees plus the raw relief. Invalid cells are masked to zero and the patch gets a validity channel.

Net: 2 or 3 conv layers with dropout, then a per-pixel head for the 5 classes. Trained on the same rule pseudo-labels as the forest. The README already says the labels are rule-derived, and this section does not change that.

Outputs: `class_probs` (K, H, W) and `epistemic_std` (H, W), so `HazardMap` and the contracts in `src/odyssey/contracts.py` do not change. `epistemic_std` is the spread of the hazard class probability (classes 3 and 4) over a 3-seed ensemble (seeds `Seeds.perception` plus 0, 1, 2). MC dropout is the fallback if the ensemble is too slow. Everything after `class_probs` (hazard combination, `hard_block`, evidence codes) is shared with the forest path and does not change.

Config: `PerceptionParams.classifier`, values `"forest"` (default) or `"cnn"`. If torch is missing or training fails, fall back to the forest and say so in the evidence legend. Torch goes in an optional requirements group, not in core.

Evaluation: train on tiles T1 to T3, hold out T4 and T5. Compare the CNN and the forest on the held-out tiles against the rule labels. Accuracy against rule labels measures how well each model imitates the rules. It is not accuracy against real terrain, and the write-up says so.

Keep rule. Keep the CNN only if all of these hold:

1. Held-out macro F1 against rule labels is at least the forest's.
2. Calibration (expected calibration error on the hazard probability) is no worse than the forest's.
3. `epistemic_std` is higher on held-out cells the model gets wrong than on cells it gets right.
4. Evidence codes still work: every `hard_block` cell carries a legend code, and the existing hard block rules (slope limit, crater rim) still fire the same way.
5. The full pipeline run time does not grow enough to hurt the live demo (measured, not guessed).

If any check fails, drop it, keep the forest, and record the measured numbers here. No number from this experiment is reported until it is measured.

Result (measured, `python -m odyssey.perception.cnn_eval`, full table in `outputs/cnn_eval.md`): the CNN fails keep checks 1 and 2, so it stays an optional experiment and the Random Forest stays the default. Train T1 to T3, held out T4 and T5, scored against rule labels, simulated noise and bands, untuned CNN (3 members, 60 steps), loss weighted by square-root inverse class frequency.

| T4 and T5 | Random Forest | CNN |
|---|---|---|
| accuracy | 0.985 | 0.333 |
| macro F1 | 0.793 | 0.130 |
| ECE, hazard classes | 0.010 | 0.127 |
| mean std on wrong cells vs right cells | 0.298 vs 0.031 | 0.020 vs 0.006 |

Check 3 (std higher on wrong cells) and check 4 (evidence codes) pass. Check 5: `compute_hazards` on T1 took 1.32 s for the forest and 1.37 s for the CNN. The held-out train and predict run took 1.65 s and 6.58 s. Without loss weights the CNN macro F1 was 0.103, so weights helped a little but did not fix it. The training tiles hold almost no steep cells (T3 about 1 percent, T4 about 22 percent), and the forest sees the exact rule inputs (slope, roughness, step height, convexity), so scoring against rule labels favours it. These numbers say how well each model imitates the rules, not how well either knows real terrain. Not tried: more steps, step and convexity channels, rare-class patch sampling.

Tests: classifier flag defaults to forest, `"cnn"` returns the same shapes and a valid probability simplex, the same seed gives the same output, and a missing torch falls back cleanly.

## Acceptance checks

- [ ] Slope map visually matches the DEM relief
- [ ] Missing patches show up as `valid_mask = False`, not as zeros
- [ ] `slope_std_deg` is larger at higher noise (two noise levels checked)
- [ ] Same seed gives the same `slope_std_deg`
- [ ] A forced steep patch is marked `hard_block = True`
- [ ] Hazard map for the demo scene is reviewed by a teammate

## Uncertainty and failure handling

Missing cells are flagged, never silently filled. Noise level is configurable so the demo can raise it.

## Out of scope

Real multispectral products, atmospheric correction, a CNN trained on imagery of the orbital tile (the DEM-derived experiment above is separate).

## Open questions

- Tile choice is owned by Saptarshi in `specs/05-data.md`. Disha confirms it as soon as it is picked.
- Cited slope and roughness thresholds, pending research notes.
- DECIDED (dev): option (b). `HazardMap.evidence_code` is an (H, W) int array and `evidence` is the legend `dict[int, str]` from code to note. Every code in the array must have a legend entry (the pipeline checks this). Disha to confirm.
- Implemented (not yet reviewed by a teammate): `compute_hazards` in `src/odyssey/perception/` and `fill_slope_uncertainty` in `src/odyssey/uncertainty/`. Evidence legend decision (option b) is implemented as written.
- Request to Udit (config and pipeline owner): add `perception: PerceptionParams` to `PipelineConfig` (class in `odyssey.perception.params`) so the sweep can change thresholds. Until then the code reads `getattr(config, "perception", None)` and uses defaults.
- Request to Udit: add `scikit-learn` and `pytest` to `requirements.txt`. Perception imports `sklearn`.
- Request to Udit: the README should say terrain classes use rule-derived pseudo-labels (spec requirement 3).
- Derived layers (`slope_deg`, `roughness`, `aspect`) and `slope_std_deg` are NaN where `valid_mask` is False. `hazard_prob` is 1.0 there, `hard_block` is False, `terrain_class` is -1. Planning already uses `nan_to_num`. Tell Udit and Saptarshi if that is a problem.
