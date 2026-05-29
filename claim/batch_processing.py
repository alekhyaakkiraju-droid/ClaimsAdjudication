"""
WO-025: Shared eager-loading and batch helpers for claim processing.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from claim.models import Claim
from claim.submission_pipeline import claim_submission_queryset
from claim.utils import get_claim_target_date, get_valid_policies_qs


def _policy_cache_key(claim: Claim) -> Tuple[int, str]:
    """Hashable cache key for insuree policies (AdDate is not hashable)."""
    return (claim.insuree_id, str(get_claim_target_date(claim)))


def claim_process_queryset(queryset=None):
    """Eager-load relations used by process_claims / processing_claim."""
    base = claim_submission_queryset(queryset)
    return base.select_related("icd", "icd_1", "icd_2", "icd_3", "icd_4")


class BatchPolicyCache:
    """Preload policies for a batch of claims keyed by (insuree_id, target_date)."""

    def __init__(self, claims: Iterable[Claim]):
        self._cache: dict[Tuple[int, str], list] = {}
        keys: set[Tuple[int, str]] = set()
        for claim in claims:
            if claim.insuree_id:
                keys.add(_policy_cache_key(claim))
        for insuree_id, target_date_str in keys:
            target_date = get_claim_target_date(
                next(c for c in claims if c.insuree_id == insuree_id)
            )
            self._cache[(insuree_id, target_date_str)] = list(
                get_valid_policies_qs(insuree_id, target_date)
            )

    def policies_for(self, claim: Claim) -> Optional[list]:
        if not claim.insuree_id:
            return None
        return list(self._cache.get(_policy_cache_key(claim), []))


def load_claims_for_processing(uuids: Sequence[str]) -> List[Claim]:
    """Load claims in caller UUID order with process-path prefetches."""
    if not uuids:
        return []
    normalized = [str(u).upper() for u in uuids]
    claims_qs = claim_process_queryset().filter(uuid__in=uuids)
    by_uuid = {str(claim.uuid).upper(): claim for claim in claims_qs}
    return [by_uuid[u] for u in normalized if u in by_uuid]


def missing_processing_uuids(
    requested: Sequence[str], loaded: Sequence[Claim]
) -> List[str]:
    loaded_set = {str(claim.uuid).upper() for claim in loaded}
    return [str(u) for u in requested if str(u).upper() not in loaded_set]


def claim_has_process_prefetch(claim: Claim) -> bool:
    prefetched = getattr(claim, "_prefetched_objects_cache", {})
    if "items" not in prefetched or "services" not in prefetched:
        return False
    if claim.health_facility_id is None or claim.insuree_id is None:
        return False
    claim.health_facility  # noqa: B018
    claim.insuree  # noqa: B018
    claim.icd  # noqa: B018
    return True
