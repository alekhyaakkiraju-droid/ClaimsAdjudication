"""
WO-025: Batch claim processing optimization tests.
"""

from unittest import mock
from uuid import uuid4

from django.test import TestCase

from claim.batch_processing import (
    BatchPolicyCache,
    claim_has_process_prefetch,
    claim_process_queryset,
    load_claims_for_processing,
    missing_processing_uuids,
)
from claim.models import Claim
from claim.services import process_claims_batch
from claim.test_helpers import (
    DummyUser,
    create_test_claim,
    create_test_claimitem,
    create_test_claimservice,
    delete_claim_with_itemsvc_dedrem_and_history,
    mark_test_claim_as_processed,
)
from core.test_helpers import create_test_interactive_user
from medical.test_helpers import create_test_item, create_test_service


class BatchProcessingPrefetchTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo025-prefetch")

    def test_load_claims_for_processing_preserves_uuid_order(self):
        claim_a = create_test_claim(custom_props={"code": f"WO025-A-{uuid4().hex[:6]}"})
        claim_b = create_test_claim(custom_props={"code": f"WO025-B-{uuid4().hex[:6]}"})
        try:
            ordered = load_claims_for_processing([str(claim_b.uuid), str(claim_a.uuid)])
            self.assertEqual([c.id for c in ordered], [claim_b.id, claim_a.id])
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(claim_a)
            delete_claim_with_itemsvc_dedrem_and_history(claim_b)

    def test_claim_process_queryset_prefetches_relations(self):
        claim = create_test_claim(custom_props={"code": f"WO025-PF-{uuid4().hex[:6]}"})
        item = create_test_item("B")
        service = create_test_service("B")
        create_test_claimitem(
            claim,
            custom_props={"item": item, "qty_provided": 1, "price_asked": 10},
        )
        create_test_claimservice(
            claim,
            custom_props={"service": service, "qty_provided": 1, "price_asked": 20},
        )
        try:
            loaded = claim_process_queryset().get(id=claim.id)
            self.assertTrue(claim_has_process_prefetch(loaded))
            with self.assertNumQueries(0):
                _ = loaded.health_facility.code
                _ = loaded.insuree.id
                _ = list(loaded.items.all())
                _ = list(loaded.services.all())
                _ = loaded.icd_id
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_missing_processing_uuids(self):
        claim = create_test_claim(custom_props={"code": f"WO025-M-{uuid4().hex[:6]}"})
        missing = uuid4()
        try:
            loaded = load_claims_for_processing([str(claim.uuid), str(missing)])
            self.assertEqual(missing_processing_uuids([str(claim.uuid), str(missing)], loaded), [str(missing)])
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(claim)


class BatchPolicyCacheTest(TestCase):
    def test_batch_policy_cache_queries_once_per_insuree(self):
        claim_a = create_test_claim(custom_props={"code": f"WO025-PC-A-{uuid4().hex[:6]}"})
        claim_b = create_test_claim(
            custom_props={
                "code": f"WO025-PC-B-{uuid4().hex[:6]}",
                "insuree": claim_a.insuree,
            }
        )
        try:
            with mock.patch(
                "claim.batch_processing.get_valid_policies_qs", return_value=[]
            ) as mock_policies:
                cache = BatchPolicyCache([claim_a, claim_b])
                cache.policies_for(claim_a)
                cache.policies_for(claim_b)
            mock_policies.assert_called_once()
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(claim_a)
            delete_claim_with_itemsvc_dedrem_and_history(claim_b)


class ProcessClaimsBatchTest(TestCase):
    def test_process_claims_batch_delegates_to_processing_claim(self):
        claim = create_test_claim(custom_props={"code": f"WO025-BATCH-{uuid4().hex[:6]}"})
        mark_test_claim_as_processed(claim, status=Claim.STATUS_CHECKED)
        user = DummyUser()
        try:
            with mock.patch("claim.services.processing.processing_claim", return_value=[]) as mock_process:
                process_claims_batch([str(claim.uuid)], user)
            mock_process.assert_called_once()
            _, kwargs = mock_process.call_args
            self.assertTrue(kwargs.get("is_process"))
            self.assertIn("policies", kwargs)
        finally:
            delete_claim_with_itemsvc_dedrem_and_history(claim)
