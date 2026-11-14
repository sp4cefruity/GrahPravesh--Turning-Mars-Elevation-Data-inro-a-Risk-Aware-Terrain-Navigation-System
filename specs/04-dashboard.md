# Spec 04: Dashboard

Status: draft (revised 2026-11-14: frontend changed to HTML and JS at Disha's request, Udit to re-approve)
Owner: Disha
Reviewer: Udit
Serves criteria: usability, explainability, uncertainty

## Purpose

One screen that tells the whole story in the 8 minute demo.

## Requirements

1. 3D terrain view and a 2D cost map with the path overlaid. Built as a static HTML, CSS and JavaScript page (Plotly.js vendored locally so it works offline). No Streamlit, no build step.
2. Ranked science targets table with confidence bands.
3. Controls: noise level, missing data toggle, bold versus cautious mode, planner choice (A* or Dijkstra). A target picker switches among the precomputed candidate paths. The default is the top ranked target.
4. Click or select a target or path segment to see its trace: inputs, cost breakdown, evidence string.
5. Visible safety badge from the path safety check.
6. Simulated layers are labelled as simulated on screen.
7. Loads quickly. It reads precomputed JSON bundles exported by the pipeline (see "Dashboard data export" in `docs/ARCHITECTURE.md`) and never recomputes. The noise and missing data controls switch between saved scenarios, so the pipeline must be run for each scenario before the demo.
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
- Serving: `python -m http.server` from `outputs/web/`, or inline the bundle in the page. Disha and Udit to pick.
- Scenario grid: which noise levels to precompute (suggest 0, 1, 2) and whether missing data on or off is a second axis.
- The Streamlit code in `src/odyssey/dashboard/` and `tests/test_dashboard.py` stays until the HTML page matches it, then gets removed along with streamlit, plotly and pandas in `requirements.txt`.
