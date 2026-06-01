"""Claim submission and creation orchestration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from django.conf import settings

from core.signals import register_service_signal

from claim.apps import ClaimConfig
from claim.models import Claim
from claim.state_machine import apply_claim_status
from claim.utils import (
    approved_amount,
    process_items_relations,
    process_services_relations,
)
from claim.validations import get_claim_category

from claim.services.processing import processing_claim
from claim.serializers.xml_serializer import ClaimSubmit


class ClaimSubmitError(Exception):
    ERROR_CODES = {
        -1: "Fatal Error",
        1: "Invalid HF Code",
        2: "Duplicate Claim Code",
        3: "Invalid Insuree CHFID",
        4: "End date is smaller than start date",
        5: "Invalid ICDCode",
        6: "Claimed amount is 0",
        7: "Invalid ItemCode",
        8: "Invalid ServiceCode",
        9: "Invalid Claim Admin",
    }

    def __init__(self, code: int, msg: Optional[str] = None) -> None:
        self.code = code
        self.msg = ClaimSubmitError.ERROR_CODES.get(
            self.code, msg or "Unknown exception"
        )

    def __str__(self) -> str:
        return "ClaimSubmitError %s: %s" % (self.code, self.msg)


class ClaimSubmitService(object):
    def __init__(self, user: Any) -> None:
        self.user = user

    def hf_scope_check(self, claim_submit: ClaimSubmit) -> None:
        self._validate_user_hf(claim_submit.health_facility_code)

    @register_service_signal("claim.enter_and_submit_claim")
    @transaction.atomic
    def enter_and_submit(
        self, claim: Dict[str, Any], rule_engine_validation: bool = True
    ) -> Claim:
        create_claim_service = ClaimCreateService(self.user)
        entered_claim = create_claim_service.enter_claim(claim)
        submitted_claim, errors = self.submit_claim(
            entered_claim,
            rule_engine_validation,
            skip_hf_validation=True,
        )
        return submitted_claim

    @register_service_signal("claim.submit_claim")
    def submit_claim(
        self,
        claim: Claim,
        rule_engine_validation: bool = True,
        skip_hf_validation: bool = False,
    ) -> Tuple[Claim, List[Any]]:
        from claim.submission_pipeline import load_claim_for_submission

        self._validate_submit_permissions()
        claim = load_claim_for_submission(claim)
        if not skip_hf_validation:
            self._validate_user_hf(claim.health_facility.code)
        claim.save_history()
        validation_errors = processing_claim(
            claim, self.user, False, rule_engine_validation
        )
        if validation_errors:
            return self.__submit_to_rejected(claim), validation_errors

        return self.__submit_to_checked(claim), []

    def _validate_submit_permissions(self) -> None:
        if type(self.user) is AnonymousUser or not self.user.id:
            raise ValidationError(_("mutation.authentication_required"))
        if not self.user.has_perms(ClaimConfig.gql_mutation_submit_claims_perms):
            raise PermissionDenied(_("unauthorized"))

    def _validate_user_hf(self, hf_code: str) -> None:
        from location.models import HealthFacility, LocationManager

        hf = LocationManager().build_user_location_filter_query(
            self.user._u, queryset=HealthFacility.filter_queryset().filter(code=hf_code)
        )
        if not hf and settings.ROW_SECURITY:
            raise ClaimSubmitError(
                "Invalid health facility code or health facility not allowed for user"
            )

    def __submit_to_rejected(self, claim: Claim) -> Claim:
        apply_claim_status(claim, Claim.STATUS_REJECTED)
        claim.save()
        return claim

    def __submit_to_checked(self, claim: Claim) -> Claim:
        claim.approved = approved_amount(claim)
        apply_claim_status(claim, Claim.STATUS_CHECKED)
        from core.utils import TimeUtils

        claim.submit_stamp = TimeUtils.now()
        claim.category = get_claim_category(claim)
        claim.save()
        return claim


class ClaimCreateService:
    def __init__(self, user: Any) -> None:
        self.user = user

    def _validate_user_hf(self, hf_id: Optional[int]) -> None:
        from location.models import HealthFacility, LocationManager

        hf = LocationManager().build_user_location_filter_query(
            self.user._u, queryset=HealthFacility.filter_queryset().filter(id=hf_id)
        )
        if not hf and settings.ROW_SECURITY:
            raise ValidationError(
                "Invalid health facility code or health facility not allowed for user"
            )

    @register_service_signal("claim.enter_claim")
    def enter_claim(self, claim: Dict[str, Any]) -> Claim:
        self._validate_permissions()
        self._validate_claim_fields(claim)
        self._validate_user_hf(claim.get("health_facility_id", None))
        self._ensure_entered_claim_fields(claim)
        claim = self._create_claim_from_dict(claim)
        return claim

    def _validate_permissions(self) -> None:
        if type(self.user) is AnonymousUser or not self.user.id:
            raise ValidationError(_("mutation.authentication_required"))
        if not self.user.has_perms(ClaimConfig.gql_mutation_create_claims_perms):
            raise PermissionDenied(_("unauthorized"))

    def _validate_claim_fields(self, claim: Dict[str, Any]) -> None:
        if not claim.get("code"):
            raise ValidationError("Provided claim without code.")

        if Claim.objects.filter(code=claim["code"], validity_to__isnull=True).exists():
            raise ValidationError(f"Claim with code '{claim['code']}' already exists.")

    def _ensure_entered_claim_fields(self, claim_submit_data: Dict[str, Any]) -> None:
        claim_submit_data["audit_user_id"] = self.user.id_for_audit
        claim_submit_data["status"] = Claim.STATUS_ENTERED
        from core.utils import TimeUtils

        claim_submit_data["validity_from"] = TimeUtils.now()

    def _create_claim_from_dict(self, claim_submit_data: Dict[str, Any]) -> Claim:
        items = claim_submit_data.pop("items", [])
        services = claim_submit_data.pop("services", [])
        claim_submit_data.pop("service_item_set", [])
        claim_submit_data.pop("service_service_set", [])
        claim = Claim.objects.create(**claim_submit_data)
        self.__process_items(claim, items, services)
        claim.save()
        return claim

    def __process_items(
        self, claim: Claim, items: List[Any], services: List[Any]
    ) -> None:
        claimed = 0
        claimed += process_items_relations(self.user, claim, items)
        claimed += process_services_relations(self.user, claim, services)
        claim.claimed = claimed


def submit_claim(claim: Claim, user: Any) -> List[Any]:
    return ClaimSubmitService(user).submit_claim(claim, user)[1]
