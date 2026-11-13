# Roles and Ownership

Three humans, each with one or more AI agents working under them. An agent works for the human who owns its role. Agent definitions are in `.claude/agents/`.

| Human | Role | Owns (folders) | Agent file |
|---|---|---|---|
| Disha | Research and Perception | `src/odyssey/perception/`, `src/odyssey/data/`, `docs/RESEARCH_NOTES.md`, `specs/01-perception.md` | `perception.md` |
| Udit | Architecture, Planning, Integration | `src/odyssey/planning/`, `src/odyssey/pipeline.py`, `docs/ARCHITECTURE.md`, `specs/02-planning.md`, `specs/00-system.md` | `planner.md` |
| Saptarshi | Uncertainty, Science, Dashboard | `src/odyssey/uncertainty/`, `src/odyssey/science/`, `src/odyssey/dashboard/`, `specs/03-uncertainty-science.md`, `specs/04-dashboard.md` | `science-uncertainty.md`, `dashboard.md` |
| Shared | Docs and Demo | `README.md`, `docs/DEMO_SCRIPT.md`, `docs/EVALUATION_MAP.md`, `docs/TIMELINE.md` | `reviewer.md` |

## Rules of the road

- You may read anything. You edit only what your role owns.
- Need something from another role? Add it to the "Open questions" section of the owner's spec and ping them.
- Cross-role contracts (data shapes between modules) are in `docs/ARCHITECTURE.md`. Changing one needs both owners to agree.
- Disha's research may reshape the flow. Until she confirms, all specs stay `draft`, and the first job of every agent is to read `docs/RESEARCH_NOTES.md`.
- Udit is the tie-breaker on architecture. Saptarshi is the tie-breaker on demo and UI. Disha is the tie-breaker on science and perception choices.
