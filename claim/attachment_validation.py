"""
Secure attachment validation for claim uploads (WO-013).

Validates MIME allowlist, extension consistency, payload size, and base64
integrity before decode/persistence. URL attachments enforce configured domains.
"""

from __future__ import annotations

import binascii
import re
from typing import Iterable, Optional, Set
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from claim.apps import ClaimConfig
from claim.models import GeneralClaimAttachmentType

# Normalized extension -> acceptable MIME types (lowercase).
EXTENSION_MIME_MAP = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".gif": {"image/gif"},
    ".txt": {"text/plain"},
}

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def _validation_enabled() -> bool:
    if getattr(ClaimConfig, "default_validations_disabled", False):
        return False
    return bool(getattr(ClaimConfig, "attachment_validation_enabled", True))


def _max_size_bytes() -> int:
    size = getattr(ClaimConfig, "attachment_max_size_bytes", None)
    if size is None or size <= 0:
        return 10 * 1024 * 1024
    return int(size)


def _allowed_mimes() -> Set[str]:
    configured = getattr(ClaimConfig, "attachment_allowed_mime_types", None) or []
    return {m.lower().strip() for m in configured if m}


def _extension_from_filename(filename: Optional[str]) -> Optional[str]:
    if not filename or "." not in filename:
        return None
    return "." + filename.rsplit(".", 1)[-1].lower()


def estimate_base64_decoded_size(document_b64: str) -> int:
    """Upper-bound decoded byte size without full decode."""
    stripped = "".join(document_b64.split())
    if not stripped:
        return 0
    padding = stripped.count("=")
    return max(0, (len(stripped) * 3) // 4 - padding)


def validate_base64_document(document_b64: str) -> bytes:
    """Reject malformed base64 before expensive persistence."""
    if document_b64 is None:
        raise ValidationError(_("claim.validation.attachment_document_required"))
    stripped = "".join(str(document_b64).split())
    if not stripped or len(stripped) % 4 != 0 or not _BASE64_RE.match(stripped):
        raise ValidationError(_("claim.validation.attachment_invalid_base64"))
    max_size = _max_size_bytes()
    if estimate_base64_decoded_size(stripped) > max_size:
        raise ValidationError(
            _("claim.validation.attachment_size_exceeded") % {"max": max_size}
        )
    try:
        return binascii.a2b_base64(stripped)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(_("claim.validation.attachment_invalid_base64")) from exc


def validate_mime_and_extension(mime: Optional[str], filename: Optional[str]) -> None:
    allowed = _allowed_mimes()
    if not allowed:
        return
    mime_norm = (mime or "").lower().strip()
    if not mime_norm or mime_norm not in allowed:
        raise ValidationError(
            _("claim.validation.attachment_mime_not_allowed") % {"mime": mime or ""}
        )
    ext = _extension_from_filename(filename)
    if ext and ext in EXTENSION_MIME_MAP:
        if mime_norm not in EXTENSION_MIME_MAP[ext]:
            raise ValidationError(
                _("claim.validation.attachment_extension_mismatch")
                % {"filename": filename, "mime": mime_norm}
            )


def validate_url_attachment(url: str, predefined_type: Optional[str], strategies: Iterable[str]) -> None:
    if not url:
        raise ValidationError(_("claim.validation.attachment_url_required"))
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError(_("mutation.attachment_url_domain_not_allowed"))
    allowed_domains = list(getattr(ClaimConfig, "allowed_domains_attachments", None) or [])
    if allowed_domains:
        host = (parsed.netloc or "").lower()
        if not any(
            host == domain.lower() or host.endswith("." + domain.lower())
            for domain in allowed_domains
        ):
            raise ValidationError(_("mutation.attachment_url_domain_not_allowed"))


def validate_attachment_input(data: dict, strategies: Optional[Iterable[str]] = None) -> Optional[bytes]:
    """
    Validate GraphQL/REST attachment payload. Returns decoded bytes for FILE uploads
    when document is present (caller may use for filesystem write).
    """
    if not _validation_enabled():
        document = data.get("document")
        return binascii.a2b_base64("".join(document.split())) if document else None

    general_type = data.get("general_type") or GeneralClaimAttachmentType.FILE
    strategies = strategies or []

    if general_type == GeneralClaimAttachmentType.URL:
        validate_url_attachment(
            data.get("url") or "",
            data.get("predefined_type"),
            strategies,
        )
        return None

    if general_type == GeneralClaimAttachmentType.FILE:
        validate_mime_and_extension(data.get("mime"), data.get("filename"))
        document = data.get("document")
        if document:
            return validate_base64_document(document)
        return None

    raise ValidationError(_("mutation.attachment_general_type_incorrect"))
