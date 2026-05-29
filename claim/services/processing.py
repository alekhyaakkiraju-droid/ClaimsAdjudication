"""Claim validation, processing, and batch orchestration."""

import datetime
import logging

from django.utils.translation import gettext as _

from claim.models import Claim, ClaimDedRem, ClaimDetail
from claim.state_machine import apply_claim_status
from claim.utils import approved_amount, get_claim_target_date, get_valid_policies_qs
from claim.validations import get_claim_category, validate_claim
from product.models import ProductItemOrService

logger = logging.getLogger(__name__)


def set_claim_submitted(claim, errors, user):
    from claim.audit_governance import record_claim_audit_event

    try:
        claim.audit_user_id_submit = user.id_for_audit
        if errors:
            apply_claim_status(claim, Claim.STATUS_REJECTED)
        else:
            claim.approved = approved_amount(claim)
            apply_claim_status(claim, Claim.STATUS_CHECKED)
            from core.utils import TimeUtils

            claim.submit_stamp = TimeUtils.now()
            claim.category = get_claim_category(claim)
        claim.save()
        record_claim_audit_event(
            "claim.submit",
            user,
            claim=claim,
            context={"rejected": bool(errors)},
        )
        return []
    except Exception as exc:
        logger.exception("set_claim_submitted failed for claim %s", claim.code)
        from claim.api_errors import mutation_error_list

        return {
            "title": claim.code,
            "list": mutation_error_list(
                _("claim.mutation.failed_to_change_status_of_claim")
                % {"code": claim.code},
                claim_code=claim.code,
                exc=exc,
            ),
        }


def processing_claim(claim, user, is_process=False, validate=True, policies=None):
    """
    Process a claim by validating it, assigning products, and handling deductions/remunerations.
    """
    errors = []
    if policies is None:
        target_date = get_claim_target_date(claim)
        if claim.insuree is not None:
            policies = get_valid_policies_qs(claim.insuree.id, target_date)
        else:
            policies = None
    if validate and claim.status != Claim.STATUS_CHECKED:
        errors = validate_claim(
            claim,
            check_max=True,
            policies=policies,
            user=user,
            is_process=is_process,
            process_dedrem_opt=True,
        )

        if len(errors) == 0:
            logger.debug(
                "ProcessClaimsMutation: claim %s validated without errors",
                claim.uuid,
            )
        else:
            logger.debug(
                "ProcessClaimsMutation: claim %s not validated, errors: %s",
                claim.uuid,
                str(errors),
            )
    if len(errors) > 0:
        deleted_dedrems = ClaimDedRem.objects.filter(
            claim=claim,
        ).delete()
        if deleted_dedrems:
            logger.debug(
                f"Claim {claim.uuid} is invalid, we deleted its dedrem ({deleted_dedrems})"
            )
    if is_process:
        errors += set_claim_processed_or_valuated(claim, errors, user)
    return errors


def process_claims_batch(uuids, user):
    """Process multiple claims with shared prefetch and policy caching."""
    from claim.audit_governance import record_claim_audit_event
    from claim.batch_processing import (
        BatchPolicyCache,
        load_claims_for_processing,
        missing_processing_uuids,
    )

    errors = []
    uuid_list = uuids or []
    claims = load_claims_for_processing(uuid_list)
    policy_cache = BatchPolicyCache(claims)

    for claim in claims:
        logger.debug("ProcessClaimsMutation: processing %s", claim.uuid)
        claim.save_history()
        claim.audit_user_id_process = user.id_for_audit
        logger.debug("ProcessClaimsMutation: validating claim %s", claim.uuid)
        c_errors = processing_claim(
            claim,
            user,
            is_process=True,
            policies=policy_cache.policies_for(claim),
        )
        logger.debug(
            "ProcessClaimsMutation: claim %s set processed or valuated", claim.uuid
        )
        if c_errors:
            errors.append({"title": claim.code, "list": c_errors})
        record_claim_audit_event(
            "claim.process",
            user,
            claim=claim,
            context={"errors": len(c_errors)},
        )

    remaining = missing_processing_uuids(uuid_list, claims)
    if remaining:
        errors += {
            "title": _("error"),
            "list": [
                {
                    "message": _("claim.validation.id_does_not_exist")
                    % {"id": ",".join(remaining)}
                }
            ],
        }
    if len(errors) == 1:
        errors = errors[0]["list"]
    return errors


def process_claims_batch_or_enqueue(uuids, user, *, client_mutation_id=None):
    """
    Process claims synchronously or enqueue when batch size meets the async threshold.

    Returns (errors, queued_job) where queued_job is set when work was enqueued.
    """
    from claim.job_queue import enqueue_process_claims, should_enqueue_batch

    uuid_list = uuids or []
    if should_enqueue_batch(uuid_list):
        job = enqueue_process_claims(
            uuid_list,
            user,
            client_mutation_id=client_mutation_id,
        )
        return [], job
    return process_claims_batch(uuid_list, user), None


validate_and_process_dedrem_claim = processing_claim


def set_claim_processed_or_valuated(claim, errors, user):
    try:
        if errors:
            apply_claim_status(claim, Claim.STATUS_REJECTED)
        if claim.status == Claim.STATUS_CHECKED:
            claim.approved = approved_amount(claim)
            if with_relative_prices(claim):
                apply_claim_status(claim, Claim.STATUS_PROCESSED)
                claim.process_stamp = datetime.datetime.now()
                claim.date_processed = datetime.date.today()
            else:
                apply_claim_status(claim, Claim.STATUS_VALUATED)
                claim.valuated = claim.approved
            claim.audit_user_id_process = user.id_for_audit
            from core.utils import TimeUtils

            claim.process_stamp = TimeUtils.now()
        claim.save()
        return []
    except Exception as ex:
        error = {
            "title": claim.code,
            "list": [
                {
                    "message": _("claim.mutation.failed_to_change_status_of_claim")
                    % {"code": claim.code},
                    "detail": claim.uuid,
                }
            ],
        }
        if hasattr(ex, "args") and len(ex.args) > 0:
            for arg in ex.args:
                error["list"].append(arg)
        return [error]


def details_with_relative_prices(details):
    return (
        details.filter(status=ClaimDetail.STATUS_PASSED)
        .filter(price_origin=ProductItemOrService.ORIGIN_RELATIVE)
        .exists()
    )


def with_relative_prices(claim):
    return details_with_relative_prices(claim.items) or details_with_relative_prices(
        claim.services
    )
