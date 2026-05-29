"""
WO-020: Query cache tests.
"""

from unittest import mock
from uuid import uuid4

from django.core.cache import cache
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from claim.api_errors import get_valid_claim
from claim.models import ClaimAttachmentType, GeneralClaimAttachmentType
from claim.query_cache import (
    NOT_FOUND,
    attachment_types_cache_key,
    bump_list_cache_version,
    cached_or_load,
    claim_detail_cache_key,
    invalidate_claim_cache,
    officers_cache_key,
    safe_cache_get,
    safe_cache_set,
)
from claim.schema import Query
from claim.test_helpers import (
    create_test_claim,
    delete_claim_with_itemsvc_dedrem_and_history,
)
from core.models import Officer
from core.models.openimis_graphql_test_case import BaseTestContext, openIMISGraphQLTestCase
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token


class SafeCacheOperationsTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_safe_cache_get_returns_none_when_backend_raises(self):
        with mock.patch("claim.query_cache.cache.get", side_effect=ConnectionError("redis down")):
            self.assertIsNone(safe_cache_get("claim:test"))

    def test_safe_cache_set_returns_false_when_backend_raises(self):
        with mock.patch("claim.query_cache.cache.set", side_effect=ConnectionError("redis down")):
            self.assertFalse(safe_cache_set("claim:test", 1, 60))

    def test_cached_or_load_falls_back_to_loader_on_cache_failure(self):
        calls = {"count": 0}

        def loader():
            calls["count"] += 1
            return ["pk-1"]

        with mock.patch("claim.query_cache.safe_cache_get", return_value=None):
            with mock.patch("claim.query_cache.safe_cache_set", return_value=False):
                result = cached_or_load("claim:ref:test", loader, timeout=60)
        self.assertEqual(result, ["pk-1"])
        self.assertEqual(calls["count"], 1)


class ClaimDetailCacheTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.claim = create_test_claim(custom_props={"code": f"WO020-{uuid4().hex[:8]}"})

    @classmethod
    def tearDownClass(cls):
        delete_claim_with_itemsvc_dedrem_and_history(cls.claim)
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def test_get_valid_claim_uses_cached_pk(self):
        key = claim_detail_cache_key(claim_id=self.claim.id)
        safe_cache_set(key, self.claim.pk, 120)
        with CaptureQueriesContext(connection) as ctx:
            loaded = get_valid_claim(claim_id=self.claim.id)
        self.assertEqual(loaded.pk, self.claim.pk)
        self.assertLessEqual(len(ctx.captured_queries), 2)

    def test_get_valid_claim_negative_cache(self):
        missing_id = self.claim.id + 99999
        key = claim_detail_cache_key(claim_id=missing_id)
        safe_cache_set(key, NOT_FOUND, 120)
        with CaptureQueriesContext(connection) as ctx:
            loaded = get_valid_claim(claim_id=missing_id)
        self.assertIsNone(loaded)
        self.assertEqual(len(ctx.captured_queries), 0)

    def test_invalidate_claim_cache_clears_detail_entry(self):
        key = claim_detail_cache_key(claim_uuid=self.claim.uuid)
        safe_cache_set(key, self.claim.pk, 120)
        invalidate_claim_cache(claim_uuids=[self.claim.uuid])
        self.assertIsNone(safe_cache_get(key))


class ReferenceDataCacheResolverTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo020-cache")
        cls.info = mock.Mock()
        cls.info.context.user = cls.user

    def setUp(self):
        cache.clear()

    def test_resolve_claim_attachment_type_uses_cached_pks(self):
        att_type, _ = ClaimAttachmentType.objects.get_or_create(
            claim_attachment_type=f"WO020-{uuid4().hex[:6]}",
            defaults={"claim_general_type": GeneralClaimAttachmentType.FILE},
        )
        key = attachment_types_cache_key()
        safe_cache_set(key, [att_type.pk], 300)
        with CaptureQueriesContext(connection) as ctx:
            qs = Query().resolve_claim_attachment_type(self.info)
            pks = list(qs.values_list("pk", flat=True))
        self.assertIn(att_type.pk, pks)
        self.assertEqual(len(ctx.captured_queries), 1)

    def test_resolve_claim_officers_uses_cached_pks(self):
        officer = Officer.objects.create(
            code=f"WO020-{uuid4().hex[:6]}",
            last_name="Cache",
            other_names="Test",
            validity_from=self.user.validity_from,
        )
        key = officers_cache_key(None)
        safe_cache_set(key, [officer.pk], 300)
        with CaptureQueriesContext(connection) as ctx:
            qs = Query().resolve_claim_officers(self.info, search=None)
            pks = list(qs.values_list("pk", flat=True))
        self.assertIn(officer.pk, pks)
        self.assertEqual(len(ctx.captured_queries), 1)


class ClaimListCacheVersionTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_bump_list_cache_version_changes_claim_list_key(self):
        from claim.query_cache import claim_list_cache_key

        before = claim_list_cache_key({"filters": []})
        bump_list_cache_version()
        after = claim_list_cache_key({"filters": []})
        self.assertNotEqual(before, after)


class ClaimListGraphQLCacheTest(openIMISGraphQLTestCase):
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo020-list")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.claim = create_test_claim(custom_props={"code": f"WO020L-{uuid4().hex[:8]}"})

    @classmethod
    def tearDownClass(cls):
        delete_claim_with_itemsvc_dedrem_and_history(cls.claim)
        super().tearDownClass()

    def setUp(self):
        cache.clear()

    def _headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def test_claims_list_second_request_uses_cached_pks(self):
        query = """
            query {
                claims(first: 5) {
                    edges { node { code } }
                }
            }
        """
        self.query(query, headers=self._headers())
        with CaptureQueriesContext(connection) as ctx:
            response = self.query(query, headers=self._headers())
        self.assertResponseNoErrors(response)
        self.assertLessEqual(len(ctx.captured_queries), 12)
