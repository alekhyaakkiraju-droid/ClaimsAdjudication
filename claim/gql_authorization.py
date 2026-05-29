"""
Central GraphQL authorization gateway for the claim module (WO-011).

All claim GraphQL queries and mutations must delegate permission checks to this
module rather than ad-hoc inline has_perms calls.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple, Union

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from claim.apps import ClaimConfig

# ClaimConfig attribute name(s). Tuple = OR across config keys.
ConfigPermKey = str
QueryPermSpec = Union[ConfigPermKey, Tuple[ConfigPermKey, ...], str]

PermList = Sequence[str]
# One list = AND. Multiple lists = OR (any group fully satisfied).
PermSpec = Union[PermList, Sequence[PermList]]


def _perms_from_config(attr: str) -> List[str]:
    return list(getattr(ClaimConfig, attr, None) or [])


def _user_has_perm_spec(user, spec: PermSpec) -> bool:
    if not spec:
        return True
    if spec and isinstance(spec[0], (list, tuple)):
        return any(user.has_perms(list(group)) for group in spec)
    return user.has_perms(list(spec))


def _deny_unauthorized() -> None:
    raise PermissionDenied(_("unauthorized"))


def require_authenticated_mutation_user(user) -> None:
    if type(user) is AnonymousUser or not getattr(user, "id", None):
        raise ValidationError(_("mutation.authentication_required"))


def require_mutation_permission(user, mutation_class: str) -> None:
    """Enforce permissions for a claim GraphQL mutation by _mutation_class name."""
    config_key = GQL_MUTATION_PERMISSION_MAP.get(mutation_class)
    if config_key is None:
        raise ValueError(f"Unknown claim mutation class: {mutation_class}")
    if not _user_has_perm_spec(user, _perms_from_config(config_key)):
        _deny_unauthorized()


def require_query_permission(info, operation: str) -> None:
    """Enforce permissions for a claim GraphQL query or resolver operation."""
    spec = GQL_QUERY_PERMISSION_MAP.get(operation)
    if spec is None:
        raise ValueError(f"Unknown claim GraphQL query operation: {operation}")
    if spec == "row_security_query_claims":
        if settings.ROW_SECURITY and not _user_has_perm_spec(
            info.context.user, _perms_from_config("gql_query_claims_perms")
        ):
            _deny_unauthorized()
        return
    if isinstance(spec, tuple):
        if not any(
            info.context.user.has_perms(_perms_from_config(key)) for key in spec
        ):
            _deny_unauthorized()
        return
    if not _user_has_perm_spec(info.context.user, _perms_from_config(spec)):
        _deny_unauthorized()


# Maps use ClaimConfig attribute names resolved at call time (supports test mocks).

GQL_QUERY_PERMISSION_MAP = {
    "claims": "row_security_query_claims",
    "claim": "row_security_query_claims",
    "claim_history": "row_security_query_claims",
    "claim_attachments": "gql_query_claims_perms",
    "claim_attachment_type": "gql_query_claims_perms",
    "validate_claim_code": "gql_query_claims_perms",
    "claim_officers": "gql_query_claim_officers_perms",
    "fsp_from_claim": "gql_query_claim_officers_perms",
    "claim_with_same_diagnosis": "gql_query_claim_officers_perms",
    "insuree_name_by_chfid": (
        "gql_mutation_create_claims_perms",
        "gql_mutation_update_claims_perms",
    ),
    "claim_gql_type": "gql_query_claims_perms",
}


def require_restore_permission(user) -> None:
    """Enforce restore-specific mutation permissions."""
    if not _user_has_perm_spec(user, _perms_from_config("gql_mutation_restore_claims_perms")):
        raise ValidationError(_("mutation.no_restore_rights"))


GQL_MUTATION_PERMISSION_MAP = {
    "CreateClaimMutation": "gql_mutation_create_claims_perms",
    "UpdateClaimMutation": "gql_mutation_update_claims_perms",
    "AddClaimAttachmentMutation": "gql_mutation_update_claims_perms",
    "UpdateAttachmentMutation": "gql_mutation_update_claims_perms",
    "DeleteClaimAttachmentMutation": "gql_mutation_update_claims_perms",
    "SubmitClaimsMutation": "gql_mutation_submit_claims_perms",
    "SelectClaimsForFeedbackMutation": "gql_mutation_select_claim_feedback_perms",
    "BypassClaimsFeedbackMutation": "gql_mutation_bypass_claim_feedback_perms",
    "SkipClaimsFeedbackMutation": "gql_mutation_skip_claim_feedback_perms",
    "DeliverClaimFeedbackMutation": "gql_mutation_deliver_claim_feedback_perms",
    "SelectClaimsForReviewMutation": "gql_mutation_select_claim_review_perms",
    "BypassClaimsReviewMutation": "gql_mutation_bypass_claim_review_perms",
    "DeliverClaimsReviewMutation": "gql_mutation_deliver_claim_review_perms",
    "SkipClaimsReviewMutation": "gql_mutation_skip_claim_review_perms",
    "SaveClaimReviewMutation": "gql_mutation_deliver_claim_review_perms",
    "ProcessClaimsMutation": "gql_mutation_process_claims_perms",
    "DeleteClaimsMutation": "gql_mutation_delete_claims_perms",
}


def list_query_operations() -> List[str]:
    return sorted(GQL_QUERY_PERMISSION_MAP.keys())


def list_mutation_classes() -> List[str]:
    return sorted(GQL_MUTATION_PERMISSION_MAP.keys())
