"""Loop guard for any step that moves the rover to a safer cell or re-plans (spec 02, requirement 14).

The planner itself is one shot and cannot loop. These helpers exist so that snapping a start or
goal, or a future replanning loop, cannot oscillate between two nearly equal choices.
All limits are assumptions.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Optional

import numpy as np

from ..contracts import Cell


class NoProgress(RuntimeError):
    """Raised when the rover revisits a cell too often or replans too many times."""


def snap_to_safe(passable: np.ndarray, cell: Cell, max_radius: float) -> Optional[Cell]:
    """Nearest passable cell by Euclidean distance, ties broken by (row, col).

    Deterministic. Returns None when no passable cell lies within `max_radius` cells.
    """
    if passable[cell]:
        return cell
    rr, cc = np.nonzero(passable)
    if rr.size == 0:
        return None
    d2 = (rr - cell[0]) ** 2 + (cc - cell[1]) ** 2
    best = d2.min()
    if math.sqrt(float(best)) > max_radius:
        return None
    tied = np.nonzero(d2 == best)[0]
    i = min(tied, key=lambda k: (int(rr[k]), int(cc[k])))
    return (int(rr[i]), int(cc[i]))


class ProgressGuard:
    def __init__(self, max_revisits: int = 2, max_replans: int = 10, switch_margin: float = 0.05):
        self.max_revisits = max_revisits
        self.max_replans = max_replans
        self.switch_margin = switch_margin
        self.visits: Counter = Counter()
        self.replans = 0

    def visit(self, cell: Cell) -> None:
        self.visits[cell] += 1
        if self.visits[cell] > self.max_revisits + 1:
            raise NoProgress(f"cell {cell} entered {self.visits[cell]} times, limit is {self.max_revisits + 1}")

    def replan(self) -> None:
        self.replans += 1
        if self.replans > self.max_replans:
            raise NoProgress(f"replanned {self.replans} times, limit is {self.max_replans}")

    def allow_switch(self, old_cost: float, new_cost: float) -> bool:
        """Accept a new route only if it is cheaper by more than the relative margin."""
        if not math.isfinite(old_cost):
            return math.isfinite(new_cost)
        return new_cost < old_cost * (1.0 - self.switch_margin)
