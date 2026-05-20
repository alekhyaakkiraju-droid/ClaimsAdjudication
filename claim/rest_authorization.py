"""
Central REST authorization for claim module endpoints (WO-012).

Aligned with claim/gql_authorization.py: maps endpoints to ClaimConfig permission
attributes resolved at request time.
"""

from __future__ import annotations

from typing import List

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext as _
from rest_framework.permissions import BasePermission

from claim.apps import ClaimConfig

# REST path name -> ClaimConfig attribute (lazy resolution for tests/mocks).
REST_ENDPOINT_PERMISSIONS = {
    "print": "claim_print_perms",
    "attach": "gql_query_claims_perms",
}


def _perms_for_endpoint(endpoint: str) -> List[str]:
    attr = REST_ENDPOINT_PERMISSIONS.get(endpoint)
    if attr is None:
        raise ValueError(f"Unknown claim REST endpoint: {endpoint}")
    return list(getattr(ClaimConfig, attr, None) or [])


def user_has_rest_permission(user, endpoint: str) -> bool:
    if type(user) is AnonymousUser or not getattr(user, "id", None):
        return False
    return user.has_perms(_perms_for_endpoint(endpoint))


def require_rest_permission(request, endpoint: str) -> None:
    """Raise PermissionDenied (403) when authenticated user lacks rights."""
    if not user_has_rest_permission(request.user, endpoint):
        raise PermissionDenied(_("unauthorized"))


class ClaimPrintRestPermission(BasePermission):
    """DRF permission for GET /claim/print/."""

    def has_permission(self, request, view):
        return user_has_rest_permission(request.user, "print")


class ClaimAttachRestPermission(BasePermission):
    """DRF permission for /claim/attach/."""

    def has_permission(self, request, view):
        return user_has_rest_permission(request.user, "attach")
