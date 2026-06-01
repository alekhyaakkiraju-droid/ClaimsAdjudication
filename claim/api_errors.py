"""
Safe lookups and consistent client-facing errors (WO-014).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from claim.models import Claim
from claim.query_cache import NOT_FOUND, get_cached_claim_pk, set_cached_claim_pk
from claim.read_queryset import claim_read_queryset
from insuree.models import Insuree

logger = logging.getLogger(__name__)


def get_valid_claim(
    *,
    claim_id: Optional[int] = None,
    claim_uuid: Optional[Union[str, UUID]] = None,
) -> Optional[Claim]:
    """Return a valid claim or None without raising DoesNotExist."""
    cached_pk = get_cached_claim_pk(claim_id=claim_id, claim_uuid=claim_uuid)
    qs = claim_read_queryset(Claim.objects.filter(*Claim.filter_validity()))
    if cached_pk is not None:
        if cached_pk == NOT_FOUND:
            return None
        return qs.filter(pk=cached_pk).first()

    if claim_id is not None:
        claim = qs.filter(id=claim_id).first()
        set_cached_claim_pk(claim_id=claim_id, pk=claim.pk if claim else None)
        return claim
    if claim_uuid is not None:
        claim = qs.filter(uuid=claim_uuid).first()
        set_cached_claim_pk(claim_uuid=claim_uuid, pk=claim.pk if claim else None)
        return claim
    return None


def get_insuree_health_facility_for_fsp(insuree_code: str, date_claimed: date) -> Any:
    """
    Resolve FSP (health facility) for an insuree at a date.
    Returns None when insuree is missing (no NPE).
    """
    insuree = (
        Insuree.objects.filter(
            chf_id=insuree_code,
            *Insuree.filter_validity(validity=date_claimed),
        )
        .select_related("health_facility")
        .first()
    )
    if insuree is None:
        return None
    return insuree.health_facility


def claim_not_found_errors(claim_uuid: Union[str, UUID]) -> List[Dict[str, Any]]:
    return [
        {
            "message": _("claim.validation.id_does_not_exist") % {"id": claim_uuid},
        }
    ]


def mutation_error_list(
    message: Union[str, Any],
    claim_code: Optional[str] = None,
    exc: Optional[BaseException] = None,
) -> List[Dict[str, Any]]:
    """
    OpenIMIS mutation error shape. Unexpected exceptions are logged; details are
    not leaked to clients.
    """
    if claim_code is not None and "%(" in str(message):
        entry: Dict[str, Any] = {"message": message % {"code": claim_code}}
    else:
        entry = {"message": str(message)}
    if exc is None:
        return [entry]
    if isinstance(exc, (ValidationError, PermissionDenied)):
        entry["detail"] = str(exc)
    else:
        logger.exception("claim mutation error: %s", entry["message"])
    return [entry]
