"""
WO-012: REST authorization map and permission class tests.
"""

from unittest import mock

from django.test import SimpleTestCase

from claim.apps import ClaimConfig
from claim.rest_authorization import (
    REST_ENDPOINT_PERMISSIONS,
    ClaimPrintRestPermission,
    user_has_rest_permission,
)


class RestAuthorizationMapTest(SimpleTestCase):
    def test_endpoints_mapped(self):
        self.assertEqual(
            set(REST_ENDPOINT_PERMISSIONS.keys()), {"print", "attach"}
        )

    def test_print_uses_claim_print_perms(self):
        self.assertEqual(REST_ENDPOINT_PERMISSIONS["print"], "claim_print_perms")

    def test_attach_uses_query_claims_perms(self):
        self.assertEqual(
            REST_ENDPOINT_PERMISSIONS["attach"], "gql_query_claims_perms"
        )


class ClaimRestPermissionRuntimeTest(SimpleTestCase):
    @mock.patch.object(ClaimConfig, "claim_print_perms", ["111006"])
    def test_runtime_config_resolution(self):
        class User:
            id = 1

            def has_perms(self, perms):
                return perms == ["111006"]

        class Request:
            user = User()

        perm = ClaimPrintRestPermission()
        self.assertTrue(perm.has_permission(Request(), None))
        self.assertFalse(user_has_rest_permission(User(), "attach"))
