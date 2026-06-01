"""
WO-028: Report query-path performance tests.
"""

import string
from datetime import datetime, timedelta
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from claim.models import Claim
from claim.reports.claim_history import claim_history_query
from claim.reports.claims_overview import claims_overview_query
from claim.reports.queryset import (
    claim_detail_report_queryset,
    claim_has_detail_report_prefetch,
    claim_has_print_report_prefetch,
    claim_operational_indicators_queryset,
    claim_print_report_queryset,
)
from claim.services import ClaimReportService
from claim.test_helpers import (
    create_test_claim,
    create_test_claimitem,
    create_test_claimservice,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.test_helpers import create_test_interactive_user
from location.models import Location
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
    return claim


class ReportQuerysetPrefetchTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo028-prefetch")

    def test_claim_detail_report_queryset_prefetches_nested_relations(self):
        claim = _create_claim_with_children(
            claim_code=f"WO028-PF-{uuid4().hex[:8]}",
            item_service_code="R",
        )
        loaded = claim_detail_report_queryset(Claim.objects.filter(id=claim.id)).first()

        self.assertTrue(claim_has_detail_report_prefetch(loaded))
        with self.assertNumQueries(0):
            items = list(loaded.items.all())
            services = list(loaded.services.all())
            hf_code = loaded.health_facility.code
            admin_name = loaded.admin.last_name
            item_code = items[0].item.code
            service_code = services[0].service.code

        self.assertEqual(len(items), 1)
        self.assertEqual(len(services), 1)
        self.assertIsNotNone(hf_code)
        self.assertIsNotNone(admin_name)
        self.assertIsNotNone(item_code)
        self.assertIsNotNone(service_code)
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_claim_print_report_queryset_prefetches_icd_and_children(self):
        claim = _create_claim_with_children(
            claim_code=f"WO028-PR-{uuid4().hex[:8]}",
            item_service_code="P",
        )
        loaded = claim_print_report_queryset(Claim.objects.filter(id=claim.id)).first()

        self.assertTrue(claim_has_print_report_prefetch(loaded))
        with self.assertNumQueries(0):
            _ = loaded.icd.code
            _ = list(loaded.items.all())
            _ = list(loaded.services.all())
        delete_claim_with_itemsvc_dedrem_and_history(claim)

    def test_claim_operational_indicators_queryset_prefetches_children(self):
        claim = _create_claim_with_children(
            claim_code=f"WO028-OP-{uuid4().hex[:8]}",
            item_service_code="O",
        )
        loaded = claim_operational_indicators_queryset(
            Claim.objects.filter(id=claim.id)
        ).first()

        with self.assertNumQueries(0):
            items = list(loaded.items.all())
            services = list(loaded.services.all())

        self.assertEqual(len(items), 1)
        self.assertEqual(len(services), 1)
        delete_claim_with_itemsvc_dedrem_and_history(claim)


class ReportQueryCountTest(TestCase):
    """Report data paths must not scale SQL queries linearly with claim count."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo028-querycount")
        cls.claims = []
        for idx in range(8):
            claim = _create_claim_with_children(
                claim_code=f"WO028-Q{idx}-{uuid4().hex[:8]}",
                item_service_code=string.ascii_uppercase[idx],
            )
            cls.claims.append(claim)

    @classmethod
    def tearDownClass(cls):
        for claim in cls.claims:
            delete_claim_with_itemsvc_dedrem_and_history(claim)
        super().tearDownClass()

    def _detail_report_query_count(self, claim_count: int) -> int:
        ids = [c.id for c in self.claims[:claim_count]]
        qs = claim_detail_report_queryset(Claim.objects.filter(id__in=ids))
        with CaptureQueriesContext(connection) as ctx:
            for claim in qs:
                _ = claim.health_facility.code
                _ = claim.insuree.chf_id
                _ = claim.admin.last_name
                for item in claim.items.all():
                    _ = item.item.code
                for service in claim.services.all():
                    _ = service.service.code
        return len(ctx.captured_queries)

    def test_detail_report_query_count_is_sublinear(self):
        queries_for_four = self._detail_report_query_count(4)
        queries_for_eight = self._detail_report_query_count(8)
        self.assertLessEqual(
            queries_for_eight - queries_for_four,
            2,
            msg=(
                f"Query count grew too much: {queries_for_four} for 4 claims vs "
                f"{queries_for_eight} for 8 claims"
            ),
        )

    def test_claim_report_service_fetch_uses_prefetch(self):
        claim = self.claims[0]
        svc = ClaimReportService(self.user)
        loaded = claim_print_report_queryset(
            Claim.objects.filter(*Claim.filter_validity())
        ).get(id=claim.id)
        with self.assertNumQueries(0):
            data_items = list(loaded.items.all())
            data_services = list(loaded.services.all())
            _ = loaded.icd.code
        self.assertEqual(len(data_items), 1)
        self.assertEqual(len(data_services), 1)

        fetched = svc.fetch(str(claim.uuid))
        self.assertEqual(fetched["code"], claim.code)
        self.assertGreaterEqual(len(fetched["items"]), 1)
        self.assertGreaterEqual(len(fetched["services"]), 1)


class ReportQueryIntegrationTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo028-integration")
        cls.claim = _create_claim_with_children(
            claim_code=f"WO028-INT-{uuid4().hex[:8]}",
            item_service_code="I",
        )

    @classmethod
    def tearDownClass(cls):
        delete_claim_with_itemsvc_dedrem_and_history(cls.claim)
        super().tearDownClass()

    def test_claims_overview_query_returns_data_for_seed_claim(self):
        date_start = (datetime.now() - timedelta(days=30)).date().isoformat()
        date_end = datetime.now().date().isoformat()
        result = claims_overview_query(
            self.user,
            date_start=date_start,
            date_end=date_end,
        )
        self.assertNotIn("error", result)
        self.assertTrue(any(row["c_code"] == self.claim.code for row in result["data"]))

    def test_claim_history_query_returns_data_for_seed_claim(self):
        date_start = (datetime.now() - timedelta(days=30)).date().isoformat()
        date_end = datetime.now().date().isoformat()
        result = claim_history_query(
            self.user,
            date_start=date_start,
            date_end=date_end,
            requested_insuree_id=self.claim.insuree_id,
        )
        self.assertNotIn("error", result)
        self.assertTrue(any(row["c_code"] == self.claim.code for row in result["data"]))

    def test_operational_indicators_query_count_per_month_is_bounded(self):
        region = Location.objects.filter(validity_to__isnull=True, type="R").first()
        if region is None:
            self.skipTest("No reference region available for operational indicators")

        year = datetime.now().year
        with CaptureQueriesContext(connection) as ctx:
            from claim.reports.claims_primary_operational_indicators import (
                claims_primary_operational_indicators_query,
            )

            result = claims_primary_operational_indicators_query(
                self.user,
                requested_year=year,
                requested_region_id=region.id,
            )
        self.assertNotIn("error", result)
        # Twelve monthly passes should stay bounded (not 12× per-claim N+1).
        self.assertLess(len(ctx.captured_queries), 80)
