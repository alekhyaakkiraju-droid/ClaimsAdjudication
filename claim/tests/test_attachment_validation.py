"""
WO-013: Unit tests for attachment validation.
"""

import base64
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from claim.apps import ClaimConfig
from claim.attachment_validation import (
    estimate_base64_decoded_size,
    validate_attachment_input,
    validate_base64_document,
    validate_mime_and_extension,
)
from claim.models import GeneralClaimAttachmentType


class AttachmentValidationTest(SimpleTestCase):
    def setUp(self):
        ClaimConfig.attachment_validation_enabled = True
        ClaimConfig.attachment_max_size_bytes = 1024
        ClaimConfig.attachment_allowed_mime_types = ["application/pdf", "text/plain"]
        ClaimConfig.allowed_domains_attachments = ["example.com"]

    def test_rejects_disallowed_mime(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_mime_and_extension("application/x-msdownload", "evil.exe")
        self.assertIn("attachment_mime_not_allowed", str(ctx.exception))

    def test_rejects_extension_mismatch(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_mime_and_extension("application/pdf", "photo.png")
        self.assertIn("attachment_extension_mismatch", str(ctx.exception))

    def test_rejects_oversized_base64_before_decode(self):
        huge = base64.b64encode(b"x" * 2048).decode("ascii")
        with self.assertRaises(ValidationError) as ctx:
            validate_base64_document(huge)
        self.assertIn("attachment_size_exceeded", str(ctx.exception))

    def test_rejects_malformed_base64(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_base64_document("not!!!base64")
        self.assertIn("attachment_invalid_base64", str(ctx.exception))

    def test_accepts_valid_file_payload(self):
        doc = base64.b64encode(b"%PDF-1.4").decode("ascii")
        payload = {
            "general_type": GeneralClaimAttachmentType.FILE,
            "mime": "application/pdf",
            "filename": "claim.pdf",
            "document": doc,
        }
        decoded = validate_attachment_input(payload)
        self.assertEqual(decoded, b"%PDF-1.4")

    def test_rejects_url_outside_allowed_domain(self):
        payload = {
            "general_type": GeneralClaimAttachmentType.URL,
            "url": "https://evil.example.org/doc",
            "predefined_type": "other",
        }
        with self.assertRaises(ValidationError) as ctx:
            validate_attachment_input(payload)
        self.assertIn("attachment_url_domain_not_allowed", str(ctx.exception))

    def test_accepts_url_on_allowed_domain(self):
        payload = {
            "general_type": GeneralClaimAttachmentType.URL,
            "url": "https://files.example.com/doc.pdf",
            "predefined_type": "other",
        }
        self.assertIsNone(validate_attachment_input(payload))

    @mock.patch.object(ClaimConfig, "attachment_validation_enabled", False)
    def test_validation_can_be_disabled(self):
        payload = {
            "general_type": GeneralClaimAttachmentType.FILE,
            "mime": "application/x-unknown",
            "filename": "x.bin",
            "document": base64.b64encode(b"ok").decode("ascii"),
        }
        self.assertIsNotNone(validate_attachment_input(payload))

    def test_estimate_base64_size(self):
        doc = base64.b64encode(b"1234").decode("ascii")
        self.assertEqual(estimate_base64_decoded_size(doc), 4)
