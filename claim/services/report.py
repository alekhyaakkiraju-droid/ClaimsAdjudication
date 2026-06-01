"""Claim print/report data fetching."""

from gettext import gettext as _

import core
from django.conf import settings
from django.core.exceptions import PermissionDenied

from claim.reports.queryset import claim_print_report_queryset


def formatClaimService(s):
    return {
        "service": str(s.service),
        "quantity": s.qty_provided,
        "price": s.price_asked,
        "explanation": s.explanation,
    }


def formatClaimItem(i):
    return {
        "item": str(i.item),
        "quantity": i.qty_provided,
        "price": i.price_asked,
        "explanation": i.explanation,
    }


class ClaimReportService(object):
    def __init__(self, user):
        self.user = user

    def fetch(self, uuid):
        from claim.models import Claim

        queryset = Claim.objects.filter(*core.filter_validity())
        if settings.ROW_SECURITY:
            from location.models import LocationManager

            queryset = LocationManager().build_user_location_filter_query(
                self.user._u,
                prefix="health_facility__location",
                queryset=queryset,
                loc_types=["D"],
            )
        claim = claim_print_report_queryset(queryset).filter(uuid=uuid).first()
        if not claim:
            raise PermissionDenied(_("unauthorized"))
        return {
            "code": claim.code,
            "visitDateFrom": claim.date_from.isoformat() if claim.date_from else None,
            "visitDateTo": claim.date_to.isoformat() if claim.date_to else None,
            "claimDate": claim.date_claimed.isoformat() if claim.date_claimed else None,
            "healthFacility": str(claim.health_facility),
            "insuree": str(claim.insuree),
            "claimAdmin": str(claim.admin) if claim.admin else None,
            "icd": str(claim.icd),
            "icd1": str(claim.icd_1) if claim.icd_1 else None,
            "icd2": str(claim.icd_2) if claim.icd_2 else None,
            "icd3": str(claim.icd_3) if claim.icd_3 else None,
            "icd4": str(claim.icd_4) if claim.icd_4 else None,
            "referFrom": str(claim.refer_from) if claim.refer_from else None,
            "referTo": str(claim.refer_to) if claim.refer_to else None,
            "referralCode": claim.referral_code,
            "guarantee": claim.guarantee_id,
            "visitType": claim.visit_type,
            "claimed": claim.claimed,
            "services": [formatClaimService(s) for s in claim.services.all()],
            "items": [formatClaimItem(i) for i in claim.items.all()],
        }
