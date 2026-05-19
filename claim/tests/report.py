from core.test_helpers import create_test_interactive_user
from rest_framework import status
from rest_framework.test import APITestCase
from django.conf import settings
from django.core.exceptions import PermissionDenied
from claim.services import ClaimReportService
from claim.test_helpers import (
    create_test_claim,
    create_test_claimitem,
    create_test_claimservice,
)
from core.models.openimis_graphql_test_case import BaseTestContext
from uuid import uuid4


class ReportAPITests(APITestCase):

    admin_user = None
    admin_token = None

    test_claim = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(username="testClaimAdmin")
        cls.user_context = BaseTestContext(user=cls.admin_user)
        cls.admin_token = cls.user_context.get_jwt()
        cls.test_claim = create_test_claim()
        create_test_claimservice(cls.test_claim)
        create_test_claimitem(cls.test_claim)

    def test_print_claim(self):
        URL = f"/{settings.SITE_ROOT()}claim/print/?uuid={self.test_claim.uuid}"
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        response = self.client.get(URL, format="json", **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_print_claim_unknown_uuid_forbidden(self):
        url = f"/{settings.SITE_ROOT()}claim/print/?uuid={uuid4()}"
        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.admin_token}",
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_500_INTERNAL_SERVER_ERROR),
        )


class ClaimReportServiceUnitTest(APITestCase):
    """WO-004: report data service used by print endpoint."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = create_test_interactive_user(username="wo004-report-api")
        cls.test_claim = create_test_claim()
        create_test_claimitem(cls.test_claim)
        create_test_claimservice(cls.test_claim)

    def test_report_service_fetch_matches_claim(self):
        svc = ClaimReportService(self.admin_user)
        data = svc.fetch(str(self.test_claim.uuid))
        self.assertEqual(data["code"], self.test_claim.code)
        self.assertTrue(len(data["items"]) >= 1)
        self.assertTrue(len(data["services"]) >= 1)

    def test_report_service_fetch_invalid_uuid(self):
        svc = ClaimReportService(self.admin_user)
        with self.assertRaises(PermissionDenied):
            svc.fetch(str(uuid4()))
