"""
WO-010: Sibling integration smoke tests.

Validates that the claim module remains pluggable and that required sibling
interfaces import successfully when the openIMIS assembly (or dev env) provides them.
Skipped in module-only runs without siblings installed.
"""

import importlib
import unittest

from django.apps import apps
from django.test import TestCase

from claim.apps import ClaimConfig, MODULE_NAME


REQUIRED_SIBLING_MODULES = (
    "core",
    "core.models",
    "insuree",
    "insuree.models",
    "location",
    "location.models",
    "medical",
    "medical.models",
    "policy",
    "policy.models",
    "product",
    "product.models",
    "claim_batch",
    "report",
    "report.services",
)

OPTIONAL_ASSEMBLY_MODULES = (
    "medical_pricelist",
    "medical_pricelist.models",
)


def _can_import(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


class PluggableModuleTest(TestCase):
    """Claim installs as a standard Django AppConfig plugin."""

    def test_module_name(self):
        self.assertEqual(MODULE_NAME, "claim")
        self.assertEqual(ClaimConfig.name, "claim")

    def test_app_config_discoverable(self):
        config = apps.get_app_config("claim")
        self.assertIsInstance(config, ClaimConfig)


@unittest.skipUnless(_can_import("core"), "core sibling not installed")
class SiblingImportSmokeTest(TestCase):
    """Required sibling packages resolve when assembly deps are present."""

    def test_required_sibling_imports(self):
        missing = [m for m in REQUIRED_SIBLING_MODULES if not _can_import(m)]
        self.assertEqual(
            missing,
            [],
            f"Missing sibling modules (check assembly): {missing}",
        )

    def test_claim_models_use_sibling_fks(self):
        from claim.models import Claim
        from insuree.models import Insuree

        field = Claim._meta.get_field("insuree")
        self.assertEqual(field.remote_field.model, Insuree)

    def test_report_service_import(self):
        from report.services import ReportService

        self.assertIsNotNone(ReportService)


@unittest.skipUnless(_can_import("core"), "core sibling not installed")
class OptionalAssemblyModuleTest(TestCase):
    def test_medical_pricelist_when_present(self):
        if not _can_import("medical_pricelist"):
            self.skipTest("medical_pricelist not in assembly")
        import medical_pricelist.models  # noqa: F401

    def test_validations_pricelist_import_path(self):
        """Validations module references medical_pricelist when installed."""
        if not _can_import("medical_pricelist"):
            self.skipTest("medical_pricelist not in assembly")
        from claim import validations

        self.assertTrue(hasattr(validations, "fetch_policies"))
