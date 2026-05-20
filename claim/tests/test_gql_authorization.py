"""
WO-011: Tests for centralized GraphQL authorization maps.
"""

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, override_settings

from claim.apps import ClaimConfig
from claim.gql_authorization import (
    GQL_MUTATION_PERMISSION_MAP,
    GQL_QUERY_PERMISSION_MAP,
    list_mutation_classes,
    list_query_operations,
    require_query_permission,
)


class GqlAuthorizationMapTest(SimpleTestCase):
    def test_query_map_covers_schema_operations(self):
        required = {
            "claims",
            "claim",
            "claim_history",
            "claim_attachments",
            "claim_officers",
            "validate_claim_code",
            "fsp_from_claim",
            "claim_with_same_diagnosis",
            "insuree_name_by_chfid",
            "claim_gql_type",
        }
        self.assertTrue(required.issubset(set(GQL_QUERY_PERMISSION_MAP.keys())))

    def test_mutation_map_covers_all_exported_mutations(self):
        required = {
            "CreateClaimMutation",
            "UpdateClaimMutation",
            "AddClaimAttachmentMutation",
            "UpdateAttachmentMutation",
            "DeleteClaimAttachmentMutation",
            "SubmitClaimsMutation",
            "SelectClaimsForFeedbackMutation",
            "BypassClaimsFeedbackMutation",
            "SkipClaimsFeedbackMutation",
            "DeliverClaimFeedbackMutation",
            "SelectClaimsForReviewMutation",
            "BypassClaimsReviewMutation",
            "DeliverClaimsReviewMutation",
            "SkipClaimsReviewMutation",
            "SaveClaimReviewMutation",
            "ProcessClaimsMutation",
            "DeleteClaimsMutation",
        }
        self.assertEqual(required, set(GQL_MUTATION_PERMISSION_MAP.keys()))

    def test_list_helpers_match_maps(self):
        self.assertEqual(
            sorted(GQL_QUERY_PERMISSION_MAP.keys()), list_query_operations()
        )
        self.assertEqual(
            sorted(GQL_MUTATION_PERMISSION_MAP.keys()), list_mutation_classes()
        )

    def test_claim_attachments_uses_query_claims_perms(self):
        self.assertEqual(
            GQL_QUERY_PERMISSION_MAP["claim_attachments"],
            "gql_query_claims_perms",
        )

    def test_fsp_and_same_diagnosis_use_officers_perm_keys(self):
        self.assertEqual(
            GQL_QUERY_PERMISSION_MAP["fsp_from_claim"],
            "gql_query_claim_officers_perms",
        )
        self.assertEqual(
            GQL_QUERY_PERMISSION_MAP["claim_with_same_diagnosis"],
            "gql_query_claim_officers_perms",
        )


class RequireQueryPermissionRowSecurityTest(SimpleTestCase):
    @override_settings(ROW_SECURITY=False)
    def test_claims_query_skips_perm_when_row_security_disabled(self):
        class User:
            def has_perms(self, perms):
                return False

        class Ctx:
            user = User()

        class Info:
            context = Ctx()

        require_query_permission(Info(), "claims")


class RequireQueryPermissionRuntimeConfigTest(SimpleTestCase):
    @mock.patch.object(ClaimConfig, "gql_query_claim_officers_perms", ["999001"])
    def test_officers_perm_resolved_at_runtime_not_import(self):
        class User:
            def has_perms(self, perms):
                return perms == ["111001"]

        class Ctx:
            user = User()

        class Info:
            context = Ctx()

        with self.assertRaises(PermissionDenied):
            require_query_permission(Info(), "fsp_from_claim")
