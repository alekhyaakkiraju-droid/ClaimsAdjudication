"""
WO-019: Efficient diagnosis variance filtering for claim GraphQL queries.

Replaces per-row correlated subqueries with a single aggregate lookup and
optional short-lived cache for diagnosis average approved amounts.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from claim.query_cache import safe_cache_get, safe_cache_set
from django.db.models import Avg, Q

from claim.apps import ClaimConfig
from claim.models import Claim

DIAGNOSIS_VARIANCE_CACHE_TTL = 300
DIAGNOSIS_VARIANCE_CACHE_PREFIX = "claim:diag_variance_avgs:"


def _variance_cache_key(last_year_date) -> str:
    payload = json.dumps({"last_year": str(last_year_date)}, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"{DIAGNOSIS_VARIANCE_CACHE_PREFIX}{digest}"


def fetch_diagnosis_avg_approved(*, validity_filters, last_year_date) -> dict[str, float]:
    """Return icd code -> average approved amount for claims in the lookback window."""
    cache_key = _variance_cache_key(last_year_date)
    cached = safe_cache_get(cache_key)
    if cached is not None:
        return cached

    rows = (
        Claim.objects.filter(*validity_filters)
        .filter(date_claimed__gt=last_year_date, icd__code__isnull=False)
        .values("icd__code")
        .annotate(diag_avg=Avg("approved"))
    )
    result = {
        row["icd__code"]: row["diag_avg"]
        for row in rows
        if row["icd__code"] is not None
    }
    safe_cache_set(cache_key, result, DIAGNOSIS_VARIANCE_CACHE_TTL)
    return result


def build_diagnosis_variance_filter(
    variance: int,
    *,
    validity_filters,
    last_year_date,
    only_on_existing: bool | None = None,
) -> Q:
    """Build a Q filter for high-variance claims without correlated subqueries."""
    if only_on_existing is None:
        only_on_existing = ClaimConfig.gql_query_claim_diagnosis_variance_only_on_existing

    threshold_factor = Decimal(1) + Decimal(variance) / Decimal(100)
    avg_by_code = fetch_diagnosis_avg_approved(
        validity_filters=validity_filters,
        last_year_date=last_year_date,
    )

    high_variance_q = Q()
    for code, diag_avg in avg_by_code.items():
        if diag_avg is None:
            continue
        threshold = threshold_factor * Decimal(str(diag_avg))
        high_variance_q |= Q(icd__code=code, claimed__gt=threshold)

    if only_on_existing:
        return high_variance_q if high_variance_q else Q(pk__in=[])

    existing_codes = list(avg_by_code.keys())
    if existing_codes:
        return high_variance_q | ~Q(icd__code__in=existing_codes)
    return high_variance_q
