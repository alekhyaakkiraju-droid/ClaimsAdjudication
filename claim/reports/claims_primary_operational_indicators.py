# flake8: noqa

import calendar
from _decimal import Decimal

from django.db.models import Q

from claim.models import Claim, ClaimDetail
from core.datetimes.ad_datetime import date
from location.models import Location, HealthFacility
from product.models import Product

from claim.reports.queryset import claim_operational_indicators_queryset
from claim.reports.template_loader import load_report_template

template = load_report_template("claims_primary_operational_indicators")

CATEGORY_TOTAL = "T"
CATEGORY_PAID = "P"
CATEGORY_REJECTED = "R"

NO_DATA_CODE = "????????"
NO_DATA_NAME = "NO_DATA"

Q1 = 1
Q2 = 2
Q3 = 3
Q4 = 4
AVAILABLE_QUARTERS = [Q1, Q2, Q3, Q4]

DEFAULT_YEAR = 0
ALL_MONTHS = -1
ALL_QUARTERS = -2
DEFAULT_REGION = -3
ALL_DISTRICTS = -4
ALL_PRODUCTS = -5
ALL_HFS = -6


def generate_subtotal():
    return {
        CATEGORY_TOTAL: Decimal(0.00),
        CATEGORY_PAID: Decimal(0.00),
        CATEGORY_REJECTED: Decimal(0.00),
    }


def prepare_product_info():
    # Prepares the required Product information and returns it in a dict[product_id:product_info]
    product_info_mapping = {}
    products = Product.objects.values("id", "code", "name")
    for product in products:
        product_info_mapping[product["id"]] = product
    return product_info_mapping


def prepare_hf_info():
    # Prepares the required HealthFacility information and returns it in a dict[hf_id:hf_info]
    hf_info_mapping = {}
    hfs = HealthFacility.objects.values("id", "code", "name")
    for hf in hfs:
        hf_info_mapping[hf["id"]] = hf
    return hf_info_mapping


def prepare_list_of_working_months(month: int, quarter: int):
    # Returns the list of months for which data will be calculated in this report
    if quarter == ALL_QUARTERS:
        if month == ALL_MONTHS:
            return list(range(1, 13))
        return [month]

    quarters = {
        1: [1, 2, 3],
        2: [4, 5, 6],
        3: [7, 8, 9],
        4: [10, 11, 12],
    }
    return quarters[quarter]


def calculate_start_end_month_dates(year: int, month: int):
    num_days = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, num_days)
    return start_date, end_date


def prepare_all_monthly_totals(subtotals: dict, working_months: list):
    # Prepares subtotals for each month
    # This is required in order to display a month without any information in the report
    for month in working_months:
        subtotals[month] = {"total": generate_subtotal()}


def get_claim_product(claim: Claim):
    # Returns the Product linked to a Claim, whether through its ClaimItem or its ClaimService
    for item in claim.items.all():
        if item.product_id:
            return item.product_id
    for service in claim.services.all():
        if service.product_id:
            return service.product_id
    return None


def dispatch_subtotals(subtotals: dict, claim: Claim, month: int):
    # Takes Claim data and dispatches it in various subtotals
    # The subtotals' structure is the following:
    # { month: {
    #       hf_id: {
    #           product_id: {
    #               categories: value
    #           },
    #           "total": { # for the HF
    #               categories: value
    #           },
    #       },
    #       "total": { # for the month
    #           categories: value
    #       },
    #   },
    #   "total": { # grand total
    #       categories: value
    #   },
    # }
    product_id = get_claim_product(claim)
    hf_id = claim.health_facility_id

    if hf_id not in subtotals[month]:
        subtotals[month][hf_id] = {"total": generate_subtotal()}
        if product_id:
            subtotals[month][hf_id][product_id] = generate_subtotal()
    elif product_id and product_id not in subtotals[month][hf_id]:
        subtotals[month][hf_id][product_id] = generate_subtotal()

    add_value_to_category(
        subtotals, month, hf_id, product_id, CATEGORY_TOTAL, Decimal(1.00)
    )

    if claim.status == Claim.STATUS_REJECTED:
        add_value_to_category(
            subtotals, month, hf_id, product_id, CATEGORY_REJECTED, Decimal(1.00)
        )
    elif claim.status == Claim.STATUS_VALUATED:
        total_remunerated = calculate_total_remunerated(claim)
        add_value_to_category(
            subtotals, month, hf_id, product_id, CATEGORY_PAID, total_remunerated
        )


def add_value_to_category(
    subtotals: dict,
    month: int,
    hf_id: int,
    product_id: int,
    category: str,
    value: Decimal,
):
    # Adds a given value for a given category in each subtotal level
    subtotals["total"][category] += value
    subtotals[month]["total"][category] += value
    subtotals[month][hf_id]["total"][category] += value
    if product_id:
        subtotals[month][hf_id][product_id][category] += value


def calculate_total_remunerated(claim: Claim):
    total_valuated = Decimal(0.00)
    for item in claim.items.all():
        if item.remunerated_amount and item.status == ClaimDetail.STATUS_PASSED:
            total_valuated += item.remunerated_amount
    for service in claim.services.all():
        if service.remunerated_amount and service.status == ClaimDetail.STATUS_PASSED:
            total_valuated += service.remunerated_amount
    return total_valuated


def format_totals(subtotals: dict, report_data: dict):
    # Adds and formats total figures to the report data
    report_data["total_t"] = subtotals["total"][CATEGORY_TOTAL]
    report_data["total_paid"] = subtotals["total"][CATEGORY_PAID]
    report_data["total_rejected"] = subtotals["total"][CATEGORY_REJECTED]


def format_final_data(
    subtotals: dict, hf_info: dict, product_info: dict, month_info: list
):
    # Formats the data in order to match what is expected by the report
    data = []
    subtotals.pop("total")  # Removing the total figures that were already taken care of
    for month_id, monthly_values in subtotals.items():
        monthly_total = subtotals[month_id].pop("total")  # Totals for the given month
        monthly_data = {
            "month_nbr": month_id,
            "month_txt": month_info[month_id - 1],
            "monthly_total_t": monthly_total[CATEGORY_TOTAL],
            "monthly_total_p": monthly_total[CATEGORY_PAID],
            "monthly_total_r": monthly_total[CATEGORY_REJECTED],
        }
        if (
            not monthly_values
        ):  # If there is no data for this month, a line must still appear for the report
            new_data_line = {
                **monthly_data,
                "month_hf_code": f"{month_id}-{NO_DATA_CODE}",  # Required for the section split in the report
                "hf_name": NO_DATA_NAME,
                "hf_code": NO_DATA_CODE,
                "product_name": NO_DATA_NAME,
                "product_code": NO_DATA_CODE,
            }
            data.append(new_data_line)
            continue

        for hf_id, hf_values in monthly_values.items():
            hf_total = subtotals[month_id][hf_id].pop(
                "total"
            )  # Totals for the given HF
            hf_code = hf_info[hf_id]["code"]
            hf_data = {
                "month_hf_code": f"{month_id}-{hf_code}",  # Required for the section split in the report
                "hf_name": hf_info[hf_id]["name"],
                "hf_code": hf_code,
                "hf_total_t": hf_total[CATEGORY_TOTAL],
                "hf_total_p": hf_total[CATEGORY_PAID],
                "hf_total_r": hf_total[CATEGORY_REJECTED],
            }
            if (
                not hf_values
            ):  # If there is no data for this HF, a line must still appear for the report
                new_data_line = {
                    **monthly_data,
                    **hf_data,
                    "product_name": NO_DATA_NAME,
                    "product_code": NO_DATA_CODE,
                }
                data.append(new_data_line)
                continue

            for product_id, product_values in hf_values.items():
                new_data_line = {
                    **monthly_data,
                    **hf_data,
                    "product_code": product_info[product_id]["code"],
                    "product_name": product_info[product_id]["name"],
                    "product_total_t": product_values[CATEGORY_TOTAL],
                    "product_total_p": product_values[CATEGORY_PAID],
                    "product_total_r": product_values[CATEGORY_REJECTED],
                }
                data.append(new_data_line)

    data.sort(key=lambda x: (x["month_nbr"], x["hf_code"], x["product_code"]))
    return data


def claims_primary_operational_indicators_query(
    user,
    requested_month=ALL_MONTHS,
    requested_quarter=ALL_QUARTERS,
    requested_year=DEFAULT_YEAR,
    requested_region_id=DEFAULT_REGION,
    requested_district_id=ALL_DISTRICTS,
    requested_product_id=ALL_PRODUCTS,
    requested_hf_id=ALL_HFS,
    **kwargs,
):
    # Checking the parameters received and returning an error if anything is wrong
    validated_parameters = {}
    month = int(requested_month)
    if month not in range(1, 13) and month != ALL_MONTHS:
        return {"error": "Error - the selected month is invalid"}
    quarter = int(requested_quarter)
    if quarter not in range(1, 5) and quarter != ALL_QUARTERS:
        return {"error": "Error - the selected quarter is invalid"}
    year = int(requested_year)
    if year not in range(2010, 2100):
        return {"error": "Error - the selected year is invalid"}
    product_id = int(requested_product_id)
    if product_id != ALL_PRODUCTS:
        product = Product.objects.filter(validity_to=None, id=product_id).first()
        if not product:
            return {"error": "Error - the requested product does not exist"}
        validated_parameters["product"] = product
    region_id = int(requested_region_id)
    region = Location.objects.filter(validity_to=None, type="R", id=region_id).first()
    if not region:
        return {"error": "Error - the requested region does not exist"}
    validated_parameters["region"] = region
    district_id = int(requested_district_id)
    if district_id != ALL_DISTRICTS:
        district_filters = (
            Q(validity_to__isnull=True)
            & Q(type="D")
            & Q(id=district_id)
            & Q(parent_id=region_id)
        )
        district = Location.objects.filter(district_filters).first()
        if not district:
            return {"error": "Error - the requested district does not exist"}
        validated_parameters["district"] = district
    hf_id = int(requested_hf_id)
    if hf_id != ALL_HFS:
        hf = HealthFacility.objects.filter(validity_to=None, id=hf_id).first()
        if not hf:
            return {"error": "Error - the requested health facility does not exist"}
        validated_parameters["hf"] = hf

    # Preparing reference data that will be used later
    months_txt = calendar.month_name[1:]
    product_info_mapping = prepare_product_info()
    hf_info_mapping = prepare_hf_info()

    # Preparing data for the header table
    header = {
        "region": f"{validated_parameters['region'].code} - {validated_parameters['region'].name}",
        "district": (
            "All districts"
            if district_id == ALL_DISTRICTS
            else f"{validated_parameters['district'].code} - {validated_parameters['district'].name}"
        ),
        "hf": (
            "All health facilities"
            if hf_id == ALL_HFS
            else f"{validated_parameters['hf'].code} - {validated_parameters['hf'].name}"
        ),
        "product": (
            "All products"
            if product_id == ALL_PRODUCTS
            else f"{validated_parameters['product'].code} - {validated_parameters['product'].name}"
        ),
        "month": "All months" if month == ALL_MONTHS else months_txt[month - 1],
        "quarter": "All quarters" if quarter == ALL_QUARTERS else f"Q{quarter}",
        "year": year,
    }
    report_data = {
        "header": [header],
    }

    # Preparing filters based on received parameters
    default_search_filters = (
        Q(validity_to__isnull=True)
        & Q(health_facility__validity_to__isnull=True)
        & Q(health_facility__location__validity_to__isnull=True)
        & Q(health_facility__location__parent_id=region_id)
        & (
            (
                Q(items__isnull=True)
                | (
                    Q(items__validity_to__isnull=True)
                    & Q(items__product__validity_to__isnull=True)
                )
            )
            & (
                Q(services__isnull=True)
                | (
                    Q(services__validity_to__isnull=True)
                    & Q(services__product__validity_to__isnull=True)
                )
            )
        )
        & Q(insuree__validity_to__isnull=True)
    )
    if product_id != ALL_PRODUCTS:
        default_search_filters &= Q(items__product_id=product_id) | Q(
            services__product_id=product_id
        )
    if hf_id != ALL_HFS:
        default_search_filters &= Q(health_facility_id=hf_id)
    elif district_id != ALL_DISTRICTS:
        default_search_filters &= Q(health_facility__location=district_id)

    subtotals = {"total": generate_subtotal()}

    # Preparing the list of months for which data will be calculated
    working_months = prepare_list_of_working_months(month, quarter)
    prepare_all_monthly_totals(subtotals, working_months)

    for current_month in working_months:

        start_date, end_date = calculate_start_end_month_dates(year, current_month)
        search_filters = default_search_filters & Q(
            date_from__range=[start_date, end_date]
        )

        claims = claim_operational_indicators_queryset(
            Claim.objects.filter(search_filters)
        ).distinct("id")
        for claim in claims:
            dispatch_subtotals(subtotals, claim, current_month)

    format_totals(subtotals, report_data)
    report_data["data"] = format_final_data(
        subtotals, hf_info_mapping, product_info_mapping, months_txt
    )

    return report_data
