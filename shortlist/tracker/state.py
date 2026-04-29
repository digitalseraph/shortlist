"""Job status state machine.

Linear-with-branches: new → tailored → applied → screen → interview → offer
                                                               ↘ rejected
                      `withdrawn` reachable from any non-terminal state.
                      Terminal states (offer, rejected, withdrawn) have no
                      outgoing transitions.
"""

from __future__ import annotations

from shortlist.models import JobStatus

_GRAPH: dict[JobStatus, set[JobStatus]] = {
    "new": {"tailored", "withdrawn"},
    "tailored": {"applied", "withdrawn"},
    "applied": {"screen", "rejected", "withdrawn"},
    "screen": {"interview", "rejected", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "offer": set(),
    "rejected": set(),
    "withdrawn": set(),
}


class InvalidStatusTransitionError(ValueError):
    pass


def allowed_next(current: JobStatus) -> set[JobStatus]:
    return _GRAPH.get(current, set())


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in _GRAPH:
        raise InvalidStatusTransitionError(f"unknown status {target!r}")
    if target not in allowed_next(current):
        raise InvalidStatusTransitionError(
            f"cannot transition {current!r} → {target!r}; allowed: {sorted(allowed_next(current))}"
        )
