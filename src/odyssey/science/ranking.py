"""Science step 2: ranking Monte Carlo.

score = weight(kind) * value / access cost, where access cost is the cautious path CVaR
(`PathResult.total_cost`, floored at the planner's base cost so a goal next to the start cannot divide
by zero). Each of `config.n_ranking_draws` draws samples
- value ~ Normal(mean, sd), sd recovered from the candidate interval, floored at 0 (feature noise),
- one weight per kind (ice, geology) ~ LogNormal(0, WEIGHT_SIGMA), the relative priority of the two
  science goals, which nobody knows exactly (weights).
Path cost is treated as fixed. The planner's own uncertainty is already inside the CVaR number.
Targets with no safe path are listed last with score 0 and rank interval after every reachable target.
Intervals are 5th to 95th percentiles. Seed: `config.seeds.ranking`.
"""

from __future__ import annotations

import numpy as np

from ..contracts import Candidate, ScienceTarget
from .model import Z90, sd_from_interval

WEIGHT_SIGMA = 0.2


def _confidence(c: Candidate, reachable: bool, span: int, n: int) -> str:
    if "NO DATA" in c.evidence or not reachable:
        return "low"
    if "CONFLICT" in c.evidence or "MISSING" in c.evidence:
        return "low" if span >= max(2, n // 3) else "medium"
    return "high" if span <= 1 else ("medium" if span <= max(2, n // 3) else "low")


def rank_targets(candidates, paths, terrain, hazards, config) -> list[ScienceTarget]:
    cands = list(candidates)
    if not cands:
        return []
    n, draws = len(cands), int(config.n_ranking_draws)
    rng = np.random.default_rng(config.seeds.ranking)
    base = config.planning.base_cost
    cost = np.array([paths[c.id]["cautious"].total_cost for c in cands], dtype=float)
    reach = np.isfinite(cost) & np.array([paths[c.id]["cautious"].safe for c in cands])
    cost = np.where(reach, np.maximum(cost, base), np.inf)

    mean = np.array([c.value_mean for c in cands])
    sd = np.array([sd_from_interval(c.value_mean, c.value_ci) for c in cands])
    z = rng.standard_normal((draws, n))
    w_draw = np.exp(WEIGHT_SIGMA * rng.standard_normal((draws, 2)))  # columns: ice, geology
    w = np.where(np.array([c.kind == "ice" for c in cands])[None, :], w_draw[:, [0]], w_draw[:, [1]])
    vals = np.clip(mean + sd * z, 0.0, None)
    scores = np.where(reach, w * vals / np.where(reach, cost, 1.0), 0.0)

    # ranks among reachable targets only, unreachable ones follow
    idx = np.flatnonzero(reach)
    n_r = len(idx)
    ranks = np.zeros((draws, n), dtype=int)
    if n_r:
        ranks[:, idx] = (-scores[:, idx]).argsort(axis=1).argsort(axis=1) + 1
    order_lost = np.flatnonzero(~reach)
    for i in order_lost:
        ranks[:, i] = n_r + 1 + int((~reach[:i]).sum())  # fixed slot, ordered by candidate order

    targets = []
    for i, c in enumerate(cands):
        pct = lambda a, q: float(np.percentile(a, q))
        v_ci = (pct(vals[:, i], 5), pct(vals[:, i], 95))
        if reach[i]:
            s_ci = (pct(scores[:, i], 5), pct(scores[:, i], 95))
            r_int = (int(np.floor(pct(ranks[:, i], 5))), int(np.ceil(pct(ranks[:, i], 95))))
            p3 = float((ranks[:, i] <= 3).mean())
            access = f"reachable, cautious path CVaR cost {cost[i]:.1f}"
        else:
            s_ci, r_int, p3 = (0.0, 0.0), (int(ranks[0, i]), int(ranks[0, i])), 0.0
            reason = paths[c.id]["cautious"].no_safe_path_reason
            access = "no safe path, so access cost is infinite and the score is 0" + (f" ({reason})" if reason else "")
        span = r_int[1] - r_int[0]
        conf = _confidence(c, bool(reach[i]), span, n)
        sure = (f"rank {r_int[0]} to {r_int[1]} of {n}, P(top 3) {p3:.2f}, score 90% interval "
                f"{s_ci[0]:.3f} to {s_ci[1]:.3f}" if reach[i] else "not ranked against reachable targets")
        evidence = f"{c.evidence} Access: {access}. How sure: {sure}. Overall {conf} confidence."
        targets.append(ScienceTarget(
            id=c.id, location=c.location, value_mean=c.value_mean, value_ci=v_ci,
            path_cost=float(cost[i]), score=float(scores[:, i].mean()), score_ci=s_ci,
            rank_interval=r_int, p_top3=p3, evidence=evidence, kind=c.kind))
    targets.sort(key=lambda t: (not np.isfinite(t.path_cost), -t.score, -t.value_mean, t.id))
    return targets
