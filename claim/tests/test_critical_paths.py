"""
Critical path integration tests (WO-004).

Expands automated coverage for submission, query, attachment, validation edge cases,
and report data fetchers beyond characterization suites (WO-002/003).
"""

import base64
import json
from datetime import date, timedelta
from unittest import mock
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from claim.models import (
    Claim,
    ClaimAttachment,
    ClaimAttachmentType,
    GeneralClaimAttachmentType,
)
from claim.services import (
    ClaimReportService,
    ClaimSubmitService,
    check_unique_claim_code,
)
from claim.test_helpers import (
    create_test_claim,
    create_test_claim_admin,
    create_test_claimitem,
    create_test_claimservice,
    delete_claim_with_itemsvc_dedrem_and_history,
    mark_test_claim_as_processed,
)
from claim.validations import fetch_policies, REJECTION_REASON_NO_COVERAGE
from core.models.openimis_graphql_test_case import BaseTestContext, openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token
from insuree.test_helpers import create_test_insuree
from medical.test_helpers import create_test_diagnosis, create_test_item, create_test_service
from policy.test_helpers import create_test_policy2
from product.test_helpers import create_test_product


class ClaimSubmissionQueryIntegrationTest(openIMISGraphQLTestCase):
    """End-to-end create → query → submit using GraphQL interfaces."""

    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo004-integration")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.product = create_test_product("WO004")
        cls.insuree = create_test_insuree()
        create_test_policy2(cls.product, cls.insuree, link=True)
        cls.icd = create_test_diagnosis()
        cls.item = create_test_item("D")
        cls.service = create_test_service("V")
        cls.claim_admin = create_test_claim_admin()
        cls.hf_id = cls.claim_admin.health_facility_id
        cls.claim_code = f"WO004-{uuid4().hex[:8]}"

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_create_query_and_submit_claim(self):
        mutation_id = str(uuid4())

        create_resp = self.query(
            f"""
            mutation {{
                createClaim(input: {{
                    clientMutationId: "{mutation_id}"
                    clientMutationLabel: "WO004 create"
                    code: "{self.claim_code}"
                    autogenerate: false
                    insureeId: {self.insuree.id}
                    adminId: {self.claim_admin.id}
                    dateFrom: "{(date.today() - timedelta(days=3)).isoformat()}"
                    dateClaimed: "{(date.today() - timedelta(days=1)).isoformat()}"
                    icdId: {self.icd.id}
                    jsonExt: "{{}}"
                    feedbackStatus: 1
                    reviewStatus: 1
                    healthFacilityId: {self.hf_id}
                    visitType: "O"
                    preAuthorization: false
                    patientCondition: "R"
                    referralCode: "REF-WO004"
                    items: [{{
                        itemId: {self.item.id}
                        priceAsked: "100.00"
                        qtyProvided: "1.00"
                        status: 1
                    }}]
                    services: [{{
                        serviceId: {self.service.id}
                        priceAsked: "50.00"
                        qtyProvided: "1.00"
                        status: 1
                        serviceItemSet: []
                        serviceServiceSet: []
                    }}]
                }}) {{
                    clientMutationId
                    internalId
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(create_resp)
        claim = Claim.objects.filter(code=self.claim_code).first()
        self.assertIsNotNone(claim)
        self.assertEqual(claim.status, Claim.STATUS_ENTERED)

        query_resp = self.query(
            f"""
            query {{
                claim(uuid: "{claim.uuid}") {{
                    uuid
                    code
                    status
                    claimed
                    items {{ priceAsked qtyProvided }}
                    services {{ priceAsked qtyProvided }}
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(query_resp)
        data = json.loads(query_resp.content)["data"]["claim"]
        self.assertEqual(data["code"], self.claim_code)

        list_resp = self.query(
            """
            query {
                claims(first: 5, orderBy: ["-dateClaimed"]) {
                    totalCount
                    edges { node { uuid code } }
                }
            }
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(list_resp)

        mark_test_claim_as_processed(claim, status=Claim.STATUS_ENTERED)
        submit_resp = self.query(
            f"""
            mutation {{
                submitClaims(input: {{
                    clientMutationId: "{uuid4()}"
                    clientMutationLabel: "WO004 submit"
                    uuids: ["{claim.uuid}"]
                }}) {{
                    clientMutationId
                }}
            }}
            """,
            headers=self._headers(),
        )
        self.assertResponseNoErrors(submit_resp)
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.STATUS_CHECKED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)


class ClaimReportServiceTest(TestCase):
    """Report data fetcher for print / claim_claim report."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="wo004-report")
        cls.claim = create_test_claim()
        create_test_claimitem(cls.claim)
        create_test_claimservice(cls.claim)

    def test_fetch_returns_claim_report_fields(self):
        svc = ClaimReportService(self.user)
        data = svc.fetch(str(self.claim.uuid))

        self.assertEqual(data["code"], self.claim.code)
        self.assertIn("healthFacility", data)
        self.assertIn("insuree", data)
        self.assertIn("services", data)
        self.assertIn("items", data)
        self.assertGreaterEqual(len(data["items"]), 1)
        self.assertGreaterEqual(len(data["services"]), 1)

    def test_fetch_unknown_uuid_raises_permission_denied(self):
        svc = ClaimReportService(self.user)
        with self.assertRaises(PermissionDenied):
            svc.fetch(str(uuid4()))


class ClaimAttachmentCriticalPathTest(APITestCase):
    """Attachment download paths beyond permission characterization."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo004-attach")
        cls.context = BaseTestContext(user=cls.user)
        cls.token = cls.context.get_jwt()
        cls.claim = create_test_claim()
        att_type, _ = ClaimAttachmentType.objects.get_or_create(
            id=2,
            defaults={
                "claim_attachment_type": "wo004",
                "claim_general_type": GeneralClaimAttachmentType.FILE,
            },
        )
        cls.attachment = ClaimAttachment.objects.create(
            claim=cls.claim,
            general_type=GeneralClaimAttachmentType.FILE,
            predefined_type=att_type,
            filename="wo004.txt",
            mime="text/plain",
            document=base64.b64encode(b"wo004-attachment-bytes").decode("ascii"),
            module="claim",
        )

    def test_attach_returns_document_content(self):
        url = f"/{settings.SITE_ROOT()}claim/attach/?id={self.attachment.id}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(b"wo004-attachment-bytes", response.content)

    def test_attach_missing_document_returns_404(self):
        att_type, _ = ClaimAttachmentType.objects.get_or_create(
            id=3,
            defaults={
                "claim_attachment_type": "wo004-empty",
                "claim_general_type": GeneralClaimAttachmentType.FILE,
            },
        )
        empty = ClaimAttachment.objects.create(
            claim=self.claim,
            general_type=GeneralClaimAttachmentType.FILE,
            predefined_type=att_type,
            filename="empty.txt",
            mime="text/plain",
            document=None,
            module="claim",
        )
        url = f"/{settings.SITE_ROOT()}claim/attach/?id={empty.id}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ClaimValidationEdgeCaseTest(openIMISGraphQLTestCase):
    """Validation edge cases on critical submission paths."""

    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo004-validation")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.existing_claim = create_test_claim()

    def test_check_unique_claim_code_detects_duplicate(self):
        errors = check_unique_claim_code(self.existing_claim.code)
        self.assertTrue(len(errors) > 0)
        self.assertIn("already exists", errors[0]["message"])

    def test_check_unique_claim_code_allows_new_code(self):
        errors = check_unique_claim_code(f"UNIQUE-{uuid4().hex}")
        self.assertEqual(errors, [])

    def test_validate_claim_code_query_unique(self):
        unique = f"WO004-UNQ-{uuid4().hex[:8]}"
        response = self.query(
            f"""
            query {{
                validateClaimCode(claimCode: "{unique}")
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        self.assertResponseNoErrors(response)
        self.assertTrue(json.loads(response.content)["data"]["validateClaimCode"])

    def test_validate_claim_code_query_duplicate(self):
        response = self.query(
            f"""
            query {{
                validateClaimCode(claimCode: "{self.existing_claim.code}")
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        self.assertResponseNoErrors(response)
        self.assertFalse(json.loads(response.content)["data"]["validateClaimCode"])

    def test_fetch_policies_rejects_claim_without_coverage(self):
        claim = create_test_claim()
        claim.insuree = create_test_insuree()
        claim.save()
        target = date.today()
        result = fetch_policies(claim, target, policies=[])
        self.assertIsNone(result)
        claim.refresh_from_db()
        self.assertEqual(claim.status, Claim.STATUS_REJECTED)
        self.assertEqual(claim.rejection_reason, REJECTION_REASON_NO_COVERAGE)
        delete_claim_with_itemsvc_dedrem_and_history(claim)


class ClaimServiceLayerIntegrationTest(TestCase):
    """Service-layer paths complementing GraphQL integration tests."""

    @classmethod
    def setUpTestData(cls):
        cls.user = create_test_interactive_user(username="wo004-service")
        cls.product = create_test_product("WO004SVC")
        cls.insuree = create_test_insuree()
        create_test_policy2(cls.product, cls.insuree, link=True)

    @mock.patch("claim.services.ClaimSubmitService._validate_user_hf")
    def test_submit_claim_service_checked_path(self, _mock_hf):
        claim = create_test_claim(
            {"insuree_id": self.insuree.id},
            product=self.product,
        )
        create_test_claimitem(claim, "D", product=self.product)
        _mock_hf.return_value = None
        service = ClaimSubmitService(user=self.user)
        submitted, errors = service.submit_claim(claim, rule_engine_validation=False)
        self.assertEqual(errors, [])
        self.assertEqual(submitted.status, Claim.STATUS_CHECKED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)
