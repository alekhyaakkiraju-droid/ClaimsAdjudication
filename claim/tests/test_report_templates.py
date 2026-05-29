import json
import unittest

from claim.reports.template_loader import load_report_template

KNOWN_TEMPLATES = (
    "claim",
    "claims_overview",
    "claim_history",
    "claim_percentage_referrals",
    "claims_primary_operational_indicators",
)


class ReportTemplateLoaderTest(unittest.TestCase):
    def test_load_known_templates(self):
        for name in KNOWN_TEMPLATES:
            content = load_report_template(name)
            self.assertTrue(content.strip().startswith("{"))
            parsed = json.loads(content)
            self.assertIn("docElements", parsed)

    def test_load_unknown_template_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_report_template("nonexistent_report")

    def test_invalid_template_name_raises(self):
        with self.assertRaises(ValueError):
            load_report_template("../claim")

    def test_claim_module_template_loads(self):
        from claim.reports import claim

        self.assertIn("docElements", json.loads(claim.template))
