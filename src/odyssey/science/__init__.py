"""Science ranking (spec 03). Formulas and the noise model are documented in `model.py`.

Exposes the two stage functions the pipeline looks for: `find_candidates` and `rank_targets`.
"""

from .candidates import find_candidates
from .ranking import rank_targets

__all__ = ["find_candidates", "rank_targets"]
