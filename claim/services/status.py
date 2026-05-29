"""Feedback, review, and lifecycle status changes."""

import logging
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext as _

from claim.models import Claim, FeedbackPrompt
from core.models import Officer

logger = logging.getLogger(__name__)


def set_claims_status(uuids, field, status, audit_data=None, user=None):
    from claim.audit_governance import operation_for_status_change, record_claim_audit_event

    errors = []
    claims = Claim.objects.filter(uuid__in=uuids, *Claim.filter_validity())
    remaining_uuid = list(set(map(str.upper, uuids)))
    for claim in claims:
        remaining_uuid.remove(claim.uuid.upper())
        try:
            claim.save_history()
            if field == "feedback_status":
                from claim.feedback_review_state_machine import apply_feedback_status

                apply_feedback_status(claim, status)
            elif field == "review_status":
                from claim.feedback_review_state_machine import apply_review_status

                apply_review_status(claim, status)
            else:
                setattr(claim, field, status)
            if field == "feedback_status":
                if status == Claim.FEEDBACK_SELECTED:
                    create_feedback_prompt(claim, user)
                elif status in [Claim.FEEDBACK_NOT_SELECTED, Claim.FEEDBACK_BYPASSED]:
                    set_feedback_prompt_validity_to_to_current_date(claim.uuid)
            if audit_data:
                for k, v in audit_data.items():
                    setattr(claim, k, v)
            claim.save()
            if user is not None:
                operation = operation_for_status_change(field, status)
                if operation:
                    record_claim_audit_event(
                        operation,
                        user,
                        claim=claim,
                        context={field: status},
                    )
        except Exception as exc:
            errors += [
                {
                    "message": _("claim.mutation.failed_to_change_status_of_claim")
                    % {"code": claim.code}
                }
            ]
            if hasattr(exc, "messages") and len(exc.messages):
                for m in exc.messages:
                    errors.append({"message": m})
            elif hasattr(exc, "args") and len(exc.args):
                for m in exc.args:
                    errors.append({"message": m})
    if len(remaining_uuid):
        errors += [
            {
                "message": _("claim.validation.id_does_not_exist")
                % {"id": ",".join(remaining_uuid)}
            }
        ]

    return errors


def create_feedback_prompt(current_claim, user):
    feedback_prompt = {}
    from core.utils import TimeUtils

    feedback_prompt["feedback_prompt_date"] = TimeUtils.date()
    feedback_prompt["validity_from"] = TimeUtils.now()
    feedback_prompt["claim"] = current_claim
    villages = []
    if current_claim.insuree.current_village:
        villages.append(current_claim.insuree.current_village)
    if current_claim.insuree.family.location:
        villages.append(current_claim.insuree.family.location)
    officer = (
        Officer.objects.filter(
            *Officer.filter_validity(),
            officer_villages__location__in=villages,
            phone__isnull=False,
        )
        .exclude(phone__exact="")
        .first()
    )
    if not officer:
        bad_officer = Officer.objects.filter(
            *Officer.filter_validity(),
            officer_villages__location__in=villages,
        ).first()
        if bad_officer:
            msg = [" officer " + bad_officer.code + "has not phone setup"]
        else:
            msg = []
        raise RuntimeError(
            f"No officer with a phone number found for the insuree village code, \
            {', '.join([str(v.code) for v in villages])}",
            *msg,
        )

    feedback_prompt["officer_id"] = officer.id
    feedback_prompt["phone_number"] = officer.phone
    feedback_prompt["audit_user_id"] = user.id_for_audit
    FeedbackPrompt.objects.create(**feedback_prompt)


def set_feedback_prompt_validity_to_to_current_date(claim_uuid):
    try:
        claim = Claim.objects.get(uuid=claim_uuid).id
        feedback_prompt_id = FeedbackPrompt.objects.get(
            claim=claim, validity_to=None
        ).id
        from core.utils import TimeUtils

        current_feedback_prompt = FeedbackPrompt.objects.get(id=feedback_prompt_id)
        current_feedback_prompt.validity_to = TimeUtils.now()
        current_feedback_prompt.save()
    except ObjectDoesNotExist:
        return "No such feedback prompt exist."


def update_claims_dedrems(uuids, user, claims=None):
    from claim.services.processing import processing_claim

    if not uuids and not claims:
        return []
    elif uuids:
        claims = Claim.objects.filter(uuid__in=uuids)
    errors = []

    remaining_uuid = list(map(UUID, uuids)) if uuids else []
    for claim in claims:
        if uuids:
            remaining_uuid.remove(UUID(claim.uuid))
        logger.debug(f"delivering review on {claim.uuid}, reprocessing dedrem ({user})")
        errors += processing_claim(claim, user, False)
    if len(remaining_uuid):
        errors.append(
            _("claim.validation.id_does_not_exist") % {"id": ",".join(remaining_uuid)}
        )
    return errors
