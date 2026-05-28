"""
WO-018: Claim read-path eager loading and query-count tests.
"""

import json
import string
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from claim.models import Claim, ClaimAttachment, GeneralClaimAttachmentType
from claim.read_queryset import claim_has_read_prefetch, claim_read_queryset
from claim.test_helpers import (
    create_test_claim,
    create_test_claimitem,
    create_test_claimservice,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.models.openimis_graphql_test_case import BaseTestContext, openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token
from medical.test_helpers import create_test_item, create_test_service


def _create_claim_with_children(*, claim_code: str, item_service_code: str):
    claim = create_test_claim(custom_props={"code": claim_code})
    item = create_test_item(item_service_code)
    service = create_test_service(item_service_code)
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
    ClaimAttachment.objects.create(
        claim=claim,
        general_type=GeneralClaimAttachmentType.FILE,
        title="WO018 attachment",
        filename="doc.pdf",
        mime="application/pdf",
        validity_from=claim.validity_from,
    )
    return claim


class ClaimReadQuerysetPrefetchTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo018-prefetch")

    def test_claim_read_queryset_prefetches_nested_relations(self):
        claim = _create_claim_with_children(
            claim_code=f"WO018-PF-{uuid4().hex[:8]}",
            item_service_code="P",
        )
        loaded = claim_read_queryset(Claim.objects.filter(id=claim.id)).first()

        self.assertTrue(claim_has_read_prefetch(loaded))
        with self.assertNumQueries(0):
            items = list(loaded.items.all())
            services = list(loaded.services.all())
            attachments = list(loaded.attachments.all())
            hf_code = loaded.health_facility.code
            insuree_id = loaded.insuree.id

        self.assertEqual(len(items), 1)
        self.assertEqual(len(services), 1)
        self.assertEqual(len(attachments), 1)
        self.assertIsNotNone(hf_code)
        self.assertIsNotNone(insuree_id)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_claim_read_queryset_includes_select_and_prefetch_lookups(self):
        qs = claim_read_queryset()
        self.assertIn("health_facility", qs.query.select_related)
        self.assertIn("insuree", qs.query.select_related)
        self.assertTrue(qs._prefetch_related_lookups)


class ClaimListQueryCountTest(openIMISGraphQLTestCase):
    """GraphQL claims list must not scale query count linearly with result size."""

    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo018-querycount")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.claims = []
        for idx in range(10):
            claim = _create_claim_with_children(
                claim_code=f"WO018-Q{idx}-{uuid4().hex[:8]}",
                item_service_code=string.ascii_uppercase[idx],
            )
            cls.claims.append(claim)

    @classmethod
    def tearDownClass(cls):
        for claim in cls.claims:
            delete_claim_with_itemsvc_dedrem_and_history(claim)
        super().tearDownClass()

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    _CLAIMS_LIST_QUERY = """
        query($first: Int!) {
            claims(first: $first, orderBy: ["-dateClaimed"]) {
                edges {
                    node {
                        uuid
                        code
                        attachmentsCount
                        healthFacility { code }
                        insuree { chfId }
                        items { priceAsked qtyProvided }
                        services { priceAsked qtyProvided }
                    }
                }
            }
        }
    """

    def _query_count_for_first(self, first: int) -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = self.query(
                self._CLAIMS_LIST_QUERY,
                variables={"first": first},
                headers=self._headers(),
            )
        self.assertResponseNoErrors(response)
        return len(ctx.captured_queries)

    def test_claim_list_query_count_is_sublinear(self):
        queries_for_five = self._query_count_for_first(5)
        queries_for_ten = self._query_count_for_first(10)
        # Without eager loading, doubling claims roughly doubles per-claim queries.
        self.assertLessEqual(
            queries_for_ten - queries_for_five,
            3,
            msg=(
                f"Query count grew too much: {queries_for_five} for 5 claims vs "
                f"{queries_for_ten} for 10 claims"
            ),
        )

    def test_nested_claim_fields_return_correct_data(self):
        target = self.claims[0]
        response = self.query(
            """
            query($uuid: UUID!) {
                claim(uuid: $uuid) {
                    uuid
                    code
                    attachmentsCount
                    items { priceAsked qtyProvided }
                    services { priceAsked qtyProvided }
                }
            }
            """,
            variables={"uuid": str(target.uuid)},
            headers=self._headers(),
        )
        self.assertResponseNoErrors(response)
        data = json.loads(response.content)["data"]["claim"]
        self.assertEqual(data["code"], target.code)
        self.assertEqual(data["attachmentsCount"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(len(data["services"]), 1)
