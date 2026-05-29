"""WO-030: XML serializer module boundary tests."""

from django.test import SimpleTestCase


class XmlSerializerImportsTest(SimpleTestCase):
    def test_serializers_package_reexports(self):
        from claim.serializers import (
            ClaimElementSubmit,
            ClaimItemSubmit,
            ClaimServiceSubmit,
            ClaimSubmit,
        )

        self.assertTrue(ClaimSubmit)
        self.assertTrue(issubclass(ClaimItemSubmit, ClaimElementSubmit))
        self.assertTrue(issubclass(ClaimServiceSubmit, ClaimElementSubmit))

    def test_services_backward_compat_reexports(self):
        import claim.services as services

        for name in (
            "ClaimSubmit",
            "ClaimItemSubmit",
            "ClaimServiceSubmit",
            "ClaimElementSubmit",
        ):
            self.assertTrue(hasattr(services, name), msg=name)

    def test_xml_submit_shim_reexports(self):
        from claim.services import xml_submit

        self.assertTrue(hasattr(xml_submit, "ClaimSubmit"))
