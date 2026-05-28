"""
WO-017: Submission pipeline optimization tests.
"""

from unittest import mock

from django.test import TestCase

from claim.models import Claim
from claim.services import ClaimSubmitService
from claim.submission_pipeline import claim_submission_queryset, load_claim_for_submission
from claim.test_helpers import (
    create_test_claim,
    create_test_claimitem,
    create_test_claimservice,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.test_helpers import create_test_interactive_user
from medical.test_helpers import create_test_item, create_test_service


class SubmissionPipelinePrefetchTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo017-prefetch")

    def test_load_claim_for_submission_prefetches_children(self):
        claim = create_test_claim(custom_props={"code": "WO017-PF"})
        item = create_test_item("P")
        service = create_test_service("P")
        create_test_claimitem(
            claim,
            custom_props={
                "item": item,
                "qty_provided": 1,
                "price_asked": 10,
                "validity_from": claim.validity_from,
            },
        )
        create_test_claimservice(
            claim,
            custom_props={
                "service": service,
                "qty_provided": 1,
                "price_asked": 20,
                "validity_from": claim.validity_from,
            },
        )

        loaded = load_claim_for_submission(claim)
        with self.assertNumQueries(0):
            items = list(loaded.items.all())
            services = list(loaded.services.all())
            hf_code = loaded.health_facility.code
            insuree_id = loaded.insuree.id

        self.assertEqual(len(items), 1)
        self.assertEqual(len(services), 1)
        self.assertIsNotNone(hf_code)
        self.assertIsNotNone(insuree_id)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    @mock.patch("claim.services.ClaimSubmitService._validate_user_hf")
    @mock.patch("claim.services.processing_claim", return_value=[])
    def test_enter_and_submit_skips_duplicate_hf_validation(
        self, _mock_processing, mock_validate_hf
    ):
        claim = create_test_claim(custom_props={"code": "WO017-HF", "status": Claim.STATUS_ENTERED})
        service = ClaimSubmitService(self.user)
        with mock.patch.object(
            ClaimSubmitService,
            "submit_claim",
            wraps=service.submit_claim,
        ) as submit_spy:
            service.submit_claim(claim, rule_engine_validation=False, skip_hf_validation=True)
        mock_validate_hf.assert_not_called()
        submit_spy.assert_called_once()
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_claim_submission_queryset_includes_select_related(self):
        qs = claim_submission_queryset()
        self.assertIn("health_facility", qs.query.select_related)
        self.assertTrue(qs._prefetch_related_lookups)
