"""
WO-020: Query cache for claim reads and reference data.

Uses Django's cache framework (Redis when configured by the assembly) with
graceful degradation when the cache backend is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Iterable, Optional, TypeVar

from django.core.cache import cache
from django.db.models import QuerySet

logger = logging.getLogger(__name__)

T = TypeVar("T")

CACHE_PREFIX = "claim:"
NOT_FOUND = "__not_found__"
LIST_VERSION_KEY = f"{CACHE_PREFIX}list:version"
OFFICERS_VERSION_KEY = f"{CACHE_PREFIX}ref:officers:version"


def _is_cache_enabled() -> bool:
    from claim.apps import ClaimConfig

    return bool(getattr(ClaimConfig, "query_cache_enabled", True))


def _reference_ttl() -> int:
    from claim.apps import ClaimConfig

    return int(getattr(ClaimConfig, "query_cache_reference_ttl", 300))


def _detail_ttl() -> int:
    from claim.apps import ClaimConfig

    return int(getattr(ClaimConfig, "query_cache_detail_ttl", 120))


def _list_ttl() -> int:
    from claim.apps import ClaimConfig

    return int(getattr(ClaimConfig, "query_cache_list_ttl", 60))


def safe_cache_get(key: str) -> Any | None:
    if not _is_cache_enabled():
        return None
    try:
        return cache.get(key)
    except Exception:
        logger.warning("claim query cache get failed for %s", key, exc_info=True)
        return None


def safe_cache_set(key: str, value: Any, timeout: int | None) -> bool:
    if not _is_cache_enabled():
        return False
    try:
        cache.set(key, value, timeout)
        return True
    except Exception:
        logger.warning("claim query cache set failed for %s", key, exc_info=True)
        return False


def safe_cache_delete(key: str) -> None:
    if not _is_cache_enabled():
        return
    try:
        cache.delete(key)
    except Exception:
        logger.warning("claim query cache delete failed for %s", key, exc_info=True)


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def claim_detail_cache_key(*, claim_id: int | None = None, claim_uuid=None) -> str | None:
    if claim_id is not None:
        return f"{CACHE_PREFIX}detail:id:{claim_id}"
    if claim_uuid is not None:
        return f"{CACHE_PREFIX}detail:uuid:{claim_uuid}"
    return None


def attachment_types_cache_key() -> str:
    return f"{CACHE_PREFIX}ref:attachment_types"


def officers_cache_key(search: str | None) -> str:
    version = safe_cache_get(OFFICERS_VERSION_KEY) or 0
    return f"{CACHE_PREFIX}ref:officers:v{version}:{search or ''}"


def claim_list_cache_key(filters: dict) -> str:
    version = safe_cache_get(LIST_VERSION_KEY) or 0
    return f"{CACHE_PREFIX}list:v{version}:{_digest(filters)}"


def cached_or_load(key: str, loader: Callable[[], T], *, timeout: int) -> T:
    cached = safe_cache_get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    result = loader()
    safe_cache_set(key, result, timeout)
    return result


def cached_queryset_pks(key: str, queryset: QuerySet, *, timeout: int) -> QuerySet:
    """Return queryset scoped to cached PKs, or evaluate and cache PKs."""
    cached = safe_cache_get(key)
    if cached is not None:
        if not cached:
            return queryset.none()
        return queryset.filter(pk__in=cached)
    pks = list(queryset.values_list("pk", flat=True))
    safe_cache_set(key, pks, timeout)
    if not pks:
        return queryset.none()
    return queryset.filter(pk__in=pks)


def get_cached_claim_pk(*, claim_id: int | None = None, claim_uuid=None) -> Optional[int | str]:
    """Return cached claim PK, NOT_FOUND sentinel, or None when uncached."""
    key = claim_detail_cache_key(claim_id=claim_id, claim_uuid=claim_uuid)
    if key is None:
        return None
    return safe_cache_get(key)


def set_cached_claim_pk(
    *,
    claim_id: int | None = None,
    claim_uuid=None,
    pk: int | None,
) -> None:
    key = claim_detail_cache_key(claim_id=claim_id, claim_uuid=claim_uuid)
    if key is None:
        return
    value = NOT_FOUND if pk is None else pk
    safe_cache_set(key, value, _detail_ttl())


def invalidate_claim_cache(
    *,
    claim_ids: Iterable[int] | None = None,
    claim_uuids: Iterable | None = None,
) -> None:
    if claim_ids:
        for claim_id in claim_ids:
            key = claim_detail_cache_key(claim_id=claim_id)
            if key:
                safe_cache_delete(key)
    if claim_uuids:
        for claim_uuid in claim_uuids:
            key = claim_detail_cache_key(claim_uuid=claim_uuid)
            if key:
                safe_cache_delete(key)
    bump_list_cache_version()


def bump_list_cache_version() -> None:
    version = int(safe_cache_get(LIST_VERSION_KEY) or 0) + 1
    safe_cache_set(LIST_VERSION_KEY, version, timeout=None)


def invalidate_reference_cache() -> None:
    safe_cache_delete(attachment_types_cache_key())
    version = int(safe_cache_get(OFFICERS_VERSION_KEY) or 0) + 1
    safe_cache_set(OFFICERS_VERSION_KEY, version, timeout=None)
