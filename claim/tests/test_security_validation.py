"""WO-036: Security validation documentation and module checks."""

from django.test import SimpleTestCase


class SecurityValidationTest(SimpleTestCase):
    def test_security_validation_doc_exists(self):
        from pathlib import Path

        doc = Path(__file__).resolve().parents[2] / "docs" / "SECURITY_VALIDATION.md"
        self.assertTrue(doc.is_file())

    def test_authorization_gateways_importable(self):
        from claim.gql_authorization import require_mutation_permission, require_query_permission
        from claim.rest_authorization import require_rest_permission

        self.assertTrue(callable(require_mutation_permission))
        self.assertTrue(callable(require_query_permission))
        self.assertTrue(callable(require_rest_permission))

    def test_attachment_validation_importable(self):
        from claim.attachment_validation import validate_attachment_input

        self.assertTrue(callable(validate_attachment_input))
