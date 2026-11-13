# Research Notes (owner: Disha)

Disha adds ideas, gaps and findings here. Agents read this before touching a spec. Anything that changes the flow gets a dated entry and a note on which spec it affects.

## How to add an entry

```
### <short title> (time, author)
What we learned:
Why it matters for the build:
Specs affected:
Status: proposed | accepted | rejected
```

## Open research questions

- Which public DEM tile to use (Jezero or another) and where to download it quickly.
- How to simulate multispectral bands and an ice signal in a way that is defensible.
- Whether a CNN is worth it for terrain classes within our time, or if Random Forest is enough.
- What slope and roughness thresholds are used in real rover practice, so our hazard rules are cited, not guessed.
- Sensible cost function weights, and how to justify them.

## Entries

### Model and baseline plan from papers and literature (2026-11-14, Disha via Claude research agent)
What we learned: Full survey and design plan in `docs/MODEL_AND_BASELINE_PLAN.md`. Covers the two reference papers, datasets (AI4Mars, HiRISE DTM), baseline (slope-threshold cost, A*/Dijkstra, weighted science score) versus proposed model (ensemble segmentation, mean-plus-variance cost, CVaR or chance-budget planning, Monte Carlo science ranking with rank intervals), metrics, ablations. No verified public orbital terrain labels were found, so a small hand-labelled classifier is the main risk. Rover slope limits and AI4Mars class codes are unverified.
Why it matters for the build: Gives cited candidates for hazard thresholds, cost weights and the uncertainty approach. Its 5-week timeline does not fit the hackathon; use `docs/TIMELINE.md`.
Specs affected: 01-perception, 02-planning, 03-uncertainty-science (not yet reconciled).
Status: proposed
