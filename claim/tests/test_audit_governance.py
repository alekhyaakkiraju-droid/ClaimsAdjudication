"""
WO-015: Audit governance tests.
"""

from unittest import mock

from django.test import SimpleTestCase

from claim.audit_governance import (
    MUTATION_OPERATION_MAP,
    SIGNIFICANT_OPERATIONS,
    mask_payload,
    mask_sensitive_value,
    operation_for_status_change,
    record_claim_audit_event,
)
from claim.models import Claim


class MaskSensitiveTest(SimpleTestCase):
    def test_masks_chf_id(self):
        self.assertEqual(mask_sensitive_value("chf_id", "1234567890"), "***7890")

    def test_masks_document_payload(self):
        masked = mask_payload(
            {
                "chf_id": "ABCDEF1234",
                "document": "A" * 100,
                "code": "CLM001",
            }
        )
        self.assertTrue(masked["chf_id"].startswith("***"))
        self.assertIn("redacted", masked["document"])
        self.assertEqual(masked["code"], "CLM001")


class AuditCoverageTest(SimpleTestCase):
    def test_significant_operations_include_lifecycle_actions(self):
        required = {
            "claim.create",
            "claim.submit",
            "claim.process",
            "claim.feedback.deliver",
            "claim.review.save",
            "claim.delete",
            "claim.restore",
        }
        self.assertTrue(required.issubset(SIGNIFICANT_OPERATIONS))

    def test_mutation_map_covers_feedback_and_review_mutations(self):
        self.assertIn("SubmitClaimsMutation", MUTATION_OPERATION_MAP)
        self.assertIn("ProcessClaimsMutation", MUTATION_OPERATION_MAP)
        self.assertIn("DeliverClaimFeedbackMutation", MUTATION_OPERATION_MAP)
        self.assertIn("SaveClaimReviewMutation", MUTATION_OPERATION_MAP)

    def test_operation_for_feedback_selected(self):
        self.assertEqual(
            operation_for_status_change("feedback_status", Claim.FEEDBACK_SELECTED),
            "claim.feedback.select",
        )

    def test_operation_for_review_delivered(self):
        self.assertEqual(
            operation_for_status_change("review_status", Claim.REVIEW_DELIVERED),
            "claim.review.deliver",
        )


class RecordAuditEventTest(SimpleTestCase):
    def test_structured_log_masks_context_pii(self):
        user = mock.Mock(id_for_audit=42)
        with self.assertLogs("claim.audit", level="INFO") as logs:
            record_claim_audit_event(
                "claim.create",
                user,
                claim_uuid="00000000-0000-0000-0000-000000000001",
                claim_code="CLM001",
                context={"chf_id": "SECRETCHFID", "status": 1},
            )
        log_line = logs.output[0]
        self.assertIn("claim_audit", log_line)
        self.assertIn("claim.create", log_line)
        self.assertNotIn("SECRETCHFID", log_line)
        self.assertIn("actor_id", log_line)
