# Roles and Ownership

Three humans, each with one or more AI agents working under them. An agent works for the human who owns its role. Agent definitions are in `.claude/agents/`.

| Human | Role | Owns (folders) | Agent file |
|---|---|---|---|
| Disha | Research, Perception, DEM Monte Carlo, Dashboard | `src/odyssey/perception/`, `src/odyssey/uncertainty/`, `src/odyssey/dashboard/`, `docs/RESEARCH_NOTES.md`, `specs/01-perception.md`, `specs/04-dashboard.md` | `perception.md`, `dashboard.md` |
| Udit | Architecture, Planning, Integration | `src/odyssey/planning/`, `src/odyssey/pipeline.py`, `docs/ARCHITECTURE.md`, `specs/02-planning.md`, `specs/00-system.md` | `planner.md` |
| Saptarshi | Data, Science | `src/odyssey/data/`, `src/odyssey/science/`, `specs/03-uncertainty-science.md` (science ranking), `specs/05-data.md` | `data.md`, `science-uncertainty.md` |
| Shared | Docs and Demo | `README.md`, `docs/DEMO_SCRIPT.md`, `docs/EVALUATION_MAP.md`, `docs/TIMELINE.md` | `reviewer.md` |

## Rules of the road

- You may read anything. You edit only what your role owns.
- Need something from another role? Add it to the "Open questions" section of the owner's spec and ping them.
- Cross-role contracts (data shapes between modules) are in `docs/ARCHITECTURE.md`. Changing one needs both owners to agree.
- Specs were approved by Udit on Nov 14. If Disha's research changes a requirement, edit the spec, mark it `draft`, and re-approve. The first job of every agent is still to read `docs/RESEARCH_NOTES.md`.
- Udit is the tie-breaker on architecture. Disha is the tie-breaker on demo, UI, perception and uncertainty choices. Saptarshi is the tie-breaker on data and science ranking choices.
