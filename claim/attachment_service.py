"""Claim attachment persistence helpers (WO-029)."""

import pathlib
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from claim.apps import ClaimConfig
from claim.attachment_strategies import attachment_strategies_dict
from claim.attachment_validation import validate_attachment_input
from claim.models import ClaimAttachment, ClaimAttachmentType, GeneralClaimAttachmentType


def create_file(date, claim_id, document_bytes: bytes):
    date_iso = date.isoformat()
    root = ClaimConfig.claim_attachments_root_path
    file_dir = "%s/%s/%s/%s" % (date_iso[0:4], date_iso[5:7], date_iso[8:10], claim_id)
    file_path = "%s/%s" % (file_dir, uuid4())
    pathlib.Path("%s/%s" % (root, file_dir)).mkdir(parents=True, exist_ok=True)
    with open("%s/%s" % (root, file_path), "xb") as f:
        f.write(document_bytes)
    return file_path


def create_attachment(claim_id, data):
    data["claim_id"] = claim_id
    from core import datetime

    now = datetime.datetime.now()
    general_type = (
        data["general_type"]
        if data.get("general_type")
        else GeneralClaimAttachmentType.FILE
    )
    data["module"] = "claim"
    if not data.get("predefined_type"):
        data["predefined_type"] = "default"

    decoded_document = validate_attachment_input(
        data, strategies=attachment_strategies_dict.keys()
    )

    if general_type == GeneralClaimAttachmentType.URL:
        if data["predefined_type"] in attachment_strategies_dict:
            data["url"] = attachment_strategies_dict[data["predefined_type"]].handler(
                data
            )
            data["document"] = data["url"]
        data["predefined_type"] = ClaimAttachmentType.objects.get(
            validity_to__isnull=True,
            claim_general_type="URL",
            claim_attachment_type=data["predefined_type"],
        )
    elif general_type == GeneralClaimAttachmentType.FILE:
        if ClaimConfig.claim_attachments_root_path:
            if decoded_document is None:
                raise ValidationError(_("claim.validation.attachment_document_required"))
            data["url"] = create_file(now, claim_id, decoded_document)
            data.pop("document", None)
        data["predefined_type"] = ClaimAttachmentType.objects.get(
            validity_to__isnull=True,
            claim_general_type="FILE",
            claim_attachment_type=data["predefined_type"],
        )
    else:
        raise ValidationError(_("mutation.attachment_general_type_incorrect"))
    data["validity_from"] = now
    ClaimAttachment.objects.create(**data)


def create_attachments(claim_id, attachments):
    for attachment in attachments:
        create_attachment(claim_id, attachment)
