"""
Central audit governance for significant claim operations (WO-015).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Union

from claim.models import Claim

logger = logging.getLogger("claim.audit")

PII_FIELD_MARKERS = (
    "chf_id",
    "chfid",
    "insuree_code",
    "document",
    "phone",
    "email",
    "last_name",
    "other_names",
    "first_name",
    "name",
    "filename",
    "url",
    "password",
    "token",
)

SIGNIFICANT_OPERATIONS = frozenset(
    {
        "claim.create",
        "claim.update",
        "claim.restore",
        "claim.submit",
        "claim.process",
        "claim.delete",
        "claim.feedback.select",
        "claim.feedback.bypass",
        "claim.feedback.skip",
        "claim.feedback.deliver",
        "claim.review.select",
        "claim.review.bypass",
        "claim.review.skip",
        "claim.review.deliver",
        "claim.review.save",
        "claim.attachment.create",
        "claim.attachment.update",
        "claim.attachment.delete",
    }
)

MUTATION_OPERATION_MAP = {
    "CreateClaimMutation": "claim.create",
    "UpdateClaimMutation": "claim.update",
    "AddClaimAttachmentMutation": "claim.attachment.create",
    "UpdateAttachmentMutation": "claim.attachment.update",
    "DeleteClaimAttachmentMutation": "claim.attachment.delete",
    "SubmitClaimsMutation": "claim.submit",
    "SelectClaimsForFeedbackMutation": "claim.feedback.select",
    "BypassClaimsFeedbackMutation": "claim.feedback.bypass",
    "SkipClaimsFeedbackMutation": "claim.feedback.skip",
    "DeliverClaimFeedbackMutation": "claim.feedback.deliver",
    "SelectClaimsForReviewMutation": "claim.review.select",
    "BypassClaimsReviewMutation": "claim.review.bypass",
    "SkipClaimsReviewMutation": "claim.review.skip",
    "DeliverClaimsReviewMutation": "claim.review.deliver",
    "SaveClaimReviewMutation": "claim.review.save",
    "ProcessClaimsMutation": "claim.process",
    "DeleteClaimsMutation": "claim.delete",
}


def mask_sensitive_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    key_lower = key.lower()
    if any(marker in key_lower for marker in PII_FIELD_MARKERS):
        if isinstance(value, str) and len(value) > 4:
            return "***" + value[-4:]
        return "***"
    if key_lower == "document" and isinstance(value, str) and len(value) > 32:
        return "<redacted:%s chars>" % len(value)
    return value


def mask_payload(data: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not data:
        return {}
    masked: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = mask_payload(value)
        elif isinstance(value, list):
            masked[key] = [
                mask_payload(item) if isinstance(item, dict) else mask_sensitive_value(key, item)
                for item in value
            ]
        else:
            masked[key] = mask_sensitive_value(key, value)
    return masked


def operation_for_status_change(field: str, status: int) -> Optional[str]:
    if field == "feedback_status":
        return {
            Claim.FEEDBACK_SELECTED: "claim.feedback.select",
            Claim.FEEDBACK_BYPASSED: "claim.feedback.bypass",
            Claim.FEEDBACK_NOT_SELECTED: "claim.feedback.skip",
            Claim.FEEDBACK_DELIVERED: "claim.feedback.deliver",
        }.get(status)
    if field == "review_status":
        return {
            Claim.REVIEW_SELECTED: "claim.review.select",
            Claim.REVIEW_BYPASSED: "claim.review.bypass",
            Claim.REVIEW_NOT_SELECTED: "claim.review.skip",
            Claim.REVIEW_DELIVERED: "claim.review.deliver",
        }.get(status)
    return None


def audit_fields_for_operation(operation: str, user) -> Dict[str, int]:
    actor_id = getattr(user, "id_for_audit", None)
    if actor_id is None:
        return {}
    mapping = {
        "claim.submit": {"audit_user_id_submit": actor_id},
        "claim.process": {"audit_user_id_process": actor_id},
        "claim.review.deliver": {"audit_user_id_review": actor_id},
        "claim.review.save": {"audit_user_id_review": actor_id},
        "claim.feedback.deliver": {"audit_user_id": actor_id},
        "claim.create": {"audit_user_id": actor_id},
        "claim.update": {"audit_user_id": actor_id},
        "claim.restore": {"audit_user_id": actor_id},
    }
    return mapping.get(operation, {"audit_user_id": actor_id})


def record_claim_audit_event(
    operation: str,
    user,
    *,
    claim=None,
    claim_uuid: Optional[Union[str, Any]] = None,
    claim_code: Optional[str] = None,
    resource_type: str = "claim",
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Emit a structured, PII-safe audit log entry for a significant claim action.
    """
    if operation not in SIGNIFICANT_OPERATIONS:
        logger.warning("claim_audit: unregistered operation %s", operation)

    from core.utils import TimeUtils

    event: Dict[str, Any] = {
        "event": operation,
        "resource_type": resource_type,
        "actor_id": getattr(user, "id_for_audit", None),
        "timestamp": TimeUtils.now().isoformat(),
    }
    if claim is not None:
        event["claim_uuid"] = str(claim.uuid)
        event["claim_code"] = claim.code
    elif claim_uuid is not None:
        event["claim_uuid"] = str(claim_uuid)
    if claim_code:
        event["claim_code"] = claim_code
    if context:
        event["context"] = mask_payload(context)
    logger.info("claim_audit %s", event)
    return event


def record_mutation_audit(
    mutation_class: str,
    user,
    *,
    claim=None,
    claim_uuid=None,
    claim_code=None,
    context=None,
):
    operation = MUTATION_OPERATION_MAP.get(mutation_class)
    if not operation:
        return
    record_claim_audit_event(
        operation,
        user,
        claim=claim,
        claim_uuid=claim_uuid,
        claim_code=claim_code,
        context=context,
    )
