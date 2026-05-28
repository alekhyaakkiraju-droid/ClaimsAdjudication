"""
WO-018: Shared eager-loading for claim GraphQL read paths.
"""

from __future__ import annotations

from django.db.models import Prefetch

from claim.models import Claim, ClaimAttachment, ClaimItem, ClaimMutation, ClaimService


def _claim_read_prefetches():
    return (
        Prefetch(
            "items",
            queryset=ClaimItem.objects.filter(
                *ClaimItem.filter_validity(),
                legacy_id__isnull=True,
            ),
        ),
        Prefetch(
            "services",
            queryset=ClaimService.objects.filter(
                *ClaimService.filter_validity(),
                legacy_id__isnull=True,
            ),
        ),
        Prefetch(
            "attachments",
            queryset=ClaimAttachment.objects.filter(
                *ClaimAttachment.filter_validity(),
                legacy_id__isnull=True,
            ),
        ),
        Prefetch(
            "mutations",
            queryset=ClaimMutation.objects.select_related("mutation").filter(
                mutation__status=0
            ),
        ),
    )


def apply_claim_read_prefetches(queryset=None):
    """Prefetch nested claim relations without select_related.

    Use before gql_optimizer.query() — select_related on insuree/health_facility
    conflicts with gql_optimizer field deferral.
    """
    if queryset is None:
        queryset = Claim.objects
    return queryset.prefetch_related(*_claim_read_prefetches())


def claim_read_queryset(queryset=None):
    """Eager-load relations used by single-claim lookups (e.g. get_valid_claim)."""
    if queryset is None:
        queryset = Claim.objects
    return queryset.select_related(
        "health_facility",
        "insuree",
        "admin",
        "icd",
        "batch_run",
        "feedback",
    ).prefetch_related(*_claim_read_prefetches())


def claim_has_read_prefetch(claim: Claim) -> bool:
    """True when read-path select_related + prefetches are already on the instance."""
    if not claim.pk:
        return False
    prefetched = getattr(claim, "_prefetched_objects_cache", {})
    required = {"items", "services", "attachments", "mutations"}
    if not required.issubset(prefetched):
        return False
    if claim.health_facility_id is None or claim.insuree_id is None:
        return False
    claim.health_facility  # noqa: B018
    claim.insuree  # noqa: B018
    return True
