"""
Central GraphQL authorization gateway for the claim module (WO-011).

All claim GraphQL queries and mutations must delegate permission checks to this
module rather than ad-hoc inline has_perms calls.
"""

from __future__ import annotations

from typing import List, Sequence, Union

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from claim.apps import ClaimConfig

PermList = Sequence[str]
# One list = AND (all perms in list). Multiple lists = OR (any list fully satisfied).
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
    spec = GQL_MUTATION_PERMISSION_MAP.get(mutation_class)
    if spec is None:
        raise ValueError(f"Unknown claim mutation class: {mutation_class}")
    if not _user_has_perm_spec(user, spec):
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
    if not _user_has_perm_spec(info.context.user, spec):
        _deny_unauthorized()


# --- Permission map: GraphQL operation -> ClaimConfig rights ---

GQL_QUERY_PERMISSION_MAP = {
    # List/detail queries (ROW_SECURITY gates denial when enabled)
    "claims": "row_security_query_claims",
    "claim": "row_security_query_claims",
    "claim_history": "row_security_query_claims",
    # Always enforced query operations
    "claim_attachments": _perms_from_config("gql_query_claims_perms"),
    "claim_attachment_type": _perms_from_config("gql_query_claims_perms"),
    "validate_claim_code": _perms_from_config("gql_query_claims_perms"),
    "claim_officers": _perms_from_config("gql_query_claim_officers_perms"),
    "fsp_from_claim": _perms_from_config("gql_query_claim_officers_perms"),
    "claim_with_same_diagnosis": _perms_from_config("gql_query_claim_officers_perms"),
    "insuree_name_by_chfid": (
        _perms_from_config("gql_mutation_create_claims_perms"),
        _perms_from_config("gql_mutation_update_claims_perms"),
    ),
    # ClaimGQLType field resolvers
    "claim_gql_type": _perms_from_config("gql_query_claims_perms"),
}

GQL_MUTATION_PERMISSION_MAP = {
    "CreateClaimMutation": _perms_from_config("gql_mutation_create_claims_perms"),
    "UpdateClaimMutation": _perms_from_config("gql_mutation_update_claims_perms"),
    "AddClaimAttachmentMutation": _perms_from_config("gql_mutation_update_claims_perms"),
    "UpdateAttachmentMutation": _perms_from_config("gql_mutation_update_claims_perms"),
    "DeleteClaimAttachmentMutation": _perms_from_config(
        "gql_mutation_update_claims_perms"
    ),
    "SubmitClaimsMutation": _perms_from_config("gql_mutation_submit_claims_perms"),
    "SelectClaimsForFeedbackMutation": _perms_from_config(
        "gql_mutation_select_claim_feedback_perms"
    ),
    "BypassClaimsFeedbackMutation": _perms_from_config(
        "gql_mutation_bypass_claim_feedback_perms"
    ),
    "SkipClaimsFeedbackMutation": _perms_from_config(
        "gql_mutation_skip_claim_feedback_perms"
    ),
    "DeliverClaimFeedbackMutation": _perms_from_config(
        "gql_mutation_deliver_claim_feedback_perms"
    ),
    "SelectClaimsForReviewMutation": _perms_from_config(
        "gql_mutation_select_claim_review_perms"
    ),
    "BypassClaimsReviewMutation": _perms_from_config(
        "gql_mutation_bypass_claim_review_perms"
    ),
    "DeliverClaimsReviewMutation": _perms_from_config(
        "gql_mutation_deliver_claim_review_perms"
    ),
    "SkipClaimsReviewMutation": _perms_from_config(
        "gql_mutation_skip_claim_review_perms"
    ),
    "SaveClaimReviewMutation": _perms_from_config(
        "gql_mutation_deliver_claim_review_perms"
    ),
    "ProcessClaimsMutation": _perms_from_config("gql_mutation_process_claims_perms"),
    "DeleteClaimsMutation": _perms_from_config("gql_mutation_delete_claims_perms"),
}


def list_query_operations() -> List[str]:
    return sorted(GQL_QUERY_PERMISSION_MAP.keys())


def list_mutation_classes() -> List[str]:
    return sorted(GQL_MUTATION_PERMISSION_MAP.keys())
