"""WO-035: Performance validation documentation and module hooks."""

from django.test import SimpleTestCase


class PerformanceValidationTest(SimpleTestCase):
    def test_performance_validation_doc_lists_targets(self):
        from pathlib import Path

        doc = Path(__file__).resolve().parents[2] / "docs" / "PERFORMANCE_VALIDATION.md"
        text = doc.read_text(encoding="utf-8")
        for keyword in ("Submission latency", "Report runtime", "Batch throughput"):
            self.assertIn(keyword, text)

    def test_optimization_modules_importable(self):
        from claim.services.processing import process_claims_batch
        from claim.submission_pipeline import load_claim_for_submission

        self.assertTrue(callable(process_claims_batch))
        self.assertTrue(callable(load_claim_for_submission))
