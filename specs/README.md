# Specs

We build spec first. A spec is a short document that says what a module must do and how we will know it works. Code follows the spec, not the other way round.

## Lifecycle

`draft` -> `approved` -> `implemented` -> `verified`

- **draft**: owner is still writing. Nobody codes against it yet.
- **approved**: owner and one other teammate agree. Contracts are frozen. Target: 2:30 AM.
- **implemented**: code exists.
- **verified**: every acceptance check passed and the owner has shown it to the team.

Only the status line changes between stages. If requirements change after approval, edit the spec first, mark it `draft` again, and re-approve.

## Index

| Spec | Owner | Status |
|---|---|---|
| `00-system.md` | Udit | draft |
| `01-perception.md` | Disha | draft |
| `02-planning.md` | Udit | draft |
| `03-uncertainty-science.md` | Saptarshi | draft |
| `04-dashboard.md` | Saptarshi | draft |

Use `TEMPLATE.md` for any new spec.

## Rules

- One page per spec if you can. Judges never read it, but your teammates and agents do.
- Every requirement has an acceptance check that someone can run or look at.
- Every spec lists which judging criterion it serves.
