"""Two tiny table helpers shared by the data and science reports. NaN means "nothing to report", shown as n/a."""

from __future__ import annotations

import numpy as np


def mean(xs) -> float:
    xs = list(xs)
    return float(np.mean(xs)) if xs else float("nan")


def to_markdown(table) -> str:
    if not table:
        return "(no rows)"
    cols = list(table[0])
    fmt = lambda v: "n/a" if isinstance(v, float) and np.isnan(v) else (f"{v:.2f}" if isinstance(v, float) else str(v))
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(r[c]) for c in cols) + " |" for r in table]
    return "\n".join(lines)
