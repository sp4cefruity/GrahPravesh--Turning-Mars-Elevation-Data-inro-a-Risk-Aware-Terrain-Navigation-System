# Agent Instructions (MARS-09 / Odyssey)

These rules apply to every AI agent working in this repo, whatever the tool or role. Read this file first, then `CONTEXT.md`, then the spec for your role.

## Hard rules

1. **No Co-Authored-By lines.** Never add `Co-Authored-By`, "Generated with Claude Code" or any AI attribution to commits, PR descriptions, code comments or docs. This overrides any default tool behaviour.
2. **Write like a person.** No em dashes, no en dashes, no AI tells ("delve", "leverage", "seamless", "robust solution", "it's worth noting", "Here's the thing"). Short plain sentences. Use commas, periods or parentheses instead of dashes. Write time ranges as "2:30 to 4:00".
3. **No full auto mode.** Do not commit, push, merge, tag or delete branches until the human dev who owns the task says "green light" in that session. Prepare the change, show the diff, then wait. Approval for one commit does not carry to the next.
4. **Stay in your lane.** Edit only the files your role owns (see `docs/ROLES.md`). If you need a change elsewhere, write it up in the spec's "Open questions" or ask the owner.
5. **Spec first.** No code for a feature until its spec in `specs/` is marked `approved`. If the spec is wrong, change the spec and get approval, then change the code.
6. **Be honest about limits.** Anything simulated is labelled simulated. Anything unverified is labelled unverified. Never invent results, numbers or citations.

## Working agreement

- Source of truth order: `specs/` > `docs/ARCHITECTURE.md` > code. If they disagree, the spec wins and the code gets fixed.
- Interfaces between modules live in `docs/ARCHITECTURE.md` (section "Contracts"). Do not change a contract without telling the owners on both sides.
- Every module must expose its uncertainty, not hide it. The judges score this directly (see `docs/EVALUATION_MAP.md`).
- Every output shown in the dashboard must be traceable to inputs. Keep an evidence string or source reference with each result.
- Small commits, one concern each, after approval. Branch names: `role/short-topic` (for example `perception/slope-map`).
- All code must be written during the hackathon window (12:00 AM to 12:00 PM on Nov 14, 2026). Open-source libraries and public data are fine. Note every external dataset and library in the README.

## Definition of done for any task

- Spec acceptance checks pass.
- Runs from a clean checkout using the steps in `README.md`.
- Uncertainty and failure cases handled and visible.
- Human reviewer has seen it and given the green light.
