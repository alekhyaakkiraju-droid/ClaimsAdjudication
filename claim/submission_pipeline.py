"""
WO-017: Shared eager-loading for the claim submission path.
"""

from __future__ import annotations

from typing import Union

from django.db.models import Prefetch, Q

from claim.models import Claim, ClaimItem, ClaimService


def _active_child_filter():
    return Q(Q(rejection_reason=0) | Q(rejection_reason__isnull=True))


def claim_submission_queryset(queryset=None):
    """Eager-load relations used by submit_claim, save_history, and validate_claim."""
    if queryset is None:
        queryset = Claim.objects
    return queryset.select_related(
        "health_facility",
        "health_facility__items_pricelist",
        "health_facility__services_pricelist",
        "insuree",
        "admin",
    ).prefetch_related(
        Prefetch(
            "items",
            queryset=ClaimItem.objects.filter(
                *ClaimItem.filter_validity(),
                _active_child_filter(),
            ),
        ),
        Prefetch(
            "services",
            queryset=ClaimService.objects.filter(
                *ClaimService.filter_validity(),
                _active_child_filter(),
            ),
        ),
    )


def claim_has_submission_prefetch(claim: Claim) -> bool:
    """True when select_related + item/service prefetches are already on the instance."""
    if not claim.pk:
        return False
    prefetched = getattr(claim, "_prefetched_objects_cache", {})
    if "items" not in prefetched or "services" not in prefetched:
        return False
    if claim.health_facility_id is None or claim.insuree_id is None:
        return False
    # Touch cached relations — must not hit the database.
    claim.health_facility  # noqa: B018
    claim.insuree  # noqa: B018
    return True


def load_claim_for_submission(claim: Union[Claim, int]) -> Claim:
    """Reload a claim with submission-path prefetches (avoids N+1 during validation)."""
    if isinstance(claim, Claim) and claim_has_submission_prefetch(claim):
        return claim
    claim_id = claim.id if isinstance(claim, Claim) else claim
    return claim_submission_queryset().get(id=claim_id)
