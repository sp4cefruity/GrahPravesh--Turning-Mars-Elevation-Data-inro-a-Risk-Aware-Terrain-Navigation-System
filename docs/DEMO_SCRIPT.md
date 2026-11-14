# Demo Script (8 minutes present, 4 minutes Q&A)

Status: final for the build at commit `2a03c63`, 2026-11-14. Every number below was measured on this build. One item is still open: the backup recording has not been made (see the pre-flight list). Rehearse once with a timer.

## Before you go on

Do this once so nothing is cold:

1. `python -m odyssey.pipeline` saves the default result.
2. `streamlit run src/odyssey/dashboard/app.py`, then open the page once and leave it open. The first load took 10.9 s on a cold server and later loads took about 4 s.
3. Open `web/index.html` in a second tab (the rover sandbox) and `docs/presentation-architecture.png` in a third.

The demo scene is fixed: tile T1 (Jezero crater), scene seed 0, sensor noise 1.0, rover start at cell (8, 8).

## Run of show

| Time | Who | What |
|---|---|---|
| 0:00 to 0:45 | Udit | The story. MARS-09 lands somewhere risky, radio delay is long, it must decide alone. Three questions: where is it safe, how do we get there, what is worth seeing and how sure are we. |
| 0:45 to 2:00 | Udit | The architecture slide (`docs/presentation-architecture.png`). Real elevation and simulated sensors go through data, perception, uncertainty and the cost map to the planner and science, then a safety check, a saved result and the dashboard. Mention the typed contracts and the hard safety rule. |
| 2:00 to 3:15 | Saptarshi, Disha | Data and perception. Saptarshi: point at the line at the top of the dashboard, "HiRISE DTM ... T1: real elevation, 2 m block mean plus simulated noise". Only the elevation is real, every sensor layer is simulated and labelled SIMULATED, and a hidden answer key is kept for testing. Disha: slope, roughness, the Random Forest terrain classes, the hazard chance and the hard block over 25 degrees. |
| 3:15 to 5:15 | Disha | Live dashboard on the default scene. Cost map, then the route to the top target T4: 102 cells, peak slope 7.4 degrees, safety check PASS. The route's hazard exposure is 2.13, against 2.93 for the slope-only baseline B0 and 4.99 for B1. Ranked table: T4 geology (P(top 3) 0.80), T2 ice (0.92), T3 ice (0.69), T5 geology (0.54), T1 ice (0.05). T6 and T7 show a red X because they have no safe route. Click T4 to read its evidence string. |
| 5:15 to 6:45 | Disha drives, Saptarshi narrates uncertainty, Udit explains the planner | The moment that sells it. See "The uncertainty moment" below. |
| 6:45 to 7:30 | Saptarshi | Honest limits. Only the elevation is real. The stated 90 percent intervals held the truth about 74 percent of the time. The Random Forest learns our own rules. One small area, one rover, no wheel slip. Real thermal inertia data is checked as a source and is the next step. |
| 7:30 to 8:00 | Udit | Close. Map back to the judging criteria in one sentence each. |

### The uncertainty moment (5:15 to 6:45)

Do these in order on the dashboard, then finish in the sandbox.

1. **Raise the sensor noise from 1.0 to 2.0.** The top target changes from T4 to T2. T2's chance of the top 3 goes from 0.92 to 1.00, T5's falls from 0.54 to 0.07, and T1's rises from 0.05 to 0.27.
2. **Set noise back to 1.0 and tick "Missing data patch (SIMULATED)".** The top target again changes from T4 to T2, because T4's route cost rises from 141.5 to 208.9. The safety check still passes.
3. **Say this about the bold and cautious dial, plainly.** In the Python pipeline the two routes to a target are almost the same length. The cost to T4 rises from 137.1 to 141.5 (about 3 percent), and the risk versus length chart is flat. Do not promise a visibly longer route here.
4. **Switch to the sandbox tab to show the dial.** Say it is a simplified browser version of the planner on a simulated surface. Drop a crater on the route and watch it replan. On the starting scene, bold gives 1341 m with hazard exposure 3.21, and cautious gives 1383 m with 2.54. Press Drive to run the rover along the route.

## If something breaks

- Dashboard will not load: use the sandbox tab (`web/index.html`) and the architecture slide, and walk through the numbers above from this page.
- The default result is saved as `outputs/result_<hash>.pkl`, so the dashboard loads it without recomputing.
- The backup recording is not made yet. Record it before presenting if there is time.

## Key numbers (default scene)

| What | Value |
|---|---|
| Scene | T1 Jezero, seed 0, noise 1.0, start (8, 8) |
| Targets found, reachable | 7 found, 5 reachable. T6 and T7 have no safe route. |
| Route to T4 | 102 cells, peak slope 7.4 degrees, safety check PASS |
| Hazard exposure, T4 route | 2.13 (ours), 2.93 (B0), 4.99 (B1) |
| Top target at noise 1.0 | T4, score 0.0052, rank interval 1 to 5, P(top 3) 0.80 |
| Top target at noise 2.0, or with the missing patch | T2 |
| Interval coverage, measured on 90 simulated scenes | value 74 percent, rank 75 percent, against the 90 percent stated |

## Q&A prep (4 minutes)

**The system**
- Why A* and not RRT? A grid cost map suits A*, it gives optimal paths, and it is easy to explain and verify. Every route is cross-checked with Dijkstra.
- Does the dial change the route? Barely in the Python pipeline: about 3 percent more cost, the same length. It shows clearly in the browser sandbox. We would rather say that than overclaim.
- Why does the rover not take the straight line? The planner minimises cost, not distance. Slope, roughness, soft ground and hazard chance all add cost. In the sandbox the straight line crosses 6 blocked cells, and the planned route is 16 percent longer with far less hazard exposure.
- Why is there no safe route to some targets? That is correct behaviour. On the steep scarp tile T4, most targets are unreachable and the system says so instead of drawing a risky path.
- Can the planner get stuck going back and forth? No. Snapping a goal to a safer cell happens once, and a replan counter and revisit limit stop any loop with a "no safe path" answer.
- How would this run on a real rover? A smaller grid, local replanning and onboard compute limits. It is pre-mission planning from orbital data, and we did not test it on a rover.
- Is the sandbox the real system? No. It is a simplified browser planner on a simulated surface. The full pipeline runs in Python on real HiRISE tiles.

**The data**
- What is real and what is simulated? Only the elevation is real: NASA HiRISE elevation models of Jezero crater and Promethei Terra. The sensor layers, noise, gaps and one sensor conflict are simulated and labelled.
- Why simulate the sensors? We had no real multispectral data in scope, and a simulated scene gives a known truth to test against.
- What do 1 m and 2 m mean? The map has one height per square metre. We average 2 by 2 blocks to 2 m cells to cut the noise, and keep the original as an answer key.
- What noise do you expect? Small, smooth height error of tens of centimetres, which we model (0.3 m, an assumption). Stereo processing flaws such as seams and offsets are real too, and we do not model them yet. Missing cells are marked blocked and never filled.
- What are the tiles? Five 512 m squares from two sites. T1 is the demo and the tuning tile. T2 to T5 are held out, and T4 is a scarp where the correct answer is often no safe route.
- Licence and credit? Credit NASA/JPL/University of Arizona. HiRISE images are public domain, and no licence is stated for the elevation models themselves.

**The models**
- Why a Random Forest? There is no real terrain label data to learn from. It runs on a laptop in seconds, and the disagreement between its trees gives uncertainty for free. It learns our own rules, so it is not an independent check.
- What did the CNN add? Nothing yet. We built a small CNN and measured it against the Random Forest on held-out tiles: macro F1 0.13 against 0.79. The forest stays the default. Both learn from rule-derived pseudo-labels, so neither is a claim about real terrain.
- How do you know the uncertainty is meaningful? Monte Carlo over elevation noise gives a slope spread for every cell, and a 1000 run ranking gives each target a rank interval. We also measured it: on 90 simulated scenes the stated 90 percent intervals held the truth about 74 percent of the time. They are too narrow, and we say so.
- Why Monte Carlo? Slope comes from height differences and ranking comes from sorting, and neither has a simple formula for how errors flow through. We shake the inputs many times and use the spread.
- What happens if the sensor data is missing or conflicting? Missing cells are marked invalid and blocked, and the planner routes around them. A conflict between two sensors widens that target's interval, and its evidence string says so.
- What about real thermal inertia? We checked real sources (a THEMIS map of Jezero and published Perseverance values) and recorded them. The thermal layer is still simulated, and integrating the real one is the next step.

## Pre-flight checklist

- [x] Everything is pushed, and the full test suite passes on the pinned versions (187 passed, Python 3.11)
- [ ] Fresh clone runs with the README steps. Checked here from a clean copy and a pinned install. Run it once on the demo laptop.
- [x] Dashboard loads in under 10 seconds once warm (about 4 s). The first cold load took 10.9 s, so open it before you go on.
- [x] Demo scene and seeds fixed: T1, seed 0, noise 1.0, start (8, 8)
- [ ] Backup video recorded and opens. Not done.
- [x] Offline copy of data: the five tile crops are in `data/tiles/`
- [ ] Laptop charged, projector adapter
- [ ] Everyone knows their segment and timing
