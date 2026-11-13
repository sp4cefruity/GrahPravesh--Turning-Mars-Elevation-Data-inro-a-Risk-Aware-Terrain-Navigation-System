# Our Understanding and Approach (MARS-09, Odyssey)

Status: draft for team review. Companion to `CONTEXT.md`. Detail and sources are in `docs/HACKATHON_BUILD_PLAN.md` and `docs/MODEL_AND_BASELINE_PLAN.md`.

## 1. How we read the problem

MARS-09 lands in an unexplored, risky region of Mars. Radio delay is long and the onboard computer is small, so Earth cannot approve every move. The rover has to decide for itself, and it has to know when it is unsure.

The brief asks for three things, and we treat them as one chain, not three separate tasks:

1. A map of the ground that says how costly and how dangerous each patch is.
2. A route across that map that avoids hazards.
3. A ranked list of places worth visiting, with how confident we are in each rank.

The hard part is not finding a path. It is making every step honest about what it does not know. A rover that is confident and wrong is worse than one that is cautious and says why. We build around that idea.

## 2. The core idea: uncertainty travels end to end

Most route planners take a single cost map and treat it as true. Ours keeps the doubt attached from the first sensor reading to the final ranking.

- Perception gives each cell a hazard probability, not a yes or no.
- The cost map stores a mean cost and a spread for every cell.
- The planner can be told how much risk to accept, and the path changes with that setting.
- The science ranking gives each target a range of possible ranks, not one number.

Each judging criterion maps onto a piece of this chain. The full mapping is in `docs/EVALUATION_MAP.md`.

## 3. Salient features of the model

### Terrain and hazard intelligence
- Slope, roughness and step height are computed from a real Mars elevation tile.
- Terrain classes come from simple physical rules plus a Random Forest. The disagreement between its trees is our measure of model uncertainty.
- The elevation data is perturbed many times with spatially correlated noise. The spread of the resulting slopes tells us how much to trust the map at each cell.
- Hard safety rules (for example, very steep slopes are blocked) are kept separate from soft cost weights. A badly tuned weight can never produce a path across a hard hazard.

### Risk-aware path planning
- The cost map feeds an A* planner, checked against Dijkstra to confirm the route is optimal for the cost used.
- Edges are priced with a bad-case average (CVaR) instead of the plain average. One setting, alpha, moves the rover between bold (alpha 0) and cautious (alpha 0.95).
- The safety margin around blocked cells grows with distance driven, following Sanchez-Ibanez et al. (IROS 2022), because position estimates drift over time.
- The planner returns a corridor of near-equal paths, not one thin line, so the rover can tolerate drift and surprises between uplinks.
- A risk-versus-length curve shows exactly what extra distance buys how much extra safety.
- A verification step checks that the final path never crosses a hard hazard.

### Science discovery with uncertainty
- Candidate formations come from spectral and geological signals, including a possible water ice signal.
- Each target is scored on expected value minus the risk of reaching it.
- Sensor noise and weight choices are resampled many times, so each target gets a rank interval and a probability of landing in the top three.
- Every target carries an evidence string explaining why it ranks where it does.

### Baselines we compare against
- **B0:** slope threshold plus A*, with no uncertainty. This is the simple version most teams would build.
- **B1:** a reproduction of the cost used by Brad and Balog (Electronics 2025), included to show why a physical slope term matters.

Showing these side by side lets us measure what the uncertainty-aware design adds, instead of just claiming it.

### Optional side track
A small SegFormer model fine-tuned on a subset of the AI4Mars rover-camera dataset, shown as a separate rover-view panel with calibration. It is time-boxed and dropped at the 4:00 AM break if it is not working. It does not feed the main pipeline.

## 4. Why these choices

- **Free, proven parts.** Python, rasterio, NumPy, scikit-learn, numba, Streamlit and Plotly. Nothing needs a GPU in the main path, which suits three laptops and a 12 hour window.
- **Explainable over fancy.** Rules and a Random Forest can be traced cell by cell. This supports the explainability criterion and keeps the demo safe.
- **Grounded in the literature.** The risk-aware cost follows the structure used by Endo et al. (ICRA 2023) for combining terrain classes with CVaR. The distance-growing margin comes from the IROS 2022 paper. Both are described, with their limits, in `docs/MODEL_AND_BASELINE_PLAN.md`.

## 5. The demo story in one line

Show the map and its doubt, show a naive path cross hazards, show our path avoid them, drag the risk dial and watch the route and the ranks move, then click any result to see the evidence behind it.

## 6. Limits we state openly

- One elevation tile, one rover, a static map. No wheel slip or power model.
- Spectral, ice and noise layers are **simulated**, not real CRISM data. They are labelled that way everywhere.
- Slope limits, cost weights and class multipliers are **assumptions** and are **unverified** against real rover data. Working values are a hard block at 25 degrees and a soft scale of 15 degrees, to be decided and cited later.
- The CVaR cost is computed edge by edge from a Gaussian assumption. It is cautious, but it is not a formal safety guarantee.
- No public labelled orbital terrain dataset was found, so orbital terrain classes come from rules and rule-derived labels, not human ground truth.
- Results show that our method beats the baselines on our simulated scene. They are not claims about real rover safety on Mars.
