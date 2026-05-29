"""
WO-024: Formalized claim restore validation rules.

Restore creates a new claim linked to a previously rejected claim via the
``restore`` foreign key. Rules enforced:

- Caller must hold ``ClaimConfig.gql_mutation_restore_claims_perms``.
- Source claim must exist, be valid, and have ``STATUS_REJECTED``.
- When ``ClaimConfig.claim_max_restore`` is set, the number of existing restore
  claims pointing at the same source must stay below that limit.
- When ``claim_max_restore`` is ``None``, no maximum is enforced (documented).
"""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from claim.apps import ClaimConfig
from claim.models import Claim


def count_restores_for_source(source_claim: Claim) -> int:
    """Return how many valid claims were restored from ``source_claim``."""
    return Claim.objects.filter(
        restore=source_claim,
        validity_to__isnull=True,
    ).count()


def validate_restore_request(restore_uuid, user) -> Claim:
    """Validate a restore request and return the source rejected claim."""
    from claim.gql_authorization import require_restore_permission

    require_restore_permission(user)

    if not restore_uuid:
        raise ValidationError(_("mutation.restored_from_does_not_exist"))

    lookup_uuid = restore_uuid
    if isinstance(restore_uuid, Claim):
        lookup_uuid = restore_uuid.uuid

    source = (
        Claim.objects.filter(uuid=lookup_uuid, validity_to__isnull=True)
        .select_related("restore")
        .first()
    )
    if source is None:
        raise ValidationError(_("mutation.restored_from_does_not_exist"))

    if source.status != Claim.STATUS_REJECTED:
        raise ValidationError(_("mutation.cannot_restore_not_rejected_claim"))

    max_restore = ClaimConfig.claim_max_restore
    if max_restore is not None:
        existing = count_restores_for_source(source)
        if existing >= max_restore:
            raise ValidationError(
                _("mutation.max_restored_claim") % {"max_restore": max_restore}
            )

    return source


def resolve_restore_uuid(restore_uuid) -> UUID | str | None:
    """Normalize restore input to a UUID usable for FK lookup."""
    if restore_uuid is None:
        return None
    if isinstance(restore_uuid, Claim):
        return restore_uuid.uuid
    return restore_uuid
