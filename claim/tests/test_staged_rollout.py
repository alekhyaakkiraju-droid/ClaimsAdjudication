"""WO-038: Staged rollout documentation checks."""

from django.test import SimpleTestCase


class StagedRolloutTest(SimpleTestCase):
    def test_staged_rollout_doc_exists(self):
        from pathlib import Path

        doc = Path(__file__).resolve().parents[2] / "docs" / "STAGED_ROLLOUT.md"
        self.assertTrue(doc.is_file())
        text = doc.read_text(encoding="utf-8")
        self.assertIn("Pilot", text)
        self.assertIn("Production-ready", text)

    def test_staged_rollout_smoke_script_exists(self):
        from pathlib import Path

        script = Path(__file__).resolve().parents[2] / "scripts" / "staged-rollout-smoke.sh"
        self.assertTrue(script.is_file())
