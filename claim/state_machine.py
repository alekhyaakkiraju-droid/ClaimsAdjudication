"""
WO-021: Explicit claim lifecycle state machine.

Preserves existing integer status values while centralizing valid transitions
and structured errors for invalid status changes.
"""

from __future__ import annotations

from claim.models import Claim

STATUS_LABELS = {
    Claim.STATUS_REJECTED: "rejected",
    Claim.STATUS_ENTERED: "entered",
    Claim.STATUS_CHECKED: "checked",
    Claim.STATUS_PROCESSED: "processed",
    Claim.STATUS_VALUATED: "valuated",
}

# Valid forward transitions observed in services, validations, and mutations.
ALLOWED_TRANSITIONS: dict[int, frozenset[int]] = {
    Claim.STATUS_ENTERED: frozenset(
        {
            Claim.STATUS_CHECKED,
            Claim.STATUS_REJECTED,
            Claim.STATUS_VALUATED,
            Claim.STATUS_PROCESSED,
        }
    ),
    Claim.STATUS_CHECKED: frozenset(
        {
            Claim.STATUS_REJECTED,
            Claim.STATUS_PROCESSED,
            Claim.STATUS_VALUATED,
        }
    ),
    Claim.STATUS_REJECTED: frozenset(),
    Claim.STATUS_PROCESSED: frozenset(),
    Claim.STATUS_VALUATED: frozenset(),
}


class ClaimStatusTransitionError(ValueError):
    """Raised when a claim status change violates the lifecycle state machine."""

    def __init__(self, from_status: int, to_status: int):
        from_label = STATUS_LABELS.get(from_status, str(from_status))
        to_label = STATUS_LABELS.get(to_status, str(to_status))
        allowed = sorted(ALLOWED_TRANSITIONS.get(from_status, frozenset()))
        allowed_labels = [STATUS_LABELS.get(s, str(s)) for s in allowed]
        super().__init__(
            f"Invalid claim status transition from {from_label} ({from_status}) "
            f"to {to_label} ({to_status}). "
            f"Allowed targets: {', '.join(allowed_labels) or 'none'}."
        )
        self.from_status = from_status
        self.to_status = to_status


def can_transition(from_status: int, to_status: int) -> bool:
    if from_status == to_status:
        return True
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def validate_transition(from_status: int, to_status: int) -> None:
    if not can_transition(from_status, to_status):
        raise ClaimStatusTransitionError(from_status, to_status)


def apply_claim_status(claim: Claim, new_status: int) -> None:
    """Validate and assign a new claim status."""
    validate_transition(claim.status, new_status)
    claim.status = new_status
