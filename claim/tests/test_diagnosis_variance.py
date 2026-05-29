"""
WO-019: Diagnosis variance query optimization tests.
"""

import json
from datetime import timedelta
from uuid import uuid4

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from claim.diagnosis_variance import (
    build_diagnosis_variance_filter,
    fetch_diagnosis_avg_approved,
)
from claim.models import Claim
from claim.test_helpers import (
    create_test_claim,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.models.openimis_graphql_test_case import BaseTestContext, openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token
from medical.test_helpers import create_test_diagnosis


def _claim_with_amounts(*, icd, claimed, approved, date_claimed):
    claim = create_test_claim(custom_props={"icd": icd, "date_claimed": date_claimed})
    claim.claimed = claimed
    claim.approved = approved
    claim.date_claimed = date_claimed
    claim.save()
    return claim


class DiagnosisVarianceFilterTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shared_icd = create_test_diagnosis(custom_props={"code": f"WO019-{uuid4().hex[:6]}"})
        cls.lookback = timezone.now().date() - timedelta(days=30)
        cls.claims = []

        baseline = _claim_with_amounts(
            icd=cls.shared_icd,
            claimed=100,
            approved=100,
            date_claimed=cls.lookback + timedelta(days=1),
        )
        cls.claims.append(baseline)

        high_claim = _claim_with_amounts(
            icd=cls.shared_icd,
            claimed=200,
            approved=50,
            date_claimed=cls.lookback + timedelta(days=2),
        )
        cls.claims.append(high_claim)

        low_claim = _claim_with_amounts(
            icd=cls.shared_icd,
            claimed=110,
            approved=100,
            date_claimed=cls.lookback + timedelta(days=3),
        )
        cls.claims.append(low_claim)

        cls.high_claim = high_claim
        cls.low_claim = low_claim

    @classmethod
    def tearDownClass(cls):
        for claim in cls.claims:
            delete_claim_with_itemsvc_dedrem_and_history(claim)
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def test_high_variance_filter_matches_expected_claims(self):
        last_year = timezone.now().date() - timedelta(days=365)
        variance_filter = build_diagnosis_variance_filter(
            50,
            validity_filters=Claim.filter_validity(),
            last_year_date=last_year,
            only_on_existing=True,
        )
        matched_ids = set(
            Claim.objects.filter(variance_filter).values_list("id", flat=True)
        )
        self.assertIn(self.high_claim.id, matched_ids)
        self.assertNotIn(self.low_claim.id, matched_ids)

    def test_fetch_diagnosis_avg_uses_single_aggregate_query(self):
        last_year = timezone.now().date() - timedelta(days=365)
        with CaptureQueriesContext(connection) as ctx:
            avgs = fetch_diagnosis_avg_approved(
                validity_filters=Claim.filter_validity(),
                last_year_date=last_year,
            )
        self.assertIn(self.shared_icd.code, avgs)
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_cached_fetch_avoids_repeat_database_query(self):
        last_year = timezone.now().date() - timedelta(days=365)
        validity_filters = Claim.filter_validity()
        fetch_diagnosis_avg_approved(
            validity_filters=validity_filters,
            last_year_date=last_year,
        )
        with CaptureQueriesContext(connection) as ctx:
            fetch_diagnosis_avg_approved(
                validity_filters=validity_filters,
                last_year_date=last_year,
            )
        self.assertEqual(len(ctx.captured_queries), 0)


class DiagnosisVarianceGraphQLTest(openIMISGraphQLTestCase):
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo019-variance")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.shared_icd = create_test_diagnosis(custom_props={"code": f"WO019G-{uuid4().hex[:6]}"})
        cls.lookback = timezone.now().date() - timedelta(days=30)
        cls.claims = []

        baseline = _claim_with_amounts(
            icd=cls.shared_icd,
            claimed=100,
            approved=100,
            date_claimed=cls.lookback + timedelta(days=1),
        )
        cls.claims.append(baseline)

        cls.high_claim = _claim_with_amounts(
            icd=cls.shared_icd,
            claimed=250,
            approved=50,
            date_claimed=cls.lookback + timedelta(days=2),
        )
        cls.claims.append(cls.high_claim)

        cls.low_claim = _claim_with_amounts(
            icd=cls.shared_icd,
            claimed=110,
            approved=100,
            date_claimed=cls.lookback + timedelta(days=3),
        )
        cls.claims.append(cls.low_claim)

    @classmethod
    def tearDownClass(cls):
        for claim in cls.claims:
            delete_claim_with_itemsvc_dedrem_and_history(claim)
        super().tearDownClass()

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_graphql_diagnosis_variance_filter_returns_high_variance_claim(self):
        response = self.query(
            """
            query($variance: Int!) {
                claims(first: 20, diagnosisVariance: $variance, orderBy: ["-dateClaimed"]) {
                    edges {
                        node {
                            code
                            claimed
                        }
                    }
                }
            }
            """,
            variables={"variance": 50},
            headers=self._headers(),
        )
        self.assertResponseNoErrors(response)
        codes = {
            edge["node"]["code"]
            for edge in json.loads(response.content)["data"]["claims"]["edges"]
        }
        self.assertIn(self.high_claim.code, codes)
        self.assertNotIn(self.low_claim.code, codes)

    def test_variance_filter_query_count_is_bounded(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self.query(
                """
                query($variance: Int!) {
                    claims(first: 5, diagnosisVariance: $variance) {
                        edges { node { code claimed } }
                    }
                }
                """,
                variables={"variance": 50},
                headers=self._headers(),
            )
        self.assertResponseNoErrors(response)
        self.assertLessEqual(
            len(ctx.captured_queries),
            15,
            msg="Diagnosis variance filter should not add per-row correlated queries",
        )
