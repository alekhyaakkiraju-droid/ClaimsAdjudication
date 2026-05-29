"""
WO-028: Shared eager-loading for claim report data-fetch paths.
"""

from __future__ import annotations

from django.db.models import Prefetch

from claim.models import Claim, ClaimItem, ClaimService


def _valid_items_queryset():
    return (
        ClaimItem.objects.filter(*ClaimItem.filter_validity())
        .select_related("item")
        .order_by("item__code")
    )


def _valid_services_queryset():
    return (
        ClaimService.objects.filter(*ClaimService.filter_validity())
        .select_related("service")
        .order_by("service__code")
    )


def claim_detail_report_queryset(queryset=None):
    """Eager-load relations used by claims_overview and claim_history reports."""
    if queryset is None:
        queryset = Claim.objects
    return queryset.select_related(
        "health_facility",
        "insuree",
        "admin",
    ).prefetch_related(
        Prefetch("items", queryset=_valid_items_queryset()),
        Prefetch("services", queryset=_valid_services_queryset()),
    )


def claim_operational_indicators_queryset(queryset=None):
    """Eager-load items/services for primary operational indicators aggregation."""
    if queryset is None:
        queryset = Claim.objects
    return queryset.prefetch_related(
        Prefetch(
            "items",
            queryset=ClaimItem.objects.filter(*ClaimItem.filter_validity()),
        ),
        Prefetch(
            "services",
            queryset=ClaimService.objects.filter(*ClaimService.filter_validity()),
        ),
    )


def claim_print_report_queryset(queryset=None):
    """Eager-load relations used by ClaimReportService (single-claim print)."""
    if queryset is None:
        queryset = Claim.objects
    return queryset.select_related(
        "health_facility",
        "insuree",
        "admin",
        "icd",
        "icd_1",
        "icd_2",
        "icd_3",
        "icd_4",
        "refer_from",
        "refer_to",
    ).prefetch_related(
        Prefetch("items", queryset=_valid_items_queryset()),
        Prefetch("services", queryset=_valid_services_queryset()),
    )


def claim_has_detail_report_prefetch(claim: Claim) -> bool:
    """True when detail-report select_related + prefetches are on the instance."""
    if not claim.pk:
        return False
    prefetched = getattr(claim, "_prefetched_objects_cache", {})
    if "items" not in prefetched or "services" not in prefetched:
        return False
    if claim.health_facility_id is None or claim.insuree_id is None:
        return False
    claim.health_facility  # noqa: B018
    claim.insuree  # noqa: B018
    claim.admin  # noqa: B018
    return True


def claim_has_print_report_prefetch(claim: Claim) -> bool:
    """True when print-report select_related + prefetches are on the instance."""
    if not claim_has_detail_report_prefetch(claim):
        return False
    claim.icd  # noqa: B018
    return True
