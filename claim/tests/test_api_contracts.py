"""WO-034: API contract documentation checks."""

from django.test import SimpleTestCase


class ApiContractDocumentationTest(SimpleTestCase):
    def test_api_contracts_doc_exists(self):
        from pathlib import Path

        doc = Path(__file__).resolve().parents[2] / "docs" / "API_CONTRACTS.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("GraphQL", text)
        self.assertIn("REST", text)

    def test_schema_query_and_mutation_have_descriptions(self):
        from claim.schema import Mutation, Query

        self.assertIn("GraphQL queries", Query.__doc__ or "")
        self.assertIn("GraphQL mutations", Mutation.__doc__ or "")

    def test_mutation_fields_expose_descriptions(self):
        from claim.schema import Mutation

        create = Mutation._meta.fields["create_claim"]
        self.assertTrue(getattr(create, "description", None))
