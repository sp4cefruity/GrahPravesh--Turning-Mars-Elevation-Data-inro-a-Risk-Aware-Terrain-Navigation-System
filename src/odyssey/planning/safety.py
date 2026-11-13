"""Path safety verifier. Runs on the TRUE blocked mask, never the inflated one.

Fails loudly (SafetyViolation) when a path crosses a blocked cell, leaves the grid,
or has a step that is not between 8-connected neighbours.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..contracts import Cell


class SafetyViolation(RuntimeError):
    """A path crossed a blocked cell or is malformed."""


@dataclass
class SafetyReport:
    safe: bool
    violations: list[str] = field(default_factory=list)
    max_slope: float = float("nan")
    risk_score: float = float("nan")


def verify_path(cells: list[Cell], blocked: np.ndarray, slope_deg: np.ndarray, p_haz: np.ndarray,
                *, raise_on_violation: bool = True) -> SafetyReport:
    h, w = blocked.shape
    problems: list[str] = []
    if not cells:
        problems.append("empty path")
    for k, (r, c) in enumerate(cells):
        if not (0 <= r < h and 0 <= c < w):
            problems.append(f"cell {k} {(r, c)} is outside the grid")
        elif blocked[r, c]:
            problems.append(f"cell {k} {(r, c)} is blocked")
    for k, (a, b) in enumerate(zip(cells, cells[1:])):
        if max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1:
            problems.append(f"step {k} from {a} to {b} is not between neighbours")
    if problems:
        if raise_on_violation:
            raise SafetyViolation("; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else ""))
        return SafetyReport(False, problems)
    rr = np.array([c[0] for c in cells])
    cc = np.array([c[1] for c in cells])
    return SafetyReport(True, [], float(np.nanmax(slope_deg[rr, cc])), float(p_haz[rr, cc].sum()))
