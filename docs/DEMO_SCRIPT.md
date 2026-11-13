# Demo Script (8 minutes present, 4 minutes Q&A)

Draft. Fill in real numbers after the 9:00 AM rehearsal. Rehearse with a timer. Keep a recorded backup in case the live demo fails.

## Run of show

| Time | Who | What |
|---|---|---|
| 0:00 to 0:45 | Udit | The story. MARS-09 lands somewhere risky, radio delay is long, it must decide alone. Three questions: where is it safe, how do we get there, what is worth seeing and how sure are we. |
| 0:45 to 2:00 | Udit | Architecture on one slide. Perception, uncertainty, planning, science, dashboard. Mention the contracts and the hard safety rule. |
| 2:00 to 3:15 | Saptarshi, Disha | Data and perception. Saptarshi: real DEM tile, what is simulated and why. Disha: slope, roughness, hazard map and how thresholds were chosen. |
| 3:15 to 5:15 | Disha | Live dashboard. Cost map, planned path avoiding hazards, ranked science targets with confidence bands. Click a target to show its evidence string. |
| 5:15 to 6:45 | Disha drives, Saptarshi narrates uncertainty, Udit explains the planner | The moment that sells it. Raise the sensor noise and add missing data. The path and ranks shift. Switch to cautious mode and show the safer, longer route. Show the path safety check passing. |
| 6:45 to 7:30 | Saptarshi | Honest limits. Simulated bands, single tile, no wheel slip. What we would do next. |
| 7:30 to 8:00 | Udit | Close. Map back to the judging criteria in one sentence each. |

## Q&A prep (4 minutes)

Likely questions and short answers to fill in:

- Why A* and not RRT? Grid cost map suits A*, gives optimal paths, easy to explain and verify.
- How do you know the uncertainty is meaningful? Monte Carlo over DEM and sensor noise, spread shown per cell. Say what noise model we used.
- What is real and what is simulated? Real DEM. Simulated spectral bands, ice signal, noise.
- What did the CNN add (if kept)? Fill in after the 4:00 AM decision.
- What happens if the sensor data is missing? Cells are marked invalid and given a high cost, the planner routes around them.
- How would this run on a real rover? Smaller grid, local replanning, onboard compute limits, honest answer on what we did not test.

## Pre-flight checklist (9:00 AM)

- [ ] Fresh clone runs with the README steps
- [ ] Dashboard loads in under 10 seconds
- [ ] Demo scene and seeds fixed
- [ ] Backup video recorded and opens
- [ ] Laptop charged, projector adapter, offline copy of data
- [ ] Everyone knows their segment and timing
