# Spec 04: Dashboard

Status: approved
Owner: Disha
Reviewer: Udit
Serves criteria: usability, explainability, uncertainty

## Purpose

One screen that tells the whole story in the 8 minute demo.

## Requirements

1. 3D terrain view and a 2D cost map with the path overlaid (Streamlit with Plotly is the working choice).
2. Ranked science targets table with confidence bands.
3. Controls: noise level, missing data toggle, bold versus cautious mode, planner choice (A* or Dijkstra). A target picker switches among the precomputed candidate paths. The default is the top ranked target.
4. Click or select a target or path segment to see its trace: inputs, cost breakdown, evidence string.
5. Visible safety badge from the path safety check.
6. Simulated layers are labelled as simulated on screen.
7. Loads quickly. It reads one serialised `PipelineResult` and does not recompute on load.
8. Cut order if late: 3D view first (keep 2D), then Dijkstra view, B1 view.

## Acceptance checks

- [ ] Fresh launch loads in under 10 seconds
- [ ] Changing noise or mode updates the path and ranks live
- [ ] The three Track A showcase items are visible without scrolling
- [ ] Works with dummy data from hour one, then swapped to real outputs

## Uncertainty and failure handling

If a stage fails, show an error panel with the reason, not a blank page. Keep a recorded backup of the demo.

## Out of scope

Authentication, multi-user, mobile layout.

## Open questions

- Layout choices after the first mentor round.
