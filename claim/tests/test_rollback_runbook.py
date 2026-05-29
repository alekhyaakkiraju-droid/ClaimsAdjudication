"""WO-037: Rollback runbook documentation checks."""

from django.test import SimpleTestCase


class RollbackRunbookTest(SimpleTestCase):
    def test_rollback_runbook_covers_high_risk_areas(self):
        from pathlib import Path

        doc = Path(__file__).resolve().parents[2] / "docs" / "ROLLBACK_RUNBOOK.md"
        text = doc.read_text(encoding="utf-8")
        for area in (
            "Authorization",
            "Redis query cache",
            "Database-backed job queue",
            "Post-rollback health checks",
        ):
            self.assertIn(area, text)
