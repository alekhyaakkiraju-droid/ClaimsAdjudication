"""
WO-016: Bulk claim item/service write path tests.
"""

from unittest import mock

from django.test import TestCase

import claim.utils as claim_utils
from claim.models import ClaimItem, ClaimService, ClaimServiceItem, ClaimServiceService
from claim.test_helpers import create_test_claim, delete_claim_with_itemsvc_dedrem_and_history
from claim.utils import (
    calcul_amount_service,
    item_create_hook,
    process_child_relation,
    process_items_relations,
    process_services_relations,
)
from core.test_helpers import create_test_interactive_user
from medical.test_helpers import create_test_item, create_test_service


class BulkClaimWritesTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo016-bulk")

    def test_process_items_uses_bulk_create(self):
        claim = create_test_claim(custom_props={"code": "WO016-ITEMS"})
        item = create_test_item("I")
        data = [
            {
                "item_id": item.id,
                "qty_provided": 2,
                "price_asked": 50,
            },
            {
                "item_id": item.id,
                "qty_provided": 1,
                "price_asked": 10,
            },
        ]
        with mock.patch.object(
            claim_utils.ClaimItem.objects,
            "bulk_create",
            wraps=ClaimItem.objects.bulk_create,
        ) as bulk_create:
            claimed = process_items_relations(self.user, claim, data)
        self.assertEqual(claimed, 110)
        self.assertEqual(claim.items.filter(legacy_id__isnull=True).count(), 2)
        bulk_create.assert_called_once()
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_process_services_uses_bulk_create_for_service_and_sub_elements(self):
        claim = create_test_claim(custom_props={"code": "WO016-SVC"})
        sub_item = create_test_item("J")
        sub_service = create_test_service("K")
        service = create_test_service("L")
        data = [
            {
                "service_id": service.id,
                "qty_provided": 1,
                "price_asked": 100,
                "service_item_set": [
                    {
                        "sub_item_code": sub_item.code,
                        "qty_asked": 1,
                        "qty_provided": 1,
                        "price_asked": 20,
                    }
                ],
                "service_service_set": [
                    {
                        "sub_service_code": sub_service.code,
                        "qty_asked": 1,
                        "qty_provided": 1,
                        "price_asked": 30,
                    }
                ],
            }
        ]
        expected_claimed = calcul_amount_service(data[0], True)
        with mock.patch.object(
            claim_utils.ClaimServiceItem.objects,
            "bulk_create",
            wraps=ClaimServiceItem.objects.bulk_create,
        ) as si_bulk:
            with mock.patch.object(
                claim_utils.ClaimServiceService.objects,
                "bulk_create",
                wraps=ClaimServiceService.objects.bulk_create,
            ) as ss_bulk:
                claimed = process_services_relations(self.user, claim, data)
        self.assertEqual(claimed, expected_claimed)
        self.assertEqual(claim.services.filter(legacy_id__isnull=True).count(), 1)
        self.assertEqual(
            ClaimServiceItem.objects.filter(claim_service__claim=claim).count(), 1
        )
        self.assertEqual(
            ClaimServiceService.objects.filter(claim_service__claim=claim).count(), 1
        )
        si_bulk.assert_called_once()
        ss_bulk.assert_called_once()
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_claimed_total_unchanged_with_multiple_children(self):
        claim = create_test_claim(custom_props={"code": "WO016-TOTAL"})
        item = create_test_item("T")
        data = [
            {"item_id": item.id, "qty_provided": 3, "price_asked": 40},
            {"item_id": item.id, "qty_provided": 2, "price_asked": 25},
        ]
        claimed = process_child_relation(
            self.user, data, claim.id, claim.items, item_create_hook
        )
        self.assertEqual(claimed, 170)
        delete_claim_with_itemsvc_dedrem_and_history(claim)
