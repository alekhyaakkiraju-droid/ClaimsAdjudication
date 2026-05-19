"""
Characterization tests for claim API permissions (WO-003).

Documents current authorization behavior across GraphQL queries, mutations, and REST
endpoints before centralized security enforcement.
"""

import base64
import json
from unittest import mock

from django.conf import settings
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from claim import schema as claim_schema
from claim.apps import ClaimConfig
from claim.models import ClaimAttachment, ClaimAttachmentType, GeneralClaimAttachmentType
from claim.test_helpers import create_test_claim
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_test_interactive_user, create_test_role
from graphql_jwt.shortcuts import get_token
from medical.test_helpers import create_test_diagnosis
from uuid import uuid4


def _errors_text(content):
    if "errors" not in content:
        return ""
    return json.dumps(content["errors"]).lower()


class ClaimPermissionCharacterizationTest(openIMISGraphQLTestCase):
    """GraphQL permission behavior as implemented today."""

    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.authorized_user = create_test_interactive_user(username="wo003-authorized")
        cls.authorized_token = get_token(
            cls.authorized_user, BaseTestContext(user=cls.authorized_user)
        )

        no_claim_role = create_test_role(
            perm_names=[],
            name=f"WO003NoClaimPerms-{uuid4().hex[:8]}",
        )
        cls.unauthorized_user = create_test_interactive_user(
            username="wo003-unauthorized",
            roles=[no_claim_role.id],
        )
        cls.unauthorized_token = get_token(
            cls.unauthorized_user, BaseTestContext(user=cls.unauthorized_user)
        )

        claims_only_role = create_test_role(
            perm_names=["gql_query_claims_perms"],
            name=f"WO003ClaimsQueryOnly-{uuid4().hex[:8]}",
        )
        cls.claims_only_user = create_test_interactive_user(
            username="wo003-claims-only",
            roles=[claims_only_role.id],
        )
        cls.claims_only_token = get_token(
            cls.claims_only_user, BaseTestContext(user=cls.claims_only_user)
        )

        cls.test_claim = create_test_claim()
        cls.test_insuree = cls.test_claim.insuree
        cls.test_icd = create_test_diagnosis()

    def _assert_graphql_unauthorized(self, response):
        content = json.loads(response.content)
        self.assertIn("errors", content)
        self.assertIn("unauthorized", _errors_text(content))

    def _assert_graphql_authorized_no_errors(self, response):
        content = json.loads(response.content)
        self.assertNotIn("errors", content, content.get("errors"))

    # --- Unauthorized GraphQL queries ---

    @override_settings(ROW_SECURITY=True)
    def test_unauthorized_claims_query_denied(self):
        response = self.query(
            """
            query {
                claims { totalCount }
            }
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)

    def test_unauthorized_validate_claim_code_denied(self):
        response = self.query(
            """
            query {
                validateClaimCode(claimCode: "WO003-TEST")
            }
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)

    @override_settings(ROW_SECURITY=True)
    def test_unauthorized_single_claim_query_denied(self):
        response = self.query(
            f"""
            query {{
                claim(id: {self.test_claim.id}) {{ id code }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)

    def test_authorized_validate_claim_code_succeeds(self):
        response = self.query(
            """
            query {
                validateClaimCode(claimCode: "WO003-UNIQUE-CODE")
            }
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.authorized_token}"},
        )
        self._assert_graphql_authorized_no_errors(response)

    # --- claim_attachments stub ---

    def test_claim_attachments_unauthorized_without_claims_perm(self):
        response = self.query(
            """
            query {
                claimAttachments { totalCount }
            }
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)

    def test_claim_attachments_stub_returns_null_when_authorized(self):
        """Resolver checks claims perms then returns None (no queryset)."""
        response = self.query(
            """
            query {
                claimAttachments { totalCount }
            }
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.authorized_token}"},
        )
        content = json.loads(response.content)
        self.assertNotIn("errors", content, content.get("errors"))
        self.assertIsNone(content["data"]["claimAttachments"])

    # --- Permission mismatch: officers vs claims constants ---

    @override_settings(ROW_SECURITY=True)
    @mock.patch.object(ClaimConfig, "gql_query_claim_officers_perms", ["999001"])
    def test_fsp_from_claim_uses_officers_perm_not_claims_perm(self):
        chf_id = self.test_insuree.chf_id
        response = self.query(
            f"""
            query {{
                fspFromClaim(
                    insureeCode: "{chf_id}",
                    dateClaimed: "2020-01-01"
                ) {{ id }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.claims_only_token}"},
        )
        self._assert_graphql_unauthorized(response)

    @override_settings(ROW_SECURITY=True)
    @mock.patch.object(ClaimConfig, "gql_query_claim_officers_perms", ["999001"])
    def test_claim_with_same_diagnosis_uses_officers_perm_not_claims_perm(self):
        chf_id = self.test_insuree.chf_id
        icd_code = self.test_claim.icd.code
        response = self.query(
            f"""
            query {{
                claimWithSameDiagnosis(icd: "{icd_code}", chfid: "{chf_id}") {{
                    totalCount
                }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.claims_only_token}"},
        )
        self._assert_graphql_unauthorized(response)

    def test_default_empty_claim_officers_perms_allows_fsp_without_officers_rights(self):
        """Default gql_query_claim_officers_perms is []; has_perms([]) is vacuously true."""
        self.assertEqual(ClaimConfig.gql_query_claim_officers_perms, [])
        chf_id = self.test_insuree.chf_id
        response = self.query(
            f"""
            query {{
                fspFromClaim(
                    insureeCode: "{chf_id}",
                    dateClaimed: "2020-01-01"
                ) {{ id }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.claims_only_token}"},
        )
        content = json.loads(response.content)
        self.assertNotIn("unauthorized", _errors_text(content))

    def test_fsp_and_same_diagnosis_resolvers_use_claim_officers_perm_constant(self):
        import inspect

        fsp_source = inspect.getsource(claim_schema.Query.resolve_fsp_from_claim)
        same_dx_source = inspect.getsource(
            claim_schema.Query.resolve_claim_with_same_diagnosis
        )
        self.assertIn("gql_query_claim_officers_perms", fsp_source)
        self.assertIn("gql_query_claim_officers_perms", same_dx_source)
        self.assertNotIn("gql_query_claims_perms", fsp_source)
        self.assertNotIn("gql_query_claims_perms", same_dx_source)

    # --- Unauthorized GraphQL mutations ---

    def test_unauthorized_create_claim_denied(self):
        response = self.query(
            f"""
            mutation {{
                createClaim(input: {{
                    clientMutationId: "wo003-create-denied"
                    clientMutationLabel: "WO003 denied create"
                    code: "wo003-denied"
                    autogenerate: false
                    insureeId: {self.test_insuree.id}
                    icdId: {self.test_icd.id}
                    healthFacilityId: {self.test_claim.health_facility_id}
                    adminId: {self.test_claim.claim_admin_id}
                    dateFrom: "2020-01-01"
                    dateClaimed: "2020-01-01"
                    visitType: "O"
                    feedbackStatus: 1
                    reviewStatus: 1
                    jsonExt: "{{}}"
                    services: []
                    items: []
                }}) {{
                    clientMutationId
                }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)

    def test_unauthorized_submit_claims_denied(self):
        response = self.query(
            f"""
            mutation {{
                submitClaims(input: {{
                    clientMutationId: "wo003-submit-denied"
                    clientMutationLabel: "WO003 denied submit"
                    uuids: ["{self.test_claim.uuid}"]
                }}) {{
                    clientMutationId
                }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)

    def test_unauthorized_process_claims_denied(self):
        response = self.query(
            f"""
            mutation {{
                processClaims(input: {{
                    clientMutationId: "wo003-process-denied"
                    clientMutationLabel: "WO003 denied process"
                    uuids: ["{self.test_claim.uuid}"]
                }}) {{
                    clientMutationId
                }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.unauthorized_token}"},
        )
        self._assert_graphql_unauthorized(response)


class ClaimRestPermissionCharacterizationTest(APITestCase):
    """REST /claim/print/ and /claim/attach/ permission behavior."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.authorized_user = create_test_interactive_user(username="wo003-rest-auth")
        cls.authorized_context = BaseTestContext(user=cls.authorized_user)
        cls.authorized_token = cls.authorized_context.get_jwt()

        no_claim_role = create_test_role(
            perm_names=[],
            name=f"WO003RestNoClaimPerms-{uuid4().hex[:8]}",
        )
        cls.unauthorized_user = create_test_interactive_user(
            username="wo003-rest-unauth",
            roles=[no_claim_role.id],
        )
        cls.unauthorized_context = BaseTestContext(user=cls.unauthorized_user)
        cls.unauthorized_token = cls.unauthorized_context.get_jwt()

        cls.test_claim = create_test_claim()
        cls._ensure_attachment()

    @classmethod
    def _ensure_attachment(cls):
        att_type, _ = ClaimAttachmentType.objects.get_or_create(
            id=1,
            defaults={
                "claim_attachment_type": "default",
                "claim_general_type": GeneralClaimAttachmentType.FILE,
            },
        )
        doc = base64.b64encode(b"wo003-test-doc").decode("ascii")
        cls.attachment = ClaimAttachment.objects.create(
            claim=cls.test_claim,
            general_type=GeneralClaimAttachmentType.FILE,
            predefined_type=att_type,
            filename="wo003.txt",
            mime="text/plain",
            document=doc,
            module="claim",
        )

    def test_rest_print_unauthorized(self):
        url = f"/{settings.SITE_ROOT()}claim/print/?uuid={self.test_claim.uuid}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.unauthorized_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rest_print_authorized(self):
        url = f"/{settings.SITE_ROOT()}claim/print/?uuid={self.test_claim.uuid}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.authorized_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rest_attach_unauthorized(self):
        url = f"/{settings.SITE_ROOT()}claim/attach/?id={self.attachment.id}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.unauthorized_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_rest_attach_authorized(self):
        url = f"/{settings.SITE_ROOT()}claim/attach/?id={self.attachment.id}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.authorized_token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
