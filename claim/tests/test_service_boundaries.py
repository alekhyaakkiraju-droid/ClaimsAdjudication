"""WO-029: Backward-compatible service and validation module boundaries."""

from django.test import SimpleTestCase


class ServiceBoundaryImportsTest(SimpleTestCase):
    def test_services_package_reexports(self):
        import claim.services as services

        for name in (
            "ClaimSubmitService",
            "ClaimCreateService",
            "ClaimReportService",
            "processing_claim",
            "update_or_create_claim",
            "set_claims_status",
            "ClaimSubmit",
        ):
            self.assertTrue(hasattr(services, name), msg=name)

    def test_validations_package_reexports(self):
        from claim.validations import (
            REJECTION_REASON_INVALID_CLAIM,
            get_claim_category,
            process_dedrem,
            validate_claim,
        )

        self.assertEqual(REJECTION_REASON_INVALID_CLAIM, 20)
        self.assertTrue(callable(get_claim_category))
        self.assertTrue(callable(process_dedrem))
        self.assertTrue(callable(validate_claim))

    def test_attachment_service_import(self):
        from claim.attachment_service import create_attachment, create_attachments

        self.assertTrue(callable(create_attachment))
        self.assertTrue(callable(create_attachments))

    def test_schema_resolvers_import(self):
        from claim.schema_resolvers import resolve_claims, resolve_claim

        self.assertTrue(callable(resolve_claims))
        self.assertTrue(callable(resolve_claim))
