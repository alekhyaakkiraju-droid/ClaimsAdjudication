"""GraphQL query resolver implementations (WO-029)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional, List

from django.db.models import Q, Subquery
from insuree.models import Insuree
import graphene_django_optimizer as gql_optimizer

from claim.api_errors import get_insuree_health_facility_for_fsp, get_valid_claim
from claim.diagnosis_variance import build_diagnosis_variance_filter
from claim.gql_authorization import require_query_permission
from claim.models import Claim, ClaimAttachment, ClaimAttachmentType
from claim.query_cache import (
    attachment_types_cache_key,
    cached_or_load,
    cached_queryset_pks,
    claim_list_cache_key,
    officers_cache_key,
)
from claim.read_queryset import apply_claim_read_prefetches
from claim.referral_diagnosis import build_same_diagnosis_filter
from claim.services.persistence import check_unique_claim_code
from core.models import Officer


class AttachmentStatusEnum(Enum):
    NONE = 0
    WITH = 1
    WITHOUT = 2


def resolve_insuree_name_by_chfid(info: Any, **kwargs: Any) -> str:
    require_query_permission(info, "insuree_name_by_chfid")
    chf_id = kwargs.get("chfId")
    insuree = (
        Insuree.objects.filter(validity_to__isnull=True, chf_id=chf_id)
        .values("last_name", "other_names")
        .first()
    )
    if insuree:
        insuree_name = f"{insuree['other_names']} {insuree['last_name']}"
    else:
        insuree_name = ""
    return insuree_name


def resolve_validate_claim_code(info: Any, **kwargs: Any) -> bool:
    require_query_permission(info, "validate_claim_code")
    errors = check_unique_claim_code(code=kwargs["claim_code"])
    return False if errors else True


def resolve_claim_job(info: Any, uuid: str, **kwargs: Any) -> Any:
    require_query_permission(info, "claim_job")
    from claim.job_queue import get_job_by_uuid

    return get_job_by_uuid(uuid)


def resolve_claim_jobs(info: Any, **kwargs: Any) -> Any:
    require_query_permission(info, "claim_jobs")
    from claim.models import ClaimJob

    return ClaimJob.get_queryset(ClaimJob.objects.all(), info)


def resolve_claim(
    info: Any, id: Optional[int] = None, uuid: Optional[str] = None, **kwargs: Any
) -> Optional[Claim]:
    require_query_permission(info, "claim")
    return get_valid_claim(claim_id=id, claim_uuid=uuid)


def resolve_claims(info: Any, **kwargs: Any) -> Any:
    require_query_permission(info, "claims")
    query = Claim.objects
    filters = []

    show_restored = kwargs.get("show_restored", None)
    if show_restored:
        filters.append(Q(restore__isnull=False))

    items = kwargs.get("items", None)
    services = kwargs.get("services", None)

    if items:
        filters.append(Q(items__item__code__in=items))

    if services:
        filters.append(Q(services__service__code__in=services))

    attachment_status = kwargs.get("attachment_status", 0)
    if attachment_status == AttachmentStatusEnum.WITH.value:
        filters.append(Q(attachments__isnull=False))
    elif attachment_status == AttachmentStatusEnum.WITHOUT.value:
        filters.append(Q(attachments__isnull=True))

    care_type = kwargs.get("care_type", None)

    if care_type:
        filters.append(Q(care_type=care_type))

    json_ext = kwargs.get("json_ext", None)

    if json_ext:
        filters.append(Q(json_ext__jsoncontains=json_ext))
    variance = kwargs.get("diagnosisVariance", None)
    if variance:
        from core import datetime, datetimedelta

        last_year = datetime.date.today() + datetimedelta(years=-1)
        filters.append(
            build_diagnosis_variance_filter(
                variance,
                validity_filters=Claim.filter_validity(**kwargs),
                last_year_date=last_year,
            )
        )
    code_is_not = kwargs.get("code_is_not", None)

    if len(filters):
        query = query.filter(*filters)
    if code_is_not:
        query = query.exclude(code=code_is_not)

    if len(filters) == 0 and not code_is_not:
        query = query.all()

    from claim.apps import ClaimConfig

    list_key = claim_list_cache_key(
        {
            "filters": [str(f) for f in filters],
            "code_is_not": code_is_not,
            "variance": variance,
            "user_id": getattr(info.context.user, "id", None),
        }
    )
    query = cached_queryset_pks(
        list_key,
        query,
        timeout=ClaimConfig.query_cache_list_ttl,
    )
    return gql_optimizer.query(apply_claim_read_prefetches(query), info)


def resolve_claim_attachments(info: Any, **kwargs: Any) -> Any:
    require_query_permission(info, "claim_attachments")
    return ClaimAttachment.objects.filter(*ClaimAttachment.filter_validity())


def resolve_claim_officers(info: Any, search: Optional[str] = None, **kwargs: Any) -> Any:
    require_query_permission(info, "claim_officers")

    from claim.apps import ClaimConfig

    def _load_officer_pks() -> List[Any]:
        qs = Officer.objects
        if search is not None:
            qs = qs.filter(
                Q(code__icontains=search)
                | Q(last_name__icontains=search)
                | Q(other_names__icontains=search)
            )
        return list(qs.values_list("pk", flat=True))

    pks = cached_or_load(
        officers_cache_key(search),
        _load_officer_pks,
        timeout=ClaimConfig.query_cache_reference_ttl,
    )
    if not pks:
        return Officer.objects.none()
    return Officer.objects.filter(pk__in=pks)


def resolve_claim_attachment_type(info: Any, **kwargs: Any) -> Any:
    require_query_permission(info, "claim_attachment_type")

    from claim.apps import ClaimConfig

    def _load_attachment_type_pks() -> List[Any]:
        return list(
            ClaimAttachmentType.objects.filter(
                *ClaimAttachmentType.filter_validity()
            ).values_list("pk", flat=True)
        )

    pks = cached_or_load(
        attachment_types_cache_key(),
        _load_attachment_type_pks,
        timeout=ClaimConfig.query_cache_reference_ttl,
    )
    if not pks:
        return ClaimAttachmentType.objects.none()
    return ClaimAttachmentType.objects.filter(pk__in=pks)


def resolve_fsp_from_claim(info: Any, **kwargs: Any) -> Any:
    require_query_permission(info, "fsp_from_claim")
    return get_insuree_health_facility_for_fsp(
        kwargs["insuree_code"], kwargs["date_claimed"]
    )


def resolve_claim_with_same_diagnosis(info: Any, **kwargs: Any) -> Any:
    require_query_permission(info, "claim_with_same_diagnosis")

    qs = Claim.objects.filter(
        build_same_diagnosis_filter(
            icd_code=kwargs["icd"],
            chf_id=kwargs["chfid"],
        )
    ).order_by("date_claimed")
    return qs


def resolve_claim_history(info: Any, **kwargs: Any) -> Any:
    claim_uuid = kwargs.get("claim_uuid")

    require_query_permission(info, "claim_history")

    query = Claim.objects.filter(
        legacy_id=Subquery(Claim.objects.filter(uuid=claim_uuid).values("id")),
        validity_to__isnull=False,
    )

    filters = []

    if "care_type" in kwargs and kwargs["care_type"]:
        filters.append(Q(care_type=kwargs["care_type"]))

    if "attachment_status" in kwargs:
        status = kwargs["attachment_status"]
        if status == 1:
            filters.append(Q(attachments__isnull=False))
        elif status == 2:
            filters.append(Q(attachments__isnull=True))

    if "code_is_not" in kwargs and kwargs["code_is_not"]:
        filters.append(~Q(code=kwargs["code_is_not"]))

    if filters:
        query = query.filter(*filters).distinct()

    return gql_optimizer.query(apply_claim_read_prefetches(query), info)
