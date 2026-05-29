"""Claim validation orchestration and element rules."""
# flake8: noqa

import logging
from collections import defaultdict
from decimal import Decimal

from claim.state_machine import apply_claim_status
from claim.models import (
    ClaimItem,
    Claim,
    ClaimService,
    ClaimDetail,
    ClaimServiceService,
    ClaimServiceItem,
)
from core import utils
from datetime import datetime
from core.datetimes.shared import datetimedelta
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils.translation import gettext as _
from medical.models import Service, ServiceService, ServiceItem
from medical_pricelist.models import ItemsPricelistDetail, ServicesPricelistDetail
from policy.models import Policy
from product.models import Product, ProductItem, ProductService, ProductItemOrService
from claim.apps import ClaimConfig
from claim.utils import (
    get_queryset_valid_at_date,
    get_valid_policies_qs,
    get_claim_target_date,
)
from claim.validations.constants import *
from claim.validations.category import get_claim_category
from claim.validations.dedrem import (
    fetch_items_and_services,
    fetch_policies,
    get_product_items_services,
    process_dedrem,
)

logger = logging.getLogger(__name__)

def validate_assign_prod_to_claimitems_and_services(
    claim,
    policies=None,
    services=None,
    items=None,
    product_items_by_item_id=None,
    product_services_by_service_id=None,
    target_date=None,
):
    errors = []
    if not policies:
        policies = get_valid_policies_qs(claim.insuree.id, target_date)
    logger.debug(
        "[claim: %s] validate_assign_prod_to_claimitems_and_services", claim.uuid
    )
    if items is None:
        items = list(
            claim.items.filter(validity_to__isnull=True).filter(
                Q(rejection_reason=0) | Q(rejection_reason__isnull=True)
            )
        )
    if services is None:
        services = list(
            claim.services.filter(validity_to__isnull=True).filter(
                Q(rejection_reason=0) | Q(rejection_reason__isnull=True)
            )
        )
    for claimitem in [i for i in items if not i.rejection_reason]:
        logger.debug("[claim: %s] validating item %s", claim.uuid, claimitem.id)
        elt_qs = product_items_by_item_id.get(
            claimitem.item_id,
            ProductItem.objects.filter(
                item_id=claimitem.item_id, product__in=[p.product for p in policies]
            ),
        )
        errors += validate_assign_prod_elt(
            claim,
            claimitem,
            claimitem.item,
            elt_qs,
            target_date=target_date,
            policies=policies,
        )
    for claimservice in [s for s in services if not s.rejection_reason]:
        logger.debug("[claim: %s] validating service %s", claim.uuid, claimservice.id)
        elt_qs = product_services_by_service_id.get(
            claimservice.service_id,
            ProductService.objects.filter(
                service_id=claimservice.service_id,
                product__in=[p.product for p in policies],
            ),
        )
        errors += validate_assign_prod_elt(
            claim,
            claimservice,
            claimservice.service,
            elt_qs,
            target_date=target_date,
            policies=policies,
        )
    logger.debug(
        "[claim: %s] validate_assign_prod_to_claimitems_and_services nb of errors %s",
        claim.uuid,
        len(errors),
    )
    return errors


def validate_assign_prod_elt(claim, elt, elt_ref, elt_qs, target_date, policies=None):
    visit_type_field = {
        "O": ("limitation_type", "limit_adult", "limit_child"),
        "E": ("limitation_type_e", "limit_adult_e", "limit_child_e"),
        "R": ("limitation_type_r", "limit_adult_r", "limit_child_r"),
    }
    logger.debug(
        "[claim: %s] Assigning product for %s %s", claim.uuid, type(elt), elt.id
    )
    visit_type = (
        claim.visit_type
        if claim.visit_type and claim.visit_type in visit_type_field
        else "O"
    )
    adult = claim.insuree.is_adult(target_date)
    (limitation_type_field, limit_adult, limit_child) = visit_type_field[visit_type]
    claim_price = elt.price_approved or elt.price_adjusted or elt.price_asked or 0
    logger.debug("[claim: %s] claim_price: %s", claim.uuid, claim_price)
    logger.debug(
        "[claim: %s] Checking product itemsvc limit at date %s with field %s C for adult: %s",
        claim.uuid,
        target_date,
        limitation_type_field,
        adult,
    )
    limit_ordering = limit_adult if adult else limit_child
    product_elt_c = _query_product_item_service_limit(
        target_date, elt_qs, limitation_type_field, "C", limit_ordering
    )
    product_elt_f = _query_product_item_service_limit(
        target_date, elt_qs, limitation_type_field, "F", limit_ordering
    )
    if not product_elt_c and not product_elt_f:
        elt.rejection_reason = REJECTION_REASON_NO_PRODUCT_FOUND
        elt.save()
        return [
            {
                "code": REJECTION_REASON_NO_PRODUCT_FOUND,
                "message": _("claim.validation.assign_prod.elt.no_product_code")
                % {"code": claim.code, "elt": str(elt_ref)},
                "detail": claim.uuid,
            }
        ]
    if product_elt_f:
        fixed_limit = getattr(product_elt_f, limit_ordering)
        logger.debug("[claim: %s] fixed_limit: %s", claim.uuid, fixed_limit)
    else:
        fixed_limit = None
    if product_elt_c:
        co_sharing_percent = getattr(product_elt_c, limit_ordering)
        logger.debug(
            "[claim: %s] co_sharing_percent: %s", claim.uuid, co_sharing_percent
        )
    else:
        co_sharing_percent = None
    product_elt = find_best_product_etl(
        product_elt_c, product_elt_f, fixed_limit, claim_price, co_sharing_percent
    )
    if product_elt is None:
        logger.warning(f"Could not find a suitable product from {type(elt)} {elt.id}")
    if product_elt.product is None:
        logger.warning(
            f"Found a productItem/Service for {type(elt)} {elt.id} but it does not have a product"
        )
    logger.debug("[claim: %s] product_id found: %s", claim.uuid, product_elt.product.id)
    elt.product = product_elt.product
    logger.debug(
        "[claim: %s] fetching policy for family %s", claim.uuid, claim.insuree.family_id
    )
    elt.policy = next(
        iter([p for p in policies if p.product == product_elt.product]), None
    )
    if elt.policy is None:
        logger.warning(
            f"{type(elt)} id {elt.id} doesn't seem to have a valid policy with product"
            f" {product_elt.product.id}"
        )
    logger.debug(
        "[claim: %s] setting policy %s",
        claim.uuid,
        elt.policy.id if elt.policy else None,
    )
    elt.price_origin = product_elt.price_origin
    if product_elt_c:
        elt.limitation = "C"
        elt.limitation_value = co_sharing_percent
    else:
        elt.limitation = "F"
        elt.limitation_value = fixed_limit
    logger.debug(
        "[claim: %s] setting limitation %s to %s",
        claim.uuid,
        elt.limitation,
        elt.limitation_value,
    )
    elt.save()
    return []


def _query_product_item_service_limit(
    target_date, elt_qs, limitation_field, limitation_type, limit_ordering
):
    pdt_elt = max(
        (pd for pd in elt_qs if getattr(pd, limitation_field) == limitation_type),
        key=lambda pd: getattr(pd, limit_ordering) or Decimal(0),
        default=None,
    )
    logger.debug(
        "product found: %s, checking product itemsvc limit at date %s "
        "with field %s (%s)",
        pdt_elt is not None,
        target_date,
        limitation_field,
        limitation_type,
    )
    return pdt_elt


def find_best_product_etl(
    product_elt_c, product_elt_f, fixed_limit, claim_price, co_sharing_percent
):
    if product_elt_c and product_elt_f:
        if fixed_limit == 0 or fixed_limit > claim_price:
            product_elt = product_elt_f
            product_elt_c = None
        else:
            if 100 - co_sharing_percent > 0:
                product_amount_own_f = claim_price - fixed_limit
                product_amount_own_c = (1 - co_sharing_percent / 100) * claim_price
                if product_amount_own_c > product_amount_own_f:
                    product_elt = product_elt_f
                    product_elt_c = None
                else:
                    product_elt = product_elt_c
            else:
                product_elt = product_elt_c
    else:
        if product_elt_c:
            product_elt = product_elt_c
        else:
            product_elt = product_elt_f
            product_elt_c = None
    return product_elt


def validate_claim(claim, check_max, process_dedrem_opt=True, policies=None, is_process=None, user=None):
    logger.debug(f"Validating claim {claim.uuid}")
    if ClaimConfig.default_validations_disabled:
        return []
    errors = []
    detail_errors = []
    errors += validate_target_date(claim)
    if len(errors) == 0:
        target_date = get_claim_target_date(claim)
        if not policies:
            policies = list(get_valid_policies_qs(claim.insuree_id, target_date))
        items, services = fetch_items_and_services(claim)
        errors += validate_insuree(claim, claim.insuree, policies)
        item_ids = [item.item_id for item in items]
        service_ids = [service.service_id for service in services]
        item_pricelist_dict = {
            pd.item_id: pd
            for pd in ItemsPricelistDetail.objects.filter(
                item_id__in=item_ids,
                items_pricelist=claim.health_facility.items_pricelist,
                items_pricelist__validity_to__isnull=True,
                *ItemsPricelistDetail.filter_validity(validity=target_date),
            ).prefetch_related("item")
        }
        # root_items = set(i.item for i in item_pricelist_dict.values())

        service_pricelist_dict = {
            pd.service_id: pd
            for pd in ServicesPricelistDetail.objects.filter(
                service_id__in=service_ids,
                services_pricelist=claim.health_facility.services_pricelist,
                services_pricelist__validity_to__isnull=True,
                *ServicesPricelistDetail.filter_validity(validity=target_date),
            ).prefetch_related("service")
        }
        root_services = set(s.service for s in service_pricelist_dict.values())
    if len(errors) == 0:
        base_category = get_claim_category(claim, root_services)
        for plc in policies:
            policy_errors = check_claim_max_no_category(
                base_category,
                plc.product,
                plc.expiry_date,
                claim.insuree_id,
                plc.effective_date,
                claim,
            )
            if len(policy_errors) > 0:
                if len(policies) == 1:
                    errors += policy_errors
                policies.remove(plc)
    else:
        apply_claim_status(claim, Claim.STATUS_REJECTED)
        claim.rejection_reason = REJECTION_REASON_NO_COVERAGE
        claim.save()
        return errors
    if len(errors) == 0:
        adult = claim.insuree.is_adult(target_date)

        product_ids = set(p.product_id for p in policies)
        item_product_data = get_product_items_services(
            target_date,
            item_ids,
            claim.insuree_id,
            adult,
            "Item",
            product_ids,
            policies,
        )
        service_product_data = get_product_items_services(
            target_date,
            service_ids,
            claim.insuree_id,
            adult,
            "Service",
            product_ids,
            policies,
        )
        product_ids = set()

        product_item_tuple_dict = {}
        for data in item_product_data.values():
            for d in data:
                pi = d["prod_item_svc"]
                product_item_tuple_dict[(pi.product.id, pi.item.id)] = pi
        product_service_tuple_dict = {}
        for data in service_product_data.values():
            for d in data:
                ps = d["prod_item_svc"]
                product_service_tuple_dict[(ps.product.id, ps.service.id)] = ps
        product_items_by_item_id = defaultdict(list)
        for item_id, data in item_product_data.items():
            seen = set()
            for d in data:
                pi = d["prod_item_svc"]
                if pi.id not in seen:
                    product_items_by_item_id[item_id].append(pi)
                    seen.add(pi.id)
        product_services_by_service_id = defaultdict(list)
        for service_id, data in service_product_data.items():
            seen = set()
            for d in data:
                ps = d["prod_item_svc"]
                if ps.id not in seen:
                    product_services_by_service_id[service_id].append(ps)
                    seen.add(ps.id)
        if policies:
            min_effective = min(
                (p.effective_date for p in policies if p.effective_date),
                default=target_date,
            )
            max_expiry = max(
                (p.expiry_date for p in policies if p.expiry_date), default=target_date
            )
        else:
            min_effective = target_date
            max_expiry = target_date
        # Identify items and services requiring historical data
        item_ids_with_limits = []
        service_ids_with_limits = []
        for item in items:
            pi_data = product_items_by_item_id.get(item.item_id, [])
            for pi in pi_data:
                if (
                    pi.waiting_period_adult
                    or pi.waiting_period_child
                    or pi.limit_no_adult is not None
                    or pi.limit_no_child is not None
                    or item.item.frequency
                ):
                    item_ids_with_limits.append(item.item_id)

        for service in services:
            ps_data = product_services_by_service_id.get(service.service_id, [])
            for ps in ps_data:
                if (
                    ps.waiting_period_adult
                    or ps.waiting_period_child
                    or ps.limit_no_adult is not None
                    or ps.limit_no_child is not None
                    or service.service.frequency
                ):
                    service_ids_with_limits.append(service.service_id)

        # Fetch historical quantities only for items/services with limits
        if item_ids_with_limits:
            historical_item_qtys = (
                ClaimItem.objects.filter(
                    item_id__in=item_ids_with_limits,
                    claim__insuree_id=claim.insuree_id,
                    claim__status__gt=Claim.STATUS_ENTERED,
                    claim__validity_to__isnull=True,
                    validity_to__isnull=True,
                    status=ClaimDetail.STATUS_PASSED,
                )
                .filter(Q(rejection_reason=0) | Q(rejection_reason__isnull=True))
                .annotate(target_date=Coalesce("claim__date_to", "claim__date_from"))
                .filter(target_date__gte=min_effective, target_date__lte=max_expiry)
                .exclude(claim__uuid=claim.uuid)
                .values(
                    "item_id",
                    "target_date",
                    qty=Coalesce("qty_approved", "qty_provided"),
                )
            )
        else:
            historical_item_qtys = []
        item_history_by_id = {}
        # recent_item_dates_by_id = {}
        for h in historical_item_qtys:
            item_id = h["item_id"]
            item_history_by_id.setdefault(item_id, []).append(
                (h["target_date"], h["qty"])
            )

        if service_ids_with_limits:
            historical_service_qtys = (
                ClaimService.objects.filter(
                    service_id__in=service_ids_with_limits,
                    claim__insuree_id=claim.insuree_id,
                    claim__status__gt=Claim.STATUS_ENTERED,
                    claim__validity_to__isnull=True,
                    validity_to__isnull=True,
                    status=ClaimDetail.STATUS_PASSED,
                )
                .filter(Q(rejection_reason=0) | Q(rejection_reason__isnull=True))
                .annotate(target_date=Coalesce("claim__date_to", "claim__date_from"))
                .filter(target_date__gte=min_effective, target_date__lte=max_expiry)
                .exclude(claim__uuid=claim.uuid)
                .values(
                    "service_id",
                    "target_date",
                    qty=Coalesce("qty_approved", "qty_provided"),
                )
            )
        else:
            historical_service_qtys = []
        service_history_by_id = {}
        for h in historical_service_qtys:
            service_id = h["service_id"]
            service_history_by_id.setdefault(service_id, []).append(
                (h["target_date"], h["qty"])
            )
        detail_errors += validate_claimitems(
            claim,
            target_date,
            adult,
            items,
            item_pricelist_dict,
            item_product_data,
            item_history_by_id,
        )
        detail_errors += validate_claimservices(
            claim,
            target_date,
            adult,
            services,
            service_pricelist_dict,
            service_product_data,
            service_history_by_id,
            base_category,
        )
        errors += validate_assign_prod_to_claimitems_and_services(
            claim,
            policies=policies,
            services=services,
            items=items,
            product_items_by_item_id=product_items_by_item_id,
            product_services_by_service_id=product_services_by_service_id,
            target_date=target_date,
        )
        if len(errors) == 0 and check_max:
            over_category_errors = [
                x
                for x in detail_errors
                if x["code"]
                in [
                    REJECTION_REASON_MAX_HOSPITAL_ADMISSIONS,
                    REJECTION_REASON_MAX_VISITS,
                    REJECTION_REASON_MAX_CONSULTATIONS,
                    REJECTION_REASON_MAX_SURGERIES,
                    REJECTION_REASON_MAX_DELIVERIES,
                    REJECTION_REASON_MAX_ANTENATAL,
                ]
            ]
            if len(over_category_errors) > 0:
                claim.items.filter(validity_to__isnull=True).update(
                    status=ClaimItem.STATUS_REJECTED,
                    qty_approved=0,
                    rejection_reason=over_category_errors[0]["code"],
                )
                claim.services.filter(validity_to__isnull=True).update(
                    status=ClaimService.STATUS_REJECTED,
                    qty_approved=0,
                    rejection_reason=over_category_errors[0]["code"],
                )
            else:
                for item in items:
                    if item.rejection_reason:
                        item.status = ClaimItem.STATUS_REJECTED
                        item.qty_approved = 0
                        item.product_item = None
                    else:
                        item.status = ClaimItem.STATUS_PASSED
                    item.save()
                for service in services:
                    if service.rejection_reason:
                        service.status = ClaimService.STATUS_REJECTED
                        service.qty_approved = 0
                        service.product_service = None
                    else:
                        service.status = ClaimService.STATUS_PASSED
                    service.save()
        if all(
            item.status == ClaimItem.STATUS_REJECTED
            for item in claim.items.filter(validity_to__isnull=True)
        ) and all(
            service.status == ClaimService.STATUS_REJECTED
            for service in claim.services.filter(validity_to__isnull=True)
        ):
            errors += [
                {
                    "code": REJECTION_REASON_INVALID_ITEM_OR_SERVICE,
                    "message": _("claim.validation.all_items_and_services_rejected")
                    % {"code": claim.code},
                    "detail": claim.uuid,
                }
            ]
            if len(detail_errors) > 0:
                errors += detail_errors
            apply_claim_status(claim, Claim.STATUS_REJECTED)
            claim.rejection_reason = REJECTION_REASON_INVALID_ITEM_OR_SERVICE
            claim.save()
        if process_dedrem_opt and len(errors) == 0:
            dedrem_errors = process_dedrem(
                claim,
                user,
                is_process=is_process,
                policies=policies,
                items=items,
                services=services,
                item_product_data=item_product_data,
                service_product_data=service_product_data,
                product_item_tuple_dict=product_item_tuple_dict,
                product_service_tuple_dict=product_service_tuple_dict,
                root_services=root_services,
            )
            errors.extend(dedrem_errors)
    logger.debug(f"Validation found {len(errors)} error(s)")
    return errors
def validate_claimitems(
    claim, target_date, adult, items, pricelist_dict, product_data_by_id, history_by_id
):
    errors = []
    for claimitem in items:
        if claimitem.rejection_reason:
            continue
        errors += validate_claimitem_validity(claim, claimitem)
        if not claimitem.rejection_reason:
            errors += validate_claimitem_in_price_list(claim, claimitem, pricelist_dict)
        if not claimitem.rejection_reason:
            errors += validate_claimdetail_care_type(claim, claimitem)
        if not claimitem.rejection_reason:
            errors += validate_claimdetail_limitation_fail(claim, claimitem)
        if not claimitem.rejection_reason:
            errors += validate_claimitem_frequency(
                claim, claimitem, target_date, history_by_id.get(claimitem.item_id, [])
            )
        if not claimitem.rejection_reason:
            errors += validate_item_product_family(
                claimitem=claimitem,
                target_date=target_date,
                item=claimitem.item,
                insuree_id=claim.insuree_id,
                adult=adult,
                products_data=product_data_by_id.get(claimitem.item_id, []),
                history=history_by_id.get(claimitem.item_id, []),
            )
        if claimitem.rejection_reason:
            claimitem.status = ClaimItem.STATUS_REJECTED
        else:
            claimitem.rejection_reason = 0
            claimitem.status = ClaimItem.STATUS_PASSED
    return errors


def validate_claimservices(
    claim,
    target_date,
    adult,
    services,
    pricelist_dict,
    product_data_by_id,
    history_by_id,
    base_category,
):
    errors = []
    for claimservice in services:
        if claimservice.rejection_reason:
            continue
        errors += validate_claimservice_validity(claim, claimservice)
        if not claimservice.rejection_reason:
            errors += validate_claimservice_in_price_list(
                claim, claimservice, pricelist_dict
            )
        if not claimservice.rejection_reason:
            errors += validate_claimdetail_care_type(claim, claimservice)
        if not claimservice.rejection_reason:
            errors += validate_claimdetail_limitation_fail(claim, claimservice)
        if not claimservice.rejection_reason:
            errors += validate_claimservice_frequency(
                claim,
                claimservice,
                target_date,
                history_by_id.get(claimservice.service_id, []),
            )
        if not claimservice.rejection_reason:
            errors += validate_service_product_family(
                claimservice=claimservice,
                target_date=target_date,
                service=claimservice.service,
                insuree_id=claim.insuree_id,
                adult=adult,
                claim=claim,
                products_data=product_data_by_id.get(claimservice.service_id, []),
                history=history_by_id.get(claimservice.service_id, []),
            )
        if claimservice.rejection_reason:
            claimservice.status = ClaimService.STATUS_REJECTED
        else:
            claimservice.rejection_reason = 0
            claimservice.status = ClaimService.STATUS_PASSED
    return errors


def validate_claimitem_validity(claim, claimitem):
    errors = []
    target_date = get_claim_target_date(claim)
    if claimitem.validity_to is None and claimitem.item.validity_to is not None:
        claimitem.rejection_reason = REJECTION_REASON_INVALID_ITEM_OR_SERVICE
        errors += [
            {
                "code": REJECTION_REASON_INVALID_ITEM_OR_SERVICE,
                "message": _("claim.validation.claimitem_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    elif claimitem.item.validity_from and claimitem.item.validity_from > target_date:
        claimitem.rejection_reason = REJECTION_REASON_TARGET_DATE
        errors += [
            {
                "code": REJECTION_REASON_TARGET_DATE,
                "message": _("claim.validation.item_future_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimservice_validity(claim, claimservice):
    errors = []
    target_date = get_claim_target_date(claim)
    if (
        claimservice.validity_to is None
        and claimservice.service.validity_to is not None
    ):
        claimservice.rejection_reason = REJECTION_REASON_INVALID_ITEM_OR_SERVICE
        errors += [
            {
                "code": REJECTION_REASON_INVALID_ITEM_OR_SERVICE,
                "message": _("claim.validation.claimservice_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    elif (
        claimservice.service.validity_from
        and claimservice.service.validity_from > target_date
    ):
        claimservice.rejection_reason = REJECTION_REASON_TARGET_DATE
        errors += [
            {
                "code": REJECTION_REASON_TARGET_DATE,
                "message": _("claim.validation.service_future_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimitem_in_price_list(claim, claimitem, pricelist_dict=None):
    errors = []
    if claimitem.item_id not in pricelist_dict:
        claimitem.rejection_reason = REJECTION_REASON_NOT_IN_PRICE_LIST
        errors += [
            {
                "code": REJECTION_REASON_NOT_IN_PRICE_LIST,
                "message": _("claim.validation.claimitem_in_price_list_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimservice_in_price_list(claim, claimservice, pricelist_dict=None):
    errors = []
    if claimservice.service_id not in pricelist_dict:
        claimservice.rejection_reason = REJECTION_REASON_NOT_IN_PRICE_LIST
        errors += [
            {
                "code": REJECTION_REASON_NOT_IN_PRICE_LIST,
                "message": _("claim.validation.claimservice_in_price_list_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimdetail_care_type(claim, claimdetail):
    errors = []
    care_type = claimdetail.itemsvc.care_type
    hf_care_type = (
        claim.health_facility.care_type if claim.health_facility.care_type else "B"
    )
    target_date = get_claim_target_date(claim)
    inpatient = target_date != claim.date_from
    if (
        (hf_care_type == "O" and inpatient)
        or (hf_care_type == "O" and care_type == "I")
        or (hf_care_type == "I" and care_type == "O")
    ):
        claimdetail.rejection_reason = REJECTION_REASON_CARE_TYPE
        errors += [
            {
                "code": REJECTION_REASON_CARE_TYPE,
                "message": _("claim.validation.claimdetail_care_type_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimdetail_limitation_fail(claim, claimdetail):
    if claimdetail.itemsvc.patient_category == 0:
        return []
    errors = []
    target_date = get_claim_target_date(claim)
    patient_category_mask = utils.patient_category_mask(claim.insuree, target_date)
    if (
        claimdetail.itemsvc.patient_category & patient_category_mask
        != patient_category_mask
    ):
        claimdetail.rejection_reason = REJECTION_REASON_CATEGORY_LIMITATION
        errors += [
            {
                "code": REJECTION_REASON_CATEGORY_LIMITATION,
                "message": _("claim.validation.claimdetail_limitation_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimitem_frequency(claim, claimitem, target_date, history):
    errors = []
    if claimitem.item.frequency and any(
        d >= (target_date - datetimedelta(days=claimitem.item.frequency))
        for d in [entry[0] for entry in history]
    ):
        claimitem.rejection_reason = REJECTION_REASON_FREQUENCY_FAILURE
        errors += [
            {
                "code": REJECTION_REASON_FREQUENCY_FAILURE,
                "message": _("claim.validation.claimitem_frequency_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_claimservice_frequency(claim, claimservice, target_date, history):
    errors = []
    if claimservice.service.frequency and any(
        d >= (target_date - datetimedelta(days=claimservice.service.frequency))
        for d in [entry[0] for entry in history]
    ):
        claimservice.rejection_reason = REJECTION_REASON_FREQUENCY_FAILURE
        errors += [
            {
                "code": REJECTION_REASON_FREQUENCY_FAILURE,
                "message": _("claim.validation.claimservice_frequency_validity")
                % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_target_date(claim):
    errors = []
    if (
        claim.date_from is None and claim.date_to is None
    ) or claim.date_claimed < claim.date_from:
        claim.reject(REJECTION_REASON_TARGET_DATE)
        errors += [
            {
                "code": REJECTION_REASON_TARGET_DATE,
                "message": _("claim.validation.target_date") % {"code": claim.code},
                "detail": claim.uuid,
            }
        ]
    return errors


def validate_insuree(claim, insuree, policies=None):
    errors = []
    if insuree.validity_to is not None:
        errors += [
            {
                "code": REJECTION_REASON_FAMILY,
                "message": _("claim.validation.family.insuree_validity")
                % {"code": claim.code, "insuree": str(insuree)},
                "detail": claim.uuid,
            }
        ]
    if not insuree.family or insuree.family.validity_to is not None:
        errors += [
            {
                "code": REJECTION_REASON_FAMILY,
                "message": _("claim.validation.family.family_validity")
                % {"code": claim.code, "insuree": str(insuree)},
                "detail": claim.uuid,
            }
        ]
    if not policies:
        errors += [
            {
                "code": REJECTION_REASON_NO_COVERAGE,
                "message": _("claim.validation.family.no_policy")
                % {"code": claim.code, "insuree": str(insuree)},
                "detail": claim.uuid,
            }
        ]

    if len(errors) > 0:
        claim.reject(REJECTION_REASON_FAMILY)
    return errors


def validate_item_product_family(
    claimitem, target_date, item, insuree_id, adult, products_data, history
):
    errors = []
    found = False
    for data in products_data:
        product_item = data["prod_item_svc"]
        insuree_policy_effective_date = data["insuree_policy_effective_date"]
        policy_effective_date = data["policy_effective_date"]
        expiry_date = data["expiry_date"]
        policy_stage = data["policy_stage"]
        found = True
        core = __import__("core")
        insuree_policy_effective_date = core.datetime.date.from_ad_date(
            insuree_policy_effective_date
        )
        expiry_date = core.datetime.date.from_ad_date(expiry_date)
        errors += check_service_item_waiting_period(
            policy_stage,
            policy_effective_date,
            insuree_policy_effective_date,
            item,
            adult,
            product_item,
            target_date,
            claimitem,
        )
        errors += check_service_item_max_provision(
            adult,
            product_item,
            item,
            insuree_policy_effective_date,
            expiry_date,
            insuree_id,
            claimitem,
            history,
        )
    if not found:
        claimitem.rejection_reason = REJECTION_REASON_NO_PRODUCT_FOUND
        errors += [
            {
                "code": REJECTION_REASON_NO_PRODUCT_FOUND,
                "message": _("claim.validation.product_family.no_product_found")
                % {"code": claimitem.claim.code, "element": str(item)},
                "detail": claimitem.claim.uuid,
            }
        ]
    return errors


def validate_service_product_family(
    claimservice, target_date, service, insuree_id, adult, claim, products_data, history
):
    errors = []
    found = False
    for data in products_data:
        product_service = data["prod_item_svc"]
        insuree_policy_effective_date = data["insuree_policy_effective_date"]
        policy_effective_date = data["policy_effective_date"]
        expiry_date = data["expiry_date"]
        policy_stage = data["policy_stage"]
        found = True
        core = __import__("core")
        insuree_policy_effective_date = core.datetime.date.from_ad_date(
            insuree_policy_effective_date
        )
        policy_effective_date = core.datetime.date.from_ad_date(policy_effective_date)
        expiry_date = core.datetime.date.from_ad_date(expiry_date)
        errors += check_service_item_waiting_period(
            policy_stage,
            policy_effective_date,
            insuree_policy_effective_date,
            service,
            adult,
            product_service,
            target_date,
            claimservice,
        )
        errors += check_service_item_max_provision(
            adult,
            product_service,
            service,
            insuree_policy_effective_date,
            expiry_date,
            insuree_id,
            claimservice,
            history,
        )
        # error_len = len(errors)
        # product = product_service.product

    if not found:
        claimservice.rejection_reason = REJECTION_REASON_NO_PRODUCT_FOUND
        errors += [
            {
                "code": REJECTION_REASON_NO_PRODUCT_FOUND,
                "message": _("claim.validation.product_family.no_product_found")
                % {"code": claimservice.claim.code, "element": str(service)},
                "detail": claimservice.claim.uuid,
            }
        ]
    return errors


def check_service_item_waiting_period(
    policy_stage,
    policy_effective_date,
    insuree_policy_effective_date,
    service_or_item,
    adult,
    product_service_item,
    target_date,
    claim_service_item,
):
    errors = []
    waiting_period = None
    if policy_stage == "N" or policy_effective_date < insuree_policy_effective_date:
        if adult:
            waiting_period = product_service_item.waiting_period_adult
        else:
            waiting_period = product_service_item.waiting_period_child
    if waiting_period and target_date < (
        insuree_policy_effective_date + datetimedelta(months=waiting_period)
    ):
        claim_service_item.rejection_reason = REJECTION_REASON_WAITING_PERIOD_FAIL
        errors += [
            {
                "code": REJECTION_REASON_WAITING_PERIOD_FAIL,
                "message": _("claim.validation.product_family.waiting_period")
                % {
                    "code": claim_service_item.claim.code,
                    "element": str(service_or_item),
                },
                "detail": claim_service_item.claim.uuid,
            }
        ]
    return errors


def check_service_item_max_provision(
    adult,
    product_service_item,
    service_or_item,
    insuree_policy_effective_date,
    expiry_date,
    insuree_id,
    claim_service_item,
    history,
):
    errors = []
    if adult:
        limit_no = product_service_item.limit_no_adult
    else:
        limit_no = product_service_item.limit_no_child
    if limit_no is not None and limit_no >= 0:
        total_qty_provided = sum(
            qty
            for date, qty in history
            if insuree_policy_effective_date <= date <= expiry_date
        )
        qty = total_qty_provided + (
            claim_service_item.qty_provided
            if claim_service_item.qty_approved is None
            else claim_service_item.qty_approved
        )
        if qty > limit_no:
            if total_qty_provided < limit_no:
                remaining_qty = limit_no - total_qty_provided
                if claim_service_item.qty_approved is None:
                    claim_service_item.qty_provided = remaining_qty
                else:
                    claim_service_item.qty_approved = remaining_qty
            else:
                claim_service_item.rejection_reason = REJECTION_REASON_QTY_OVER_LIMIT
                errors += [
                    {
                        "code": REJECTION_REASON_QTY_OVER_LIMIT,
                        "message": _("claim.validation.product_family.max_nb_allowed"),
                    }
                ]
    return errors


def check_claim_max_no_category(
    base_category, product_data, expiry_date, insuree_id, policy_effective_date, claim
):
    errors = []
    category_dict = {
        "C": {
            "field": "max_no_consultation",
            "reason": REJECTION_REASON_MAX_CONSULTATIONS,
            "message": "claim.validation.product_family.max_nb_consultation",
        },
        "S": {
            "field": "max_no_surgery",
            "reason": REJECTION_REASON_MAX_SURGERIES,
            "message": "claim.validation.product_family.max_nb_surgeries",
        },
        "D": {
            "field": "max_no_delivery",
            "reason": REJECTION_REASON_MAX_DELIVERIES,
            "message": "claim.validation.product_family.max_nb_deliveries",
        },
        "A": {
            "field": "max_no_antenatal",
            "reason": REJECTION_REASON_MAX_ANTENATAL,
            "message": "claim.validation.product_family.max_nb_antenatal",
        },
        "H": {
            "field": "max_no_hospitalization",
            "reason": REJECTION_REASON_MAX_HOSPITAL_ADMISSIONS,
            "message": "claim.validation.product_family.max_nb_hospitalizations",
        },
        "V": {
            "field": "max_no_visits",
            "reason": REJECTION_REASON_MAX_VISITS,
            "message": "claim.validation.product_family.max_nb_visits",
        },
    }.get(base_category)
    if (
        category_dict
        and getattr(product_data, category_dict["field"], None) is not None
        and getattr(product_data, category_dict["field"], None) >= 0
    ):
        max_value = getattr(product_data, category_dict["field"])
        historical_claims = (
            Claim.objects.filter(
                insuree_id=claim.insuree_id,
                validity_to__isnull=True,
                status__gt=Claim.STATUS_ENTERED,
                category=base_category,
            )
            .annotate(target_date=Coalesce("date_to", "date_from"))
            .filter(
                target_date__gte=policy_effective_date,
                target_date__lte=expiry_date,
            )
            .exclude(uuid=claim.uuid)
            .values("target_date", "category")
        )
        claims_by_category = defaultdict(list)
        for hc in historical_claims:
            cat = hc["category"]
            claims_by_category[cat].append(hc["target_date"])

        dates = claims_by_category.get(base_category, [])
        if base_category == "V":
            dates += claims_by_category.get(None, [])
        count = len([d for d in dates if policy_effective_date <= d <= expiry_date])
        if count >= max_value:
            claim.rejection_reason = category_dict["reason"]
            errors += [
                {
                    "code": category_dict["reason"],
                    "message": _(category_dict["message"])
                    % {"code": claim.code, "count": count, "max": max_value},
                    "detail": claim.uuid,
                }
            ]
    return errors
