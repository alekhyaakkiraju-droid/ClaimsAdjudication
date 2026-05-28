"""
WO-016: Bulk claim item write path tests.
"""

from unittest import mock

from django.test import TestCase

import claim.utils as claim_utils
from claim.models import ClaimItem
from claim.test_helpers import create_test_claim, delete_claim_with_itemsvc_dedrem_and_history
from claim.utils import (
    item_create_hook,
    process_child_relation,
    process_items_relations,
)
from core.test_helpers import create_test_interactive_user
from medical.test_helpers import create_test_item


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
