# flake8: noqa

from _decimal import Decimal
from typing import Dict, Union

from django.db.models import Q, Prefetch

from core.utils import filter_validity
from location.models import Location, HealthFacility
from product.models import Product
from claim.models import Claim, ClaimItem, ClaimService

import logging

from claim.reports.template_loader import load_report_template

logger = logging.getLogger(__name__)

template = load_report_template("claims_overview")

CLAIM_ELEMENT_TYPE_ITEM = "Item"
CLAIM_ELEMENT_TYPE_SERVICE = "Service"

SCOPE_FULL = "F"
SCOPE_ONLY_CLAIMS = "C"
SCOPE_REJECTION = "R"
AVAILABLE_SCOPES = [SCOPE_FULL, SCOPE_ONLY_CLAIMS, SCOPE_REJECTION]

ALL_PRODUCTS = -1
ALL_REGIONS = -2
ALL_DISTRICTS = -3
ALL_HFS = -4

STATUS_ALL = -5
STATUS_REJECTED = 1
STATUS_ENTERED = 2
STATUS_CHECKED = 4
STATUS_PROCESSED = 8
STATUS_VALUATED = 16
AVAILABLE_STATUSES = [
    STATUS_REJECTED,
    STATUS_ENTERED,
    STATUS_CHECKED,
    STATUS_PROCESSED,
    STATUS_VALUATED,
]


def coalesce_amounts(*values):
    """
    Return the first non-None value or Decimal(0.00) if all values are None

    From: https://towardsdatascience.com/4-cute-python-functions-for-working-with-dirty-data-2cf7974280b5
    """
    return next((v for v in values if v is not None), Decimal(0.00))


# def generate_claim_detail(element,
def generate_claim_detail(
    element: Union[ClaimItem, ClaimService],
    claim_data: Dict,
    price_approved: Decimal,
    element_type: str,
) -> Dict:
    element_name = (
        element.item.name
        if element_type == CLAIM_ELEMENT_TYPE_ITEM
        else element.service.name
    )
    element_code = (
        element.item.code
        if element_type == CLAIM_ELEMENT_TYPE_ITEM
        else element.service.code
    )

    claim_detail = {
        **claim_data,
        "e_status": element.status,
        "e_justification": element.justification,
        "e_qty_asked": element.qty_provided,
        "e_qty_approved": element.qty_approved,
        "e_claimed": element.price_asked * element.qty_provided,
        "e_adjusted": element.price_adjusted,
        "e_approved": price_approved,
        "e_valuated": element.price_valuated,
        "e_paid": element.remunerated_amount,
        "e_rejection": element.rejection_reason,
        "e_name": element_name,
        "e_code": element_code,
        "e_type": element_type,
    }

    return claim_detail


def claims_overview_query(
    user,
    date_start="2009-01-01",
    date_end="2032-12-31",
    scope=SCOPE_FULL,
    requested_region_id=ALL_REGIONS,
    requested_district_id=ALL_DISTRICTS,
    requested_product_id=ALL_PRODUCTS,
    requested_hf_id=ALL_HFS,
    requested_claim_status=STATUS_ALL,
    **kwargs,
):
    # /!\ The scope is not taken care of in this version. Unfortunately, the initial report is very unclear,
    # there is too much data displayed and the display is poor.
    # This report is using only the full scope of the previous report. If reduced versions are necessary,
    # I would suggest creating other reports.

    # /!\ There is a general issue with the way various amounts are stored in Claim, ClaimItem and ClaimService.
    # Sometimes, the amounts in the details(ClaimItem, ClaimService) of a claim
    # don't add up to figures at the Claim level.
    # The figures used for calculating the total values are based only on the Claim-level figures.

    # Checking the parameters received and returning an error if anything is wrong
    validated_parameters = {}
    if date_start > date_end:
        return {"error": "Error - the start date cannot be greater than the end date"}
    if scope not in AVAILABLE_SCOPES:
        return {"error": "Error - the requested scope is unknown"}
    claim_status = int(requested_claim_status)
    if claim_status not in AVAILABLE_STATUSES and claim_status != STATUS_ALL:
        return {"error": "Error - the requested claim status is unknown"}
    product_id = int(requested_product_id)
    if product_id != ALL_PRODUCTS:
        product = Product.objects.filter(validity_to=None, id=product_id).first()
        if not product:
            return {"error": "Error - the requested product does not exist"}
        validated_parameters["product"] = product
    region_id = int(requested_region_id)
    if region_id != ALL_REGIONS:
        region = Location.objects.filter(
            validity_to=None, type="R", id=region_id
        ).first()
        if not region:
            return {"error": "Error - the requested region does not exist"}
        validated_parameters["region"] = region
    district_id = int(requested_district_id)
    if district_id != ALL_DISTRICTS:
        district_filters = Q(validity_to__isnull=True) & Q(type="D") & Q(id=district_id)
        if (
            region_id != ALL_REGIONS
        ):  # The FE pickers allow you to select a district without a region, so additional steps are required
            district_filters &= Q(parent_id=region_id)
        district = Location.objects.filter(district_filters).first()
        if not district:
            return {"error": "Error - the requested district does not exist"}
        validated_parameters["district"] = district
        if (
            region_id == ALL_REGIONS
        ):  # The FE pickers allow you to select a district without a region, so additional steps are required
            validated_parameters["region"] = district.parent
    hf_id = int(requested_hf_id)
    if hf_id != ALL_HFS:
        hf = HealthFacility.objects.filter(validity_to=None, id=hf_id).first()
        if not hf:
            return {"error": "Error - the requested health facility does not exist"}
        validated_parameters["hf"] = hf

    # Preparing data for the header table
    header = {
        "date_start": date_start,
        "date_end": date_end,
        "scope": scope,
        "product": (
            "All products"
            if product_id == ALL_PRODUCTS
            else f"{validated_parameters['product'].code} - {validated_parameters['product'].name}"
        ),
        "status": "All statuses" if claim_status == STATUS_ALL else str(claim_status),
    }

    # Preparing filters based on received parameters
    claim_filters = (
        Q(validity_to__isnull=True)
        & Q(admin__validity_to__isnull=True)
        & (
            (Q(date_to__isnull=False) & Q(date_to__range=(date_start, date_end)))
            | (Q(date_from__range=(date_start, date_end)))
        )
    )
    if hf_id != ALL_HFS:
        claim_filters &= Q(health_facility_id=hf_id)
        hf = validated_parameters["hf"]
        header["hf"] = f"{hf.code} - {hf.name}"
        header["district"] = f"{hf.location.code} - {hf.location.name}"
        header["region"] = f"{hf.location.parent.code} - {hf.location.parent.name}"
    else:
        # Possibly multiple HFs
        claim_filters &= Q(health_facility__validity_to__isnull=True)
        header["hf"] = "All health facilities"
        if district_id != ALL_DISTRICTS:
            claim_filters &= Q(health_facility__location_id=district_id)
            header["district"] = (
                f"{validated_parameters['district'].code} - {validated_parameters['district'].name}"
            )
            header["region"] = (
                f"{validated_parameters['region'].code} - {validated_parameters['region'].name}"
            )
        elif region_id != ALL_REGIONS:
            claim_filters &= Q(health_facility__location__parent_id=region_id)
            header["district"] = "All districts"
            header["region"] = (
                f"{validated_parameters['region'].code} - {validated_parameters['region'].name}"
            )
        else:
            header["district"] = "All districts"
            header["region"] = "All regions"
    if claim_status != STATUS_ALL:
        claim_filters &= Q(status=claim_status)
    if product_id != ALL_PRODUCTS:
        claim_filters &= Q(items__product_id=product_id) | Q(
            services__product_id=product_id
        )

    # The .distinct() will not work on MSSQL (because it generates a DISTINCT ON(...) clause)
    # If this report has to be generated with an MSSQL database, this part will need to be changed.
    # An easy way would be to make a set of claim codes - during the for loop, check if the code is in the set:
    # if it's not in the set -> process the claim and add its code to the set
    # if it's already in the set -> continue
    claim_queryset = (
        Claim.objects.filter(claim_filters)
        .distinct("date_claimed", "insuree__chf_id", "code")
        .order_by("date_claimed", "insuree__chf_id", "code")
        .prefetch_related(
            Prefetch("items", queryset=ClaimItem.objects.filter(*ClaimItem.filter_validity()))
        )
        .prefetch_related("items__item")
        .prefetch_related("insuree")
        .prefetch_related(
            Prefetch(
                "services", queryset=ClaimService.objects.filter(*ClaimService.filter_validity())
            )
        )
        .prefetch_related("services__service")
        .prefetch_related("admin")
    )

    total_claimed = Decimal(0.0)
    total_approved = Decimal(0.0)
    total_adjusted = Decimal(0.0)
    total_paid = Decimal(0.0)
    data = []

    for claim in claim_queryset:
        new_data_claim = {
            "c_code": claim.code,
            "c_date_claimed": claim.date_claimed,
            "c_insuree_nbr": claim.insuree.chf_id,
            "c_insuree_name": claim.insuree.last_name,
            "c_insuree_other_names": claim.insuree.other_names,
            "c_status": claim.status,
            "c_date_from": claim.date_from,
            "c_date_to": claim.date_to,
            "c_claimed": claim.claimed,
            "c_approved": claim.approved,
            "c_valuated": claim.valuated,
            "c_paid": claim.remunerated,
            "c_health_facility_code": claim.health_facility.code,
            "c_health_facility_name": claim.health_facility.name,
            "c_admin_name": claim.admin.last_name,
            "c_admin_other_names": claim.admin.other_names,
        }

        if claim.claimed:
            total_claimed += claim.claimed
        if claim.approved:
            total_approved += claim.approved
        if claim.valuated:
            total_adjusted += claim.valuated

        for item in claim.items.order_by("item__code"):

            price_approved = coalesce_amounts(
                item.price_approved, item.price_asked
            ) * coalesce_amounts(item.qty_approved, item.qty_provided)

            claim_element = generate_claim_detail(
                item, new_data_claim, price_approved, CLAIM_ELEMENT_TYPE_ITEM
            )
            data.append(claim_element)

            if item.remunerated_amount:
                total_paid += item.remunerated_amount

        for service in claim.services.order_by("service__code"):

            price_approved = coalesce_amounts(
                service.price_approved, service.price_asked
            ) * coalesce_amounts(service.qty_approved, service.qty_provided)

            claim_element = generate_claim_detail(
                service, new_data_claim, price_approved, CLAIM_ELEMENT_TYPE_SERVICE
            )
            data.append(claim_element)

            if service.remunerated_amount:
                total_paid += service.remunerated_amount

    footer = {
        "total_claims": len(claim_queryset),
        "total_claimed": total_claimed,
        "total_approved": total_approved,
        "total_adjusted": total_adjusted,
        "total_paid": total_paid,
    }

    return {"data": data, "header": [header], "footer": [footer]}
