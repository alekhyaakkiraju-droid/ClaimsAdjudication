"""Deductible and remuneration processing."""

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.db.models import Q
from django.utils.translation import gettext as _

from claim.apps import ClaimConfig
from claim.models import (
    Claim,
    ClaimDedRem,
    ClaimItem,
    ClaimService,
    ClaimServiceItem,
    ClaimServiceService,
)
from claim.state_machine import apply_claim_status
from claim.utils import get_claim_target_date, get_queryset_valid_at_date, get_valid_policies_qs
from claim.validations.constants import (
    Deductible,
    REJECTION_REASON_NO_COVERAGE,
    REJECTION_REASON_NO_PRODUCT_FOUND,
)
from claim.validations.category import get_claim_category
from core.datetimes.shared import datetimedelta
from medical.models import Service, ServiceItem, ServiceService
from medical_pricelist.models import ItemsPricelistDetail, ServicesPricelistDetail
from policy.models import Policy
from product.models import Product, ProductItem, ProductItemOrService, ProductService

logger = logging.getLogger(__name__)


def initialize_dedrem_processing(claim, services):
    """Initialize basic claim processing parameters."""
    errors = []
    logger.debug(f"processing dedrem for claim {claim.uuid}")
    target_date = get_claim_target_date(claim)
    category = get_claim_category(claim, services)
    hospitalization = claim.date_from != target_date
    hf_level = claim.health_facility.level
    return errors, target_date, category, hospitalization, hf_level


def archive_old_dedrems(claim):
    """Archive existing dedrems for the claim."""
    ClaimDedRem.objects.filter(claim_id=claim.id, *ClaimDedRem.filter_validity()).update(
        validity_to=datetime.now()
    )


def fetch_policies(claim, target_date, policies=None):
    """Retrieve valid policies if not provided."""
    if not policies:
        policies = list(
            get_valid_policies_qs(claim.insuree.id, target_date).prefetch_related(
                "product"
            )
        )
    if not policies:
        logger.warning(f"No valid policies found for claim {claim.uuid}")
        apply_claim_status(claim, Claim.STATUS_REJECTED)
        claim.rejection_reason = REJECTION_REASON_NO_COVERAGE
        claim.save()
        return None
    return policies


def fetch_items_and_services(claim, items=None, services=None):
    """Retrieve claim items and services if not provided."""
    if items is None:
        items = list(
            claim.items.filter(
                item__isnull=False,
                validity_to__isnull=True,
            ).filter(Q(Q(rejection_reason=0) | Q(rejection_reason__isnull=True)))
        )
    if services is None:
        services = list(
            claim.services.filter(
                service__isnull=False,
                validity_to__isnull=True,
            ).filter(Q(Q(rejection_reason=0) | Q(rejection_reason__isnull=True)))
        )
    return items, services


def get_policy_and_product_info(policies, items, services):
    """Extract policy and product information from provided items and services."""

    policies_id = list(
        set(
            (
                *[s.policy_id for s in services if s.policy_id is not None],
                *[i.policy_id for i in items if i.policy_id is not None],
            )
        )
    )
    products_id = list(
        set(
            (
                *[s.product_id for s in services if s.product_id is not None],
                *[i.product_id for i in items if i.product_id is not None],
            )
        )
    )
    if policies and not policies_id:
        policies_id = [p.id for p in policies]
        products_id = [p.product_id for p in policies]

    return policies_id, products_id


def calculate_hospital_visit(product, hospitalization, hf_level):
    return (
        product.ceiling_interpretation == Product.CEILING_INTERPRETATION_IN_PATIENT
        and hospitalization
    ) or (
        product.ceiling_interpretation == Product.CEILING_INTERPRETATION_HOSPITAL
        and hf_level == "H"
    )


def get_policy_members(policy_id, target_date):
    """Count policy members."""
    return Policy.objects.filter(
        id=policy_id,
        effective_date__lte=target_date,
        expiry_date__gte=target_date,
        validity_to__isnull=True,
    ).count()


def initialize_deductibles_and_ceilings():
    """Initialize deductible and ceiling tracking variables."""
    return {
        "deductible": None,
        "ceiling": None,
        "prev_deductible": None,
        "prev_remunerated": 0,
        "prev_remunerated_consult": 0,
        "prev_remunerated_surgery": 0,
        "prev_remunerated_hospitalization": 0,
        "prev_remunerated_delivery": 0,
        "prev_remunerated_antenatal": 0,
        "remunerated_consultation": 0,
        "remunerated_surgery": 0,
        "remunerated_hospitalization": 0,
        "remunerated_delivery": 0,
        "remunerated_antenatal": 0,
        "relative_prices": False,
        "deducted": 0,
        "remunerated": 0,
    }


def fetch_previous_dedrems(claim, policy_id):
    """Retrieve previous dedrems excluding current claim."""
    return list(
        ClaimDedRem.objects.filter(policy_id=policy_id).exclude(claim_id=claim.id)
    )


def calculate_deductibles_and_ceilings(
    product, claim, demrems, hospital_visit, policy_members
):
    deductibles = initialize_deductibles_and_ceilings()
    ded_g = _get_dedrem("ded", "G", "ded_g", product, claim.insuree, demrems)
    if ded_g:
        deductibles["deductible"] = ded_g
        deductibles["prev_deductible"] = ded_g.prev
    rem_g = _get_dedrem("max", "G", "rem_g", product, claim.insuree, demrems)
    if rem_g:
        deductibles["ceiling"] = rem_g
        deductibles["prev_remunerated"] = rem_g.prev
    if product.max_policy:
        if policy_members > product.threshold:
            if product.max_policy_extra_member:
                deductibles["ceiling"] = Deductible(
                    product.max_policy
                    + (policy_members - product.threshold)
                    * product.max_policy_extra_member,
                    deductibles["ceiling"].type,
                    deductibles["ceiling"].prev,
                )
            if (
                product.max_ceiling_policy
                and deductibles["ceiling"].amount > product.max_ceiling_policy
            ):
                deductibles["ceiling"] = Deductible(
                    product.max_ceiling_policy,
                    deductibles["ceiling"].type,
                    deductibles["ceiling"].prev,
                )
        else:
            deductibles["ceiling"] = Deductible(
                product.max_policy,
                deductibles["ceiling"].type,
                deductibles["ceiling"].prev,
            )
    if not deductibles["deductible"]:
        if hospital_visit:
            ded_ip = _get_dedrem(
                "ded_ip", "I", "ded_ip", product, claim.insuree, demrems
            )
            if ded_ip:
                deductibles["deductible"] = ded_ip
                deductibles["prev_deductible"] = ded_ip.prev
        else:
            ded_op = _get_dedrem(
                "ded_op", "O", "ded_op", product, claim.insuree, demrems
            )
            if ded_op:
                deductibles["deductible"] = ded_op
                deductibles["prev_deductible"] = ded_op.prev
    if not deductibles["ceiling"]:
        if hospital_visit:
            max_ip = _get_dedrem(
                "max_ip", "I", "rem_ip", product, claim.insuree, demrems
            )
            if max_ip:
                deductibles["ceiling"] = max_ip
                deductibles["prev_remunerated"] = max_ip.prev
            if product.max_ip_policy:
                if policy_members > product.threshold:
                    if product.max_policy_extra_member_ip:
                        deductibles["ceiling"] = Deductible(
                            product.max_ip_policy
                            + (policy_members - product.threshold)
                            * product.max_policy_extra_member_ip,
                            deductibles["ceiling"].type,
                            deductibles["ceiling"].prev,
                        )
                    if (
                        product.max_ceiling_policy_ip
                        and deductibles["ceiling"].amount
                        > product.max_ceiling_policy_ip
                    ):
                        deductibles["ceiling"] = Deductible(
                            product.max_ceiling_policy_ip,
                            deductibles["ceiling"].type,
                            deductibles["ceiling"].prev,
                        )
                else:
                    deductibles["ceiling"] = Deductible(
                        product.max_ip_policy,
                        deductibles["ceiling"].type,
                        deductibles["ceiling"].prev,
                    )
        else:
            max_op = _get_dedrem(
                "max_op", "O", "rem_op", product, claim.insuree, demrems
            )
            if max_op:
                deductibles["ceiling"] = max_op
                deductibles["prev_remunerated"] = max_op.prev
            if product.max_op_policy:
                if product.threshold and policy_members > product.threshold:
                    if product.max_policy_extra_member_op:
                        deductibles["ceiling"] = Deductible(
                            product.max_op_policy
                            + (policy_members - product.threshold)
                            * product.max_policy_extra_member_op,
                            deductibles["ceiling"].type,
                            deductibles["ceiling"].prev,
                        )
                    if (
                        product.max_ceiling_policy_op
                        and deductibles["ceiling"].amount
                        > product.max_ceiling_policy_op
                    ):
                        deductibles["ceiling"] = Deductible(
                            product.max_ceiling_policy_op,
                            deductibles["ceiling"].type,
                            deductibles["ceiling"].prev,
                        )
                else:
                    deductibles["ceiling"] = Deductible(
                        product.max_op_policy,
                        deductibles["ceiling"].type,
                        deductibles["ceiling"].prev,
                    )
    return deductibles


def get_pricelist_detail(claim, claim_detail, target_date, detail_is_item):
    """Fetch pricelist detail for item or service."""
    pricelist_detail_qs = (
        ItemsPricelistDetail if detail_is_item else ServicesPricelistDetail
    ).objects.filter(
        itemsvcs_pricelist=(
            claim.health_facility.items_pricelist
            if detail_is_item
            else claim.health_facility.services_pricelist
        ),
        itemsvc=claim_detail.itemsvc,
        itemsvcs_pricelist__validity_to__isnull=True,
    )
    return get_queryset_valid_at_date(pricelist_detail_qs, target_date).first()


def get_product_itemsvc(claim_detail, detail_is_item, tuple_dict=None):
    if tuple_dict is None:
        if detail_is_item:
            product_itemsvc = ProductItem.objects.filter(
                product_id=claim_detail.product_id,
                item_id=claim_detail.item_id,
                validity_to__isnull=True,
            ).first()
        else:
            product_itemsvc = ProductService.objects.filter(
                product_id=claim_detail.product_id,
                service_id=claim_detail.service_id,
                validity_to__isnull=True,
            ).first()
    else:
        product_itemsvc = tuple_dict.get(
            (
                claim_detail.product_id,
                claim_detail.item_id if detail_is_item else claim_detail.service_id,
            )
        )
    if product_itemsvc is None:
        raise ValueError(f"Product {'Item' if detail_is_item else 'Service'} not found")
    return product_itemsvc


def calculate_price_adjusted(
    claim, claim_detail, itemsvc_pricelist_detail, detail_is_item
):
    """Calculate adjusted price for claim detail."""
    pl_price = (
        itemsvc_pricelist_detail.price_overrule
        if itemsvc_pricelist_detail.price_overrule
        else claim_detail.itemsvc.price
    )
    if claim_detail.price_approved is not None:
        return claim_detail.price_approved
    if claim_detail.price_origin == ProductItemOrService.ORIGIN_CLAIM:
        set_price_adjusted = claim_detail.price_asked
        if ClaimConfig.verify_quantities and not detail_is_item:
            service_price = None
            if claim_detail.service.packagetype == "F":
                service_price = claim_detail.service.price
            if (
                service_price
                and (claim_detail.price_adjusted or claim_detail.price_asked)
                > service_price
            ):
                return service_price
        return set_price_adjusted
    set_price_adjusted = pl_price
    if ClaimConfig.verify_quantities and not detail_is_item:
        set_price_adjusted = verify_service_quantities(claim_detail, set_price_adjusted)
    return set_price_adjusted


def verify_service_quantities(claim_detail, set_price_adjusted):
    """Verify service quantities for package services."""
    continue_service_check = True
    if claim_detail.service.packagetype == "P":
        service_services = ServiceService.objects.filter(
            parent=claim_detail.service.id
        ).all()
        claim_service_services = ClaimServiceService.objects.filter(
            claim_service=claim_detail.id
        ).all()
        if len(service_services) == len(claim_service_services):
            for servservice in service_services:
                for claimserviceservice in claim_service_services:
                    if servservice.service.id == claimserviceservice.service.id:
                        if (
                            servservice.qty_provided
                            != claimserviceservice.qty_displayed
                        ):
                            return 0
                if not continue_service_check:
                    break
        else:
            return 0
        continue_item_check = True
        service_items = ServiceItem.objects.filter(parent=claim_detail.service.id).all()
        claim_service_items = ClaimServiceItem.objects.filter(
            claim_service=claim_detail.id
        ).all()
        if len(service_items) == len(claim_service_items):
            for serviceitem in service_items:
                for claimservicesitem in claim_service_items:
                    if serviceitem.item.id == claimservicesitem.item.id:
                        if serviceitem.qty_provided != claimservicesitem.qty_displayed:
                            return 0
                if not continue_item_check:
                    break
        else:
            return 0
    return set_price_adjusted


def process_claim_detail(
    claim,
    claim_detail,
    product_data,
    deductibles,
    category,
    hospital_visit,
    product_itemsvc,
    set_price_adjusted,
    itemsvc_quantity,
):
    """Process individual claim item or service."""
    work_value = int(itemsvc_quantity * set_price_adjusted)
    set_unit_price_adjusted = set_price_adjusted
    set_price_deducted = 0
    exceed_ceiling_amount = 0
    exceed_ceiling_amount_category = 0
    if (
        claim_detail.limitation == ProductItemOrService.LIMIT_FIXED_AMOUNT
        and claim_detail.limitation_value
        and (itemsvc_quantity * claim_detail.limitation_value) < work_value
    ):
        work_value = itemsvc_quantity * claim_detail.limitation_value
    if (
        deductibles["deductible"]
        and deductibles["deductible"].amount
        - deductibles["prev_deductible"]
        - deductibles["deducted"]
        > 0
    ):
        if (
            deductibles["deductible"].amount
            - deductibles["deductible"].prev
            - deductibles["deducted"]
            >= work_value
        ):
            set_price_deducted = work_value
            deductibles["deducted"] += work_value
            set_price_approved = 0
            set_price_remunerated = 0
        else:
            set_price_deducted = (
                deductibles["deductible"].amount
                - deductibles["deductible"].prev
                - deductibles["deducted"]
            )
            work_value -= set_price_deducted
            deductibles["deducted"] += (
                deductibles["deductible"].amount
                - deductibles["deductible"].prev
                - deductibles["deducted"]
            )
    if (
        claim_detail.limitation == ProductItemOrService.LIMIT_CO_INSURANCE
        and claim_detail.limitation_value
    ):
        work_value = claim_detail.limitation_value / 100 * work_value
    work_value, exceed_ceiling_amount_category = apply_category_ceilings(
        product_data, category, work_value, deductibles
    )
    set_price_approved, set_price_remunerated, exceed_ceiling_amount = (
        apply_ceiling_exclusions(
            claim,
            claim_detail,
            product_itemsvc,
            hospital_visit,
            work_value,
            deductibles,
        )
    )
    return {
        "set_price_deducted": set_price_deducted,
        "set_price_approved": set_price_approved,
        "set_price_remunerated": set_price_remunerated,
        "exceed_ceiling_amount": exceed_ceiling_amount,
        "exceed_ceiling_amount_category": exceed_ceiling_amount_category,
        "set_unit_price_adjusted": set_unit_price_adjusted,
        "work_value": work_value,
    }


def apply_category_ceilings(product, category, work_value, deductibles):
    """Apply category-specific ceilings."""
    exceed_ceiling_amount_category = 0
    category_checks = {
        Service.CATEGORY_SURGERY: (
            product.max_amount_surgery,
            "remunerated_surgery",
            "prev_remunerated_surgery",
        ),
        Service.CATEGORY_DELIVERY: (
            product.max_amount_delivery,
            "remunerated_delivery",
            "prev_remunerated_delivery",
        ),
        Service.CATEGORY_ANTENATAL: (
            product.max_amount_antenatal,
            "remunerated_antenatal",
            "prev_remunerated_antenatal",
        ),
        Service.CATEGORY_HOSPITALIZATION: (
            product.max_amount_hospitalization,
            "remunerated_hospitalization",
            "prev_remunerated_hospitalization",
        ),
        Service.CATEGORY_CONSULTATION: (
            product.max_amount_consultation,
            "remunerated_consultation",
            "prev_remunerated_consult",
        ),
    }
    if category != Service.CATEGORY_VISIT and category in category_checks:
        max_amount, remunerated_key, prev_remunerated_key = category_checks[category]
        if max_amount:
            total_remunerated = (
                work_value
                + deductibles[prev_remunerated_key]
                + deductibles[remunerated_key]
            )
            if total_remunerated <= max_amount:
                deductibles[remunerated_key] += work_value
            else:
                if (
                    deductibles[prev_remunerated_key] + deductibles[remunerated_key]
                    >= max_amount
                ):
                    exceed_ceiling_amount_category = work_value
                    work_value = 0
                else:
                    exceed_ceiling_amount_category = total_remunerated - max_amount
                    work_value -= exceed_ceiling_amount_category
                    deductibles[remunerated_key] += work_value
    return work_value, exceed_ceiling_amount_category


def apply_ceiling_exclusions(
    claim, claim_detail, product_itemsvc, hospital_visit, work_value, deductibles
):
    """Apply ceiling exclusions based on patient type and visit type."""
    exceed_ceiling_amount = 0
    set_price_approved = work_value
    set_price_remunerated = work_value
    if product_itemsvc and (
        (
            claim.insuree.is_adult
            and hospital_visit
            and product_itemsvc.ceiling_exclusion_adult in ("B", "H")
        )
        or (
            claim.insuree.is_adult
            and not hospital_visit
            and product_itemsvc.ceiling_exclusion_adult in ("B", "N")
        )
        or (
            not claim.insuree.is_adult
            and hospital_visit
            and product_itemsvc.ceiling_exclusion_child in ("B", "H")
        )
        or (
            not claim.insuree.is_adult
            and not hospital_visit
            and product_itemsvc.ceiling_exclusion_child in ("B", "N")
        )
    ):
        exceed_ceiling_amount = 0
    else:
        if deductibles["ceiling"] and deductibles["ceiling"].amount > 0:
            remaining_ceiling = (
                deductibles["ceiling"].amount
                - deductibles["prev_remunerated"]
                - deductibles["remunerated"]
            )
            if remaining_ceiling > 0:
                if remaining_ceiling >= work_value:
                    deductibles["remunerated"] += work_value
                else:
                    exceed_ceiling_amount = work_value - remaining_ceiling
                    set_price_approved = remaining_ceiling
                    set_price_remunerated = remaining_ceiling
                    deductibles["remunerated"] += remaining_ceiling
            else:
                exceed_ceiling_amount = work_value
                set_price_approved = 0
                set_price_remunerated = 0
        else:
            deductibles["remunerated"] += work_value
    return set_price_approved, set_price_remunerated, exceed_ceiling_amount


def update_claim_detail(claim_detail, is_process, result, relative_prices):
    """Update claim detail with processed values."""
    if claim_detail.price_approved is None:
        claim_detail.price_adjusted = result["set_unit_price_adjusted"]
    if is_process:
        if claim_detail.price_origin == ProductItemOrService.ORIGIN_RELATIVE:
            claim_detail.price_valuated = None
            claim_detail.deductable_amount = result["set_price_deducted"]
            claim_detail.exceed_ceiling_amount = result["exceed_ceiling_amount"]
            relative_prices = True
        else:
            claim_detail.price_valuated = result["set_price_approved"]
            claim_detail.deductable_amount = result["set_price_deducted"]
            claim_detail.exceed_ceiling_amount = result["exceed_ceiling_amount"]
            claim_detail.remunerated_amount = result["set_price_remunerated"]
    claim_detail.save()
    return relative_prices


def create_claim_dedrem(claim, policy, user, deductibles, hospital_visit):
    """Create new ClaimDedRem record."""
    now = datetime.now()
    claim_ded_rem_to_create = {
        "policy": policy,
        "insuree": claim.insuree,
        "claim": claim,
        "ded_g": deductibles["deducted"],
        "rem_g": deductibles["remunerated"],
        "rem_consult": deductibles["remunerated_consultation"],
        "rem_hospitalization": deductibles["remunerated_hospitalization"],
        "rem_delivery": deductibles["remunerated_delivery"],
        "rem_antenatal": deductibles["remunerated_antenatal"],
        "rem_surgery": deductibles["remunerated_surgery"],
        "audit_user_id": getattr(user, "id_for_audit", -1),
        "validity_from": now,
    }
    if hospital_visit:
        claim_ded_rem_to_create["ded_ip"] = deductibles["deducted"]
        claim_ded_rem_to_create["rem_ip"] = deductibles["remunerated"]
    else:
        claim_ded_rem_to_create["ded_op"] = deductibles["deducted"]
        claim_ded_rem_to_create["rem_op"] = deductibles["remunerated"]
    ClaimDedRem.objects.create(**claim_ded_rem_to_create)


def update_claim_status(claim, is_process, deductibles, user, products_id):
    """Update final claim status and related fields."""
    now = datetime.now()
    if not deductibles:
        logger.warning(
            f"claim {claim.uuid} did not have any item or service to valuate."
        )
        apply_claim_status(claim, Claim.STATUS_REJECTED)
        return [
            {
                "code": REJECTION_REASON_NO_PRODUCT_FOUND,
                "message": _("claim.validation.assign_prod.elt.no_product_code")
                % {"code": claim.code, "element": "all"},
                "detail": claim.uuid,
            }
        ]
    elif is_process:
        claim.approved = deductibles["remunerated"]
        if deductibles["relative_prices"]:
            apply_claim_status(claim, Claim.STATUS_PROCESSED)
            claim.remunerated = None
        else:
            apply_claim_status(claim, Claim.STATUS_VALUATED)
            claim.remunerated = deductibles["remunerated"]
        claim.audit_user_id_process = getattr(user, "id_for_audit", -1)
        claim.process_stamp = now
        claim.date_processed = now
        from claim.feedback_review_state_machine import (
            apply_feedback_status,
            apply_review_status,
        )

        if claim.feedback_status == Claim.FEEDBACK_SELECTED:
            apply_feedback_status(claim, Claim.FEEDBACK_BYPASSED)
        if claim.review_status == Claim.REVIEW_SELECTED:
            apply_review_status(claim, Claim.REVIEW_BYPASSED)
    if not products_id:
        logger.warning(f"claim {claim.uuid} is not covered by any product.")
        apply_claim_status(claim, Claim.STATUS_REJECTED)
        return [
            {
                "code": REJECTION_REASON_NO_PRODUCT_FOUND,
                "message": _("claim.validation.product_family.no_item_or_service")
                % {"code": claim.code, "element": "all"},
                "detail": claim.uuid,
            }
        ]
    claim.save()
    return []


def process_dedrem(
    claim,
    user=None,
    is_process=False,
    policies=None,
    items=None,
    services=None,
    item_product_data=None,
    service_product_data=None,
    product_item_tuple_dict=None,
    product_service_tuple_dict=None,
    root_services=None,
):
    errors, target_date, category, hospitalization, hf_level = (
        initialize_dedrem_processing(claim, root_services)
    )
    archive_old_dedrems(claim)
    policies = fetch_policies(claim, target_date, policies)
    if not policies:
        return [
            {
                "code": REJECTION_REASON_NO_COVERAGE,
                "message": _("claim.validation.family.no_policy")
                % {"code": claim.code, "insuree": str(claim.insuree)},
                "detail": claim.uuid,
            }
        ]
    items, services = fetch_items_and_services(claim, items, services)
    policies_id, products_id = get_policy_and_product_info(policies, items, services)
    claim_deductibles = {}
    if item_product_data is None:
        item_ids = [item.item_id for item in items]
        item_product_data = get_product_items_services(
            target_date,
            item_ids,
            claim.insuree_id,
            claim.insuree.is_adult(target_date),
            "Item",
            set(p.product_id for p in policies),
            policies,
        )
    if service_product_data is None:
        service_ids = [service.service_id for service in services]
        service_product_data = get_product_items_services(
            target_date,
            service_ids,
            claim.insuree_id,
            claim.insuree.is_adult(target_date),
            "Service",
            set(p.product_id for p in policies),
            policies,
        )

    if product_item_tuple_dict is None:
        product_item_tuple_dict = {}
        for data in item_product_data.values():
            for d in data:
                pi = d["prod_item_svc"]
                product_item_tuple_dict[(pi.product.id, pi.item.id)] = pi
    if product_service_tuple_dict is None:
        product_service_tuple_dict = {}
        for data in service_product_data.values():
            for d in data:
                ps = d["prod_item_svc"]
                product_service_tuple_dict[(ps.product.id, ps.service.id)] = ps
    for policy_id in policies_id:
        policy = next((p for p in policies if p.id == policy_id), None)
        if not policy:
            continue
        product = policy.product
        hospital_visit = calculate_hospital_visit(product, hospitalization, hf_level)
        policy_members = get_policy_members(policy_id, target_date)
        demrems = fetch_previous_dedrems(claim, policy_id)
        deductibles = calculate_deductibles_and_ceilings(
            product, claim, demrems, hospital_visit, policy_members
        )
        itmsrv = [*items, *services]
        for claim_detail in itmsrv:
            if claim_detail.status not in [
                ClaimItem.STATUS_PASSED,
                ClaimService.STATUS_PASSED,
            ]:
                continue
            detail_is_item = isinstance(claim_detail, ClaimItem)
            itemsvc_quantity = claim_detail.qty_approved or claim_detail.qty_provided
            itemsvc_pricelist_detail = get_pricelist_detail(
                claim, claim_detail, target_date, detail_is_item
            )
            product_itemsvc = get_product_itemsvc(
                claim_detail,
                detail_is_item,
                (
                    product_item_tuple_dict
                    if detail_is_item
                    else product_service_tuple_dict
                ),
            )
            set_price_adjusted = calculate_price_adjusted(
                claim, claim_detail, itemsvc_pricelist_detail, detail_is_item
            )
            result = process_claim_detail(
                claim,
                claim_detail,
                product,
                deductibles,
                category,
                hospital_visit,
                product_itemsvc,
                set_price_adjusted,
                itemsvc_quantity,
            )
            deductibles["relative_prices"] = update_claim_detail(
                claim_detail, is_process, result, deductibles["relative_prices"]
            )
        create_claim_dedrem(claim, policy, user, deductibles, hospital_visit)
        merge_deductible(claim_deductibles, deductibles)
    errors.extend(
        update_claim_status(claim, is_process, claim_deductibles, user, products_id)
    )
    return errors


def merge_deductible(claim_deductibles, deductibles):
    for k in deductibles.keys():
        data = deductibles[k]
        if k in claim_deductibles:
            if isinstance(data, bool):
                claim_deductibles[k] = claim_deductibles[k] & deductibles[k]
            elif isinstance(data, (int, float, Decimal)):
                claim_deductibles[k] = claim_deductibles[k] + deductibles[k]
            else:
                claim_deductibles[k].append(deductibles[k])
        else:
            if isinstance(data, (bool, int, float, Decimal)):
                claim_deductibles[k] = deductibles[k]
            else:
                claim_deductibles[k] = [deductibles[k]]


def get_product_items_services(
    target_date, elt_ids, insuree_id, adult, item_or_service, product_ids, policies
):
    if not elt_ids:
        return {}
    if item_or_service == "Item":
        model = ProductItem
        field = "item"
    else:
        model = ProductService
        field = "service"
    qs = model.objects.filter(
        validity_to__isnull=True,
        product_id__in=product_ids,
        **{f"{field}_id__in": elt_ids},
    ).select_related("product", f"{field}")
    data_by_elt = defaultdict(list)
    policies_by_product = defaultdict(list)
    for p in policies:
        policies_by_product[p.product_id].append(p)
    for obj in qs:
        elt_id = getattr(obj, f"{field}_id")
        for policy in policies_by_product[obj.product_id]:
            data_by_elt[elt_id].append(
                {
                    "prod_item_svc": obj,
                    "insuree_policy_effective_date": policy.effective_date,
                    "policy_effective_date": policy.effective_date,
                    "expiry_date": policy.expiry_date,
                    "policy_stage": policy.stage,
                    "waiting_period": getattr(
                        obj, "waiting_period_adult" if adult else "waiting_period_child"
                    )
                    or 0,
                }
            )
    for elt_id in data_by_elt:
        data_by_elt[elt_id].sort(
            key=lambda d: d["policy_effective_date"]
            + datetimedelta(months=d["waiting_period"])
        )
    return data_by_elt


def _get_dedrem(prefix, dedrem_type, field, product, insuree, demrems):
    if getattr(product, prefix + "_treatment", None):
        return Deductible(getattr(product, prefix + "_treatment", None), dedrem_type, 0)
    if getattr(product, prefix + "_insuree", None):
        prev = sum(
            [getattr(dr, field, 0) for dr in demrems if dr.insuree_id == insuree.id]
        )
        return Deductible(
            getattr(product, prefix + "_insuree", None),
            dedrem_type,
            prev if prev else 0,
        )
    if getattr(product, prefix + "_policy", None):
        prev = sum([getattr(dr, field, 0) for dr in demrems])
        return Deductible(
            getattr(product, prefix + "_policy", None), dedrem_type, prev if prev else 0
        )
    return None
