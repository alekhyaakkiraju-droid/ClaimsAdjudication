"""
WO-014: Exception handling and safe lookup tests.
"""

import json
from uuid import uuid4

from django.test import SimpleTestCase

from claim.api_errors import mutation_error_list
from core.models.openimis_graphql_test_case import (
    BaseTestContext,
    openIMISGraphQLTestCase,
)
from core.test_helpers import create_test_interactive_user
from graphql_jwt.shortcuts import get_token


class ApiErrorsUnitTest(SimpleTestCase):
    def test_mutation_error_list_hides_unexpected_exception_detail(self):
        errors = mutation_error_list("failed", exc=RuntimeError("secret internals"))
        self.assertEqual(len(errors), 1)
        self.assertIn("failed", errors[0]["message"])
        self.assertNotIn("detail", errors[0])

    def test_mutation_error_list_keeps_validation_detail(self):
        from django.core.exceptions import ValidationError

        errors = mutation_error_list("failed", exc=ValidationError("bad field"))
        self.assertEqual(errors[0]["detail"], "['bad field']")


class FspFromClaimExceptionTest(openIMISGraphQLTestCase):
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo014-fsp")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))

    def test_fsp_unknown_insuree_returns_null_without_exception(self):
        response = self.query(
            """
            query {
                fspFromClaim(
                    insureeCode: "WO014-NONEXISTENT-CHF",
                    dateClaimed: "2020-01-01"
                ) { id }
            }
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        content = json.loads(response.content)
        self.assertNotIn("errors", content, content.get("errors"))
        self.assertIsNone(content["data"]["fspFromClaim"])


class ResolveClaimExceptionTest(openIMISGraphQLTestCase):
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = create_test_interactive_user(username="wo014-claim")
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))

    def test_claim_unknown_uuid_returns_null_without_exception(self):
        response = self.query(
            f"""
            query {{
                claim(uuid: "{uuid4()}") {{ id code }}
            }}
            """,
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        content = json.loads(response.content)
        self.assertNotIn("errors", content, content.get("errors"))
        self.assertIsNone(content["data"]["claim"])
