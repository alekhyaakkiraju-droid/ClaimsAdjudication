"""
WO-022: Explicit feedback and review sub-workflow state machines.

Preserves existing integer status values while centralizing valid transitions
for feedback_status and review_status fields.
"""

from __future__ import annotations

from claim.models import Claim

FEEDBACK_STATUS_LABELS = {
    Claim.FEEDBACK_IDLE: "idle",
    Claim.FEEDBACK_NOT_SELECTED: "not_selected",
    Claim.FEEDBACK_SELECTED: "selected",
    Claim.FEEDBACK_DELIVERED: "delivered",
    Claim.FEEDBACK_BYPASSED: "bypassed",
}

REVIEW_STATUS_LABELS = {
    Claim.REVIEW_IDLE: "idle",
    Claim.REVIEW_NOT_SELECTED: "not_selected",
    Claim.REVIEW_SELECTED: "selected",
    Claim.REVIEW_DELIVERED: "delivered",
    Claim.REVIEW_BYPASSED: "bypassed",
}

# Observed in feedback/review mutations and processing auto-bypass paths.
FEEDBACK_ALLOWED_TRANSITIONS: dict[int, frozenset[int]] = {
    Claim.FEEDBACK_IDLE: frozenset(
        {
            Claim.FEEDBACK_NOT_SELECTED,
            Claim.FEEDBACK_SELECTED,
            Claim.FEEDBACK_DELIVERED,
            Claim.FEEDBACK_BYPASSED,
        }
    ),
    Claim.FEEDBACK_NOT_SELECTED: frozenset(
        {
            Claim.FEEDBACK_SELECTED,
            Claim.FEEDBACK_BYPASSED,
        }
    ),
    Claim.FEEDBACK_SELECTED: frozenset(
        {
            Claim.FEEDBACK_NOT_SELECTED,
            Claim.FEEDBACK_DELIVERED,
            Claim.FEEDBACK_BYPASSED,
        }
    ),
    Claim.FEEDBACK_DELIVERED: frozenset(),
    Claim.FEEDBACK_BYPASSED: frozenset(),
}

REVIEW_ALLOWED_TRANSITIONS: dict[int, frozenset[int]] = {
    Claim.REVIEW_IDLE: frozenset(
        {
            Claim.REVIEW_NOT_SELECTED,
            Claim.REVIEW_SELECTED,
            Claim.REVIEW_DELIVERED,
            Claim.REVIEW_BYPASSED,
        }
    ),
    Claim.REVIEW_NOT_SELECTED: frozenset(
        {
            Claim.REVIEW_SELECTED,
            Claim.REVIEW_BYPASSED,
        }
    ),
    Claim.REVIEW_SELECTED: frozenset(
        {
            Claim.REVIEW_NOT_SELECTED,
            Claim.REVIEW_DELIVERED,
            Claim.REVIEW_BYPASSED,
        }
    ),
    Claim.REVIEW_DELIVERED: frozenset(),
    Claim.REVIEW_BYPASSED: frozenset(),
}


class FeedbackReviewStatusTransitionError(ValueError):
    """Raised when a feedback/review status change violates workflow rules."""

    def __init__(
        self,
        field: str,
        from_status: int,
        to_status: int,
        labels: dict[int, str],
        allowed: dict[int, frozenset[int]],
    ):
        from_label = labels.get(from_status, str(from_status))
        to_label = labels.get(to_status, str(to_status))
        allowed_targets = sorted(allowed.get(from_status, frozenset()))
        allowed_labels = [labels.get(s, str(s)) for s in allowed_targets]
        super().__init__(
            f"Invalid {field} transition from {from_label} ({from_status}) "
            f"to {to_label} ({to_status}). "
            f"Allowed targets: {', '.join(allowed_labels) or 'none'}."
        )
        self.field = field
        self.from_status = from_status
        self.to_status = to_status


def _can_transition(from_status: int, to_status: int, allowed: dict[int, frozenset[int]]) -> bool:
    if from_status == to_status:
        return True
    return to_status in allowed.get(from_status, frozenset())


def _validate_transition(
    field: str,
    from_status: int,
    to_status: int,
    labels: dict[int, str],
    allowed: dict[int, frozenset[int]],
) -> None:
    if not _can_transition(from_status, to_status, allowed):
        raise FeedbackReviewStatusTransitionError(
            field, from_status, to_status, labels, allowed
        )


def can_transition_feedback(from_status: int, to_status: int) -> bool:
    return _can_transition(from_status, to_status, FEEDBACK_ALLOWED_TRANSITIONS)


def can_transition_review(from_status: int, to_status: int) -> bool:
    return _can_transition(from_status, to_status, REVIEW_ALLOWED_TRANSITIONS)


def validate_feedback_transition(from_status: int, to_status: int) -> None:
    _validate_transition(
        "feedback_status",
        from_status,
        to_status,
        FEEDBACK_STATUS_LABELS,
        FEEDBACK_ALLOWED_TRANSITIONS,
    )


def validate_review_transition(from_status: int, to_status: int) -> None:
    _validate_transition(
        "review_status",
        from_status,
        to_status,
        REVIEW_STATUS_LABELS,
        REVIEW_ALLOWED_TRANSITIONS,
    )


def apply_feedback_status(claim: Claim, new_status: int) -> None:
    validate_feedback_transition(claim.feedback_status, new_status)
    claim.feedback_status = new_status


def apply_review_status(claim: Claim, new_status: int) -> None:
    validate_review_transition(claim.review_status, new_status)
    claim.review_status = new_status
