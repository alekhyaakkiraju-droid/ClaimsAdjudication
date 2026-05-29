"""
WO-023: Referral fields and multi-diagnosis support helpers.

The claim model stores one primary diagnosis (``icd``) and up to four additional
diagnoses (``icd_1`` … ``icd_4``). Referral metadata lives on ``refer_from``,
``refer_to``, and ``referral_code``.

Duplicate-diagnosis lookup (``claimWithSameDiagnosis``) matches the supplied ICD
code against **all** supported diagnosis fields, not only the primary ``icd`` field.
"""

from __future__ import annotations

from django.db.models import Q

ADDITIONAL_ICD_FIELD_NAMES = ("icd_1", "icd_2", "icd_3", "icd_4")
ALL_ICD_FIELD_NAMES = ("icd",) + ADDITIONAL_ICD_FIELD_NAMES
REFERRAL_FIELD_NAMES = ("refer_from", "refer_to", "referral_code")


def build_same_diagnosis_filter(*, icd_code: str, chf_id: str) -> Q:
    """Return a Q filter for claims with the same ICD on any supported diagnosis field."""
    diagnosis_match = Q()
    for field in ALL_ICD_FIELD_NAMES:
        diagnosis_match |= Q(**{f"{field}__code": icd_code, f"{field}__validity_to__isnull": True})

    return diagnosis_match & Q(
        insuree__chf_id=chf_id,
        insuree__validity_to__isnull=True,
        validity_to__isnull=True,
    )


def count_additional_diagnoses_in_data(incoming_data: dict) -> int:
    """Count additional diagnosis keys present in mutation/service payload data."""
    return sum(
        1
        for key in incoming_data
        if key.startswith("icd_") and key.endswith("_id") and key != "icd_id"
    )
