"""
Safe lookups and consistent client-facing errors (WO-014).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from claim.models import Claim
from claim.read_queryset import claim_read_queryset
from insuree.models import Insuree

logger = logging.getLogger(__name__)


def get_valid_claim(*, claim_id: Optional[int] = None, claim_uuid: Optional[Union[str, UUID]] = None):
    """Return a valid claim or None without raising DoesNotExist."""
    qs = claim_read_queryset(Claim.objects.filter(*Claim.filter_validity()))
    if claim_id is not None:
        return qs.filter(id=claim_id).first()
    if claim_uuid is not None:
        return qs.filter(uuid=claim_uuid).first()
    return None


def get_insuree_health_facility_for_fsp(insuree_code: str, date_claimed):
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


def claim_not_found_errors(claim_uuid) -> List[Dict[str, Any]]:
    return [
        {
            "message": _("claim.validation.id_does_not_exist") % {"id": claim_uuid},
        }
    ]


def mutation_error_list(message, claim_code=None, exc: Optional[BaseException] = None):
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
