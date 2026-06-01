"""Claim category derivation."""

from claim.models import ClaimService
from claim.utils import get_claim_target_date
from medical.models import Service


def get_claim_category(claim, services=None):
    """
    Determine the claim category based on its services.
    """
    if claim.category:
        return claim.category
    service_categories = [
        Service.CATEGORY_SURGERY,
        Service.CATEGORY_DELIVERY,
        Service.CATEGORY_ANTENATAL,
        Service.CATEGORY_HOSPITALIZATION,
        Service.CATEGORY_CONSULTATION,
        Service.CATEGORY_OTHER,
        Service.CATEGORY_VISIT,
    ]
    target_date = get_claim_target_date(claim)
    if services is None:
        services = Service.objects.filter(
            claimservice__claim=claim,
            *Service.filter_validity(validity=target_date),
            *ClaimService.filter_validity(validity=target_date, prefix="claimservice__"),
        )

    claim_service_categories = [service.category for service in services]
    if claim.date_from != target_date:
        claim_service_categories.append(Service.CATEGORY_HOSPITALIZATION)
    for category in service_categories:
        if category in claim_service_categories:
            claim_category = category
            break
    else:
        claim_category = Service.CATEGORY_VISIT
    return claim_category
