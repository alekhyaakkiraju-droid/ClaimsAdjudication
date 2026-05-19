"""
Characterization tests for claim lifecycle workflows (WO-002).

These tests document current behavior of status transitions, approved amounts,
quantity overshoot validation, additional diagnosis limits, and save_history.
"""

from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from claim.apps import ClaimConfig
from claim.models import Claim, ClaimDetail, ClaimItem, ClaimService
from claim.services import (
    processing_claim,
    set_claim_submitted,
    validate_claim_data,
    validate_number_of_additional_diagnoses,
)
from claim.test_helpers import (
    DummyUser,
    create_test_claim,
    create_test_claimitem,
    create_test_claimservice,
    delete_claim_with_itemsvc_dedrem_and_history,
    mark_test_claim_as_processed,
)
from claim.utils import approved_amount, item_create_hook, process_child_relation
from core.test_helpers import create_test_interactive_user
from insuree.test_helpers import create_test_insuree
from medical.test_helpers import create_test_diagnosis, create_test_item, create_test_service
from policy.test_helpers import create_test_policy2
from product.test_helpers import create_test_product


class ClaimWorkflowCharacterizationTest(TestCase):
    """Documents current claim workflow behavior before refactoring."""

    @classmethod
    def setUpTestData(cls):
        cls.product = create_test_product("WO002")
        cls.user = create_test_interactive_user()
        cls.dummy_user = DummyUser()

    def _claim_with_provisions(self, **claim_props):
        insuree = create_test_insuree()
        create_test_policy2(self.product, insuree, link=True)
        claim = create_test_claim(
            {"insuree_id": insuree.id, **claim_props},
            product=self.product,
        )
        item = create_test_claimitem(
            claim,
            "D",
            custom_props={"qty_provided": 2, "price_asked": 100},
            product=self.product,
        )
        service = create_test_claimservice(
            claim,
            "V",
            custom_props={"qty_provided": 1, "price_asked": 50},
            product=self.product,
        )
        return claim, item, service

    # --- Status transitions ---

    def test_entered_claim_starts_with_status_entered(self):
        claim, _, _ = self._claim_with_provisions()
        self.assertEqual(claim.status, Claim.STATUS_ENTERED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_set_claim_submitted_moves_checked_when_no_errors(self):
        claim, _, _ = self._claim_with_provisions()
        mark_test_claim_as_processed(claim, status=Claim.STATUS_ENTERED)
        claim.status = Claim.STATUS_ENTERED
        claim.save()

        result_errors = set_claim_submitted(claim, [], self.dummy_user)
        claim.refresh_from_db()

        self.assertEqual(result_errors, [])
        self.assertEqual(claim.status, Claim.STATUS_CHECKED)
        self.assertIsNotNone(claim.submit_stamp)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_set_claim_submitted_moves_rejected_when_errors(self):
        claim, _, _ = self._claim_with_provisions()
        errors = [{"message": "validation failed"}]

        result_errors = set_claim_submitted(claim, errors, self.dummy_user)
        claim.refresh_from_db()

        self.assertEqual(result_errors, [])
        self.assertEqual(claim.status, Claim.STATUS_REJECTED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_processing_checked_claim_valuates_without_relative_prices(self):
        claim, item, service = self._claim_with_provisions()
        mark_test_claim_as_processed(claim, status=Claim.STATUS_CHECKED)

        errors = processing_claim(claim, self.user, is_process=True)
        claim.refresh_from_db()

        self.assertEqual(errors, [])
        self.assertEqual(claim.status, Claim.STATUS_VALUATED)
        self.assertEqual(claim.approved, approved_amount(claim))
        self.assertIsNotNone(claim.process_stamp)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_set_claim_processed_or_valuated_rejects_on_errors(self):
        from claim.services import set_claim_processed_or_valuated

        claim, _, _ = self._claim_with_provisions()
        mark_test_claim_as_processed(claim, status=Claim.STATUS_CHECKED)
        errors = [{"message": "forced failure"}]

        set_claim_processed_or_valuated(claim, errors, self.user)
        claim.refresh_from_db()

        self.assertEqual(claim.status, Claim.STATUS_REJECTED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_validate_claim_data_rejects_edit_when_not_entered_or_checked(self):
        claim, _, _ = self._claim_with_provisions()
        claim.status = Claim.STATUS_VALUATED
        claim.save()

        with self.assertRaises(ValidationError):
            validate_claim_data(
                {"code": claim.code, "uuid": str(claim.uuid), "services": []},
                self.user,
            )
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    @mock.patch("claim.services.ClaimSubmitService._validate_user_hf")
    def test_submit_claim_service_checked_on_success(self, _mock_hf):
        from claim.services import ClaimSubmitService

        claim, _, _ = self._claim_with_provisions()
        _mock_hf.return_value = None
        service = ClaimSubmitService(user=self.user)
        submitted, errors = service.submit_claim(claim, rule_engine_validation=False)

        self.assertEqual(errors, [])
        self.assertEqual(submitted.status, Claim.STATUS_CHECKED)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    # --- approved_amount ---

    def test_approved_amount_sums_passed_item_and_service_lines(self):
        claim, item, service = self._claim_with_provisions()
        item.qty_approved = 2
        item.price_approved = Decimal("40")
        item.status = ClaimDetail.STATUS_PASSED
        item.save()
        service.qty_approved = 1
        service.price_approved = Decimal("30")
        service.status = ClaimDetail.STATUS_PASSED
        service.save()

        amount = approved_amount(claim)

        self.assertEqual(amount, Decimal("110"))  # 2*40 + 1*30
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_approved_amount_zero_when_claim_rejected(self):
        claim, item, service = self._claim_with_provisions()
        item.qty_approved = 2
        item.price_approved = Decimal("40")
        item.save()
        claim.status = Claim.STATUS_REJECTED
        claim.save()

        self.assertEqual(approved_amount(claim), 0)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_checked_claim_sets_approved_from_approved_amount(self):
        claim, item, service = self._claim_with_provisions()
        item.qty_approved = 1
        item.price_approved = Decimal("25")
        item.save()

        set_claim_submitted(claim, [], self.dummy_user)
        claim.refresh_from_db()

        self.assertEqual(claim.status, Claim.STATUS_CHECKED)
        self.assertEqual(claim.approved, approved_amount(claim))
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    # --- Quantity overshoot ---

    def test_process_child_relation_rejects_item_quantity_above_maximum(self):
        claim, _, _ = self._claim_with_provisions()
        item = create_test_item("D", custom_props={"maximum_amount": 3})
        data = [
            {
                "item_id": item.id,
                "qty_provided": 10,
                "price_asked": 100,
            }
        ]

        with self.assertRaises(ValidationError):
            process_child_relation(
                self.dummy_user, data, claim.id, claim.items, item_create_hook
            )
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_process_child_relation_rejects_service_quantity_above_maximum(self):
        from claim.utils import service_create_hook

        claim, _, _ = self._claim_with_provisions()
        service = create_test_service("V", custom_props={"maximum_amount": 2})
        data = [
            {
                "service_id": service.id,
                "qty_provided": 5,
                "price_asked": 100,
            }
        ]

        with self.assertRaises(ValidationError):
            process_child_relation(
                self.dummy_user, data, claim.id, claim.services, service_create_hook
            )
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_process_child_relation_allows_quantity_at_maximum(self):
        claim, _, _ = self._claim_with_provisions()
        item = create_test_item("D", custom_props={"maximum_amount": 5})
        data = [
            {
                "item_id": item.id,
                "qty_provided": 5,
                "price_asked": 100,
            }
        ]

        claimed = process_child_relation(
            self.dummy_user, data, claim.id, claim.items, item_create_hook
        )
        self.assertEqual(claimed, 500)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    # --- Additional diagnosis limits ---

    def test_validate_number_of_additional_diagnoses_within_limit(self):
        allowed = ClaimConfig.additional_diagnosis_number_allowed
        data = {f"icd_{i}_id": i + 1 for i in range(1, allowed + 1)}
        data["icd_id"] = 99

        self.assertTrue(validate_number_of_additional_diagnoses(data))

    def test_validate_number_of_additional_diagnoses_over_limit(self):
        allowed = ClaimConfig.additional_diagnosis_number_allowed
        data = {f"icd_{i}_id": i + 1 for i in range(1, allowed + 2)}
        data["icd_id"] = 99

        self.assertFalse(validate_number_of_additional_diagnoses(data))

    def test_validate_claim_data_rejects_too_many_additional_diagnoses(self):
        claim, _, _ = self._claim_with_provisions()
        allowed = ClaimConfig.additional_diagnosis_number_allowed
        extra_icds = [
            create_test_diagnosis(custom_props={"code": f"WO2ICD{i}"})
            for i in range(allowed + 1)
        ]
        data = {
            "code": claim.code,
            "uuid": str(claim.uuid),
            "services": [],
            "icd_id": claim.icd_id,
        }
        for idx, icd in enumerate(extra_icds, start=1):
            data[f"icd_{idx}_id"] = icd.id

        with self.assertRaises(ValidationError):
            validate_claim_data(data, self.user)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    # --- save_history ---

    def test_save_history_preserves_child_items_and_services_on_previous_claim(self):
        claim, item, service = self._claim_with_provisions()
        original_item_id = item.item_id
        original_service_id = service.service_id
        original_item_qty = item.qty_provided
        original_service_qty = service.qty_provided

        prev_claim_id = claim.save_history()
        self.assertIsNotNone(prev_claim_id)

        prev_claim = Claim.objects.get(id=prev_claim_id)
        self.assertIsNotNone(prev_claim.validity_to)

        prev_items = ClaimItem.objects.filter(claim_id=prev_claim_id)
        prev_services = ClaimService.objects.filter(claim_id=prev_claim_id)
        self.assertEqual(prev_items.count(), 1)
        self.assertEqual(prev_services.count(), 1)

        historized_item = prev_items.first()
        historized_service = prev_services.first()
        self.assertEqual(historized_item.item_id, original_item_id)
        self.assertEqual(historized_service.service_id, original_service_id)
        self.assertEqual(historized_item.qty_provided, original_item_qty)
        self.assertEqual(historized_service.qty_provided, original_service_qty)
        self.assertIsNotNone(historized_item.validity_to)
        self.assertIsNotNone(historized_service.validity_to)

        current_items = claim.items.filter(validity_to__isnull=True)
        current_services = claim.services.filter(validity_to__isnull=True)
        self.assertEqual(current_items.count(), 1)
        self.assertEqual(current_services.count(), 1)

        delete_claim_with_itemsvc_dedrem_and_history(claim)
