# Timeline (Nov 14, 2026)

Internal deadline: **all deliverables ready by 9:15 AM**. The 9:15 to 9:30 slot is buffer. 9:30 to 10:00 is the official submission window.

Owners: U = Udit, D = Disha, S = Saptarshi.

| Time | Official block | Our plan | Owner |
|---|---|---|---|
| 12:00 to 1:00 | Session 1 (briefing, rules, criteria) | Read the judging criteria together. Set up repo. D starts research and downloads the DEM tile. U drafts `specs/00-system.md` and contracts. S sets up the dashboard shell with dummy data. | all |
| 1:00 to 2:30 | Session 1 | Specs 01 to 04 drafted. Data loader and synthetic layer (simulated spectral bands, noise, missing patches) working. Contracts frozen at 2:15 so people can build in parallel. Specs move to `approved`. | all |
| 2:30 to 4:00 | Mentor Round 1 | Use mentors to pressure-test the approach, uncertainty method and demo story. Start implementing against the contracts. D: slope, roughness, hazard rules, CNN trial. U: cost map and A*. S: Monte Carlo and target scoring. | all |
| 4:00 to 4:30 | Break | Eat. Ten minute sync: what works, what is blocked. Decide CNN keep or drop. | all |
| 4:30 to 6:00 | Session 2 | Each module works on real data. D: terrain classes and hazard map delivered. U: A* and Dijkstra on the real cost map. S: uncertainty maps and ranked targets. | all |
| 6:00 | Checkpoint | First end-to-end run through `pipeline.py`, even if rough. Anything not integrated by now is cut or simplified. | U |
| 6:00 to 7:30 | Session 2 | Wire the dashboard to real outputs. Cautious versus bold toggle. Evidence strings on every target. Failure cases in the scene (noisy, missing, conflicting data). | S, U |
| 7:30 | **Feature freeze** | Only fixes and polish after this point. | all |
| 7:30 to 8:30 | Mentor Round 2 | Demo to mentors, collect feedback, fix the top three issues only. Draft README. | all |
| 8:30 to 9:15 | Final sprint | 8:30 to 8:45 bug fixes. 8:45 README and limitations final, run from a clean checkout. 9:00 full demo rehearsal with a timer. 9:10 final commit (after dev green light), screenshots and backup demo video saved. | all |
| 9:15 | **Deliverables ready** | Repo link, README, working demo, backup recording. | all |
| 9:15 to 9:30 | Buffer | Fix submission issues only. | U |
| 9:30 to 10:00 | Submission and shortlisting | Submit before 10:00. Do not wait. Rest, hydrate, prep Q&A. | U |
| 10:00 to 12:00 | Top 10 presentations | 8 minutes present, 4 minutes Q&A. See `docs/DEMO_SCRIPT.md`. | all |

## Cut list if we run late (drop in this order)

1. CNN for terrain classes (stay on rules plus Random Forest).
2. Dijkstra comparison view.
3. 3D rotation polish in the dashboard (keep 2D maps).
4. Extra science target categories (keep ice and geological interest).

Never cut: cost map, planned path with hazards avoided, ranked targets with uncertainty, README with limitations, backup demo video.

## Rest

Twelve hours overnight is tough. Take a rotating 20 minute break during Session 2 so someone is always fresh for integration.
