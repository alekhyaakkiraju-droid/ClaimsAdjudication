"""WO-031: Type annotation coverage for public API modules."""

import inspect
from pathlib import Path

from django.test import SimpleTestCase

TYPED_MODULES = (
    "claim.serializers.xml_serializer",
    "claim.services.submit",
    "claim.attachment_service",
    "claim.api_errors",
    "claim.gql_authorization",
    "claim.rest_authorization",
    "claim.schema_resolvers",
)


class TypeAnnotationCoverageTest(SimpleTestCase):
    def test_public_modules_listed_in_mypy_overrides(self):
        config = Path(__file__).resolve().parents[2] / "pyproject.toml"
        text = config.read_text(encoding="utf-8")
        for module in TYPED_MODULES:
            prefix = module.replace(".", ".")  # full dotted name
            self.assertIn(prefix, text, msg=f"missing mypy override for {module}")

    def test_key_service_callables_have_annotations(self):
        from claim.services.submit import ClaimSubmitService, submit_claim

        sig = inspect.signature(ClaimSubmitService.submit_claim)
        self.assertIsNotNone(sig.return_annotation)
        self.assertIn("claim", sig.parameters)
        sig_fn = inspect.signature(submit_claim)
        self.assertIsNotNone(sig_fn.return_annotation)

    def test_xml_serializer_public_methods_typed(self):
        from claim.serializers.xml_serializer import ClaimSubmit

        sig = inspect.signature(ClaimSubmit.to_xml)
        self.assertEqual(sig.return_annotation, str)
