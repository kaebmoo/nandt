"""Wait-time estimator contract (§5.5).

Caller must use get_estimator(...).estimate(entry, now) rather than computing wait
inline, so the algorithm can switch later without touching queue routes/templates.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EstimateResult:
    wait_minutes: float
    people_ahead: int
    method: str
    confidence: str = "approx"


class WaitEstimator(Protocol):
    def estimate(self, entry, now=None) -> EstimateResult:
        ...


def get_estimator(db, tenant_config=None) -> WaitEstimator:
    """Factory seam for future Erlang-C/ML estimators; currently always simple_avg."""
    from .simple_avg import SimpleAverageEstimator

    return SimpleAverageEstimator(db, tenant_config=tenant_config)
