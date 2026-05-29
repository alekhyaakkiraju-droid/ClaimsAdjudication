import graphene
from enum import Enum
import logging
from core.models import Officer, MutationLog
from insuree.models import Insuree
from .services import check_unique_claim_code
from core.schema import (
    signal_mutation_module_validate,
    signal_mutation_module_after_mutating,
)
from django.db.models import Subquery, Q
from claim.diagnosis_variance import build_diagnosis_variance_filter
import graphene_django_optimizer as gql_optimizer
from core.schema import OrderedDjangoFilterConnectionField, OfficerGQLType
from .models import ClaimMutation, Claim
from graphene_django.filter import DjangoFilterConnectionField
from claim.api_errors import get_insuree_health_facility_for_fsp, get_valid_claim
from claim.read_queryset import apply_claim_read_prefetches
from claim.gql_authorization import require_query_permission
from claim.models import ClaimAttachment
# We do need all queries and mutations in the namespace here.

from location.schema import HealthFacilityGQLType
from .gql_queries import (
    ClaimAttachmentTypeGQLType,
    ClaimGQLType,
    ClaimAttachmentGQLType,
)
from .gql_mutations import (
    DeleteClaimsMutation,
    ProcessClaimsMutation,
    SkipClaimsReviewMutation,
    BypassClaimsReviewMutation,
    DeliverClaimsReviewMutation,
    SaveClaimReviewMutation,
    SelectClaimsForReviewMutation,
    SkipClaimsFeedbackMutation,
    BypassClaimsFeedbackMutation,
    DeliverClaimFeedbackMutation,
    SelectClaimsForFeedbackMutation,
    SubmitClaimsMutation,
    DeleteAttachmentMutation,
    UpdateAttachmentMutation,
    CreateAttachmentMutation,
    UpdateClaimMutation,
    CreateClaimMutation
)

logger = logging.getLogger(__name__)


class Query(graphene.ObjectType):
    claims = OrderedDjangoFilterConnectionField(
        ClaimGQLType,
        diagnosisVariance=graphene.Int(),
        code_is_not=graphene.String(),
        orderBy=graphene.List(of_type=graphene.String),
        items=graphene.List(of_type=graphene.String),
        services=graphene.List(of_type=graphene.String),
        json_ext=graphene.JSONString(),
        attachment_status=graphene.Int(required=False),
        care_type=graphene.String(required=False),
        show_restored=graphene.Boolean(required=False),
    )

    claim = graphene.Field(ClaimGQLType, id=graphene.Int(), uuid=graphene.UUID())

    claim_attachments = DjangoFilterConnectionField(ClaimAttachmentGQLType)

    claim_officers = DjangoFilterConnectionField(
        OfficerGQLType, search=graphene.String()
    )

    insuree_name_by_chfid = graphene.String(chfId=graphene.String(required=True))

    validate_claim_code = graphene.Field(
        graphene.Boolean,
        claim_code=graphene.String(required=True),
        description="Checks that the specified claim code is unique.",
    )
    fsp_from_claim = graphene.Field(
        HealthFacilityGQLType,
        insuree_code=graphene.String(required=True),
        date_claimed=graphene.Date(required=True),
        description="Return FSP of insuree during creation of the claim.",
    )

    claim_with_same_diagnosis = OrderedDjangoFilterConnectionField(
        ClaimGQLType,
        icd=graphene.String(required=True),
        chfid=graphene.String(required=True),
        description="Return last claim (date claimed) with identical diagnosis for given insuree.",
    )

    claim_attachment_type = DjangoFilterConnectionField(ClaimAttachmentTypeGQLType)

    claim_history = OrderedDjangoFilterConnectionField(
        ClaimGQLType,
        claim_uuid=graphene.String(required=True),
        diagnosisVariance=graphene.Int(),
        code_is_not=graphene.String(),
        orderBy=graphene.List(of_type=graphene.String),
        items=graphene.List(of_type=graphene.String),
        services=graphene.List(of_type=graphene.String),
        json_ext=graphene.JSONString(),
        attachment_status=graphene.Int(required=False),
        care_type=graphene.String(required=False),
        show_restored=graphene.Boolean(required=False),
        rejection_code=graphene.Int(required=False)
    )

    def resolve_insuree_name_by_chfid(self, info, **kwargs):
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

    def resolve_validate_claim_code(self, info, **kwargs):
        require_query_permission(info, "validate_claim_code")
        errors = check_unique_claim_code(code=kwargs["claim_code"])
        return False if errors else True

    def resolve_claim(self, info, id=None, uuid=None, **kwargs):
        require_query_permission(info, "claim")
        return get_valid_claim(claim_id=id, claim_uuid=uuid)

    def resolve_claims(self, info, **kwargs):
        class AttachmentStatusEnum(Enum):
            NONE = 0
            WITH = 1
            WITHOUT = 2

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
        # filtered already in get_queryser
        # query = query.filter(
        #   LocationManager().build_user_location_filter_query(
        #       info.context.user._u, prefix='health_facility__location'
        #   )
        # )
        code_is_not = kwargs.get("code_is_not", None)

        if len(filters):
            query = query.filter(*filters)
        if code_is_not:
            query = query.exclude(code=code_is_not)

        if len(filters) == 0 and not code_is_not:
            query = query.all()
        return gql_optimizer.query(apply_claim_read_prefetches(query), info)

    def resolve_claim_attachments(self, info, **kwargs):
        require_query_permission(info, "claim_attachments")
        return ClaimAttachment.objects.filter(*ClaimAttachment.filter_validity())

    def resolve_claim_officers(self, info, search=None, **kwargs):
        require_query_permission(info, "claim_officers")

        qs = Officer.objects

        if search is not None:
            qs = qs.filter(
                Q(code__icontains=search)
                | Q(last_name__icontains=search)
                | Q(other_names__icontains=search)
            )
        return qs

    def resolve_fsp_from_claim(self, info, **kwargs):
        require_query_permission(info, "fsp_from_claim")
        return get_insuree_health_facility_for_fsp(
            kwargs["insuree_code"], kwargs["date_claimed"]
        )

    def resolve_claim_with_same_diagnosis(self, info, **kwargs):
        require_query_permission(info, "claim_with_same_diagnosis")

        qs = Claim.objects.filter(
            icd__code=kwargs["icd"],
            icd__validity_to__isnull=True,
            insuree__chf_id=kwargs["chfid"],
            insuree__validity_to__isnull=True,
            validity_to__isnull=True,
        ).order_by("date_claimed")
        return qs

    def resolve_claim_history(self, info, **kwargs):
        claim_uuid = kwargs.get('claim_uuid')

        require_query_permission(info, "claim_history")

        query = Claim.objects.filter(
            legacy_id=Subquery(Claim.objects.filter(uuid=claim_uuid).values('id')),
            validity_to__isnull=False
        )

        filters = []

        if "care_type" in kwargs and kwargs["care_type"]:
            filters.append(Q(care_type=kwargs["care_type"]))

        if "attachment_status" in kwargs:
            status = kwargs["attachment_status"]
            if status == 1:  # WITH
                filters.append(Q(attachments__isnull=False))
            elif status == 2:  # WITHOUT
                filters.append(Q(attachments__isnull=True))

        if "code_is_not" in kwargs and kwargs["code_is_not"]:
            filters.append(~Q(code=kwargs["code_is_not"]))

        if filters:
            query = query.filter(*filters).distinct()

        return gql_optimizer.query(apply_claim_read_prefetches(query), info)


class Mutation(graphene.ObjectType):
    create_claim = CreateClaimMutation.Field()
    update_claim = UpdateClaimMutation.Field()
    create_claim_attachment = CreateAttachmentMutation.Field()
    update_claim_attachment = UpdateAttachmentMutation.Field()
    delete_claim_attachment = DeleteAttachmentMutation.Field()
    submit_claims = SubmitClaimsMutation.Field()
    select_claims_for_feedback = SelectClaimsForFeedbackMutation.Field()
    deliver_claim_feedback = DeliverClaimFeedbackMutation.Field()
    bypass_claims_feedback = BypassClaimsFeedbackMutation.Field()
    skip_claims_feedback = SkipClaimsFeedbackMutation.Field()
    select_claims_for_review = SelectClaimsForReviewMutation.Field()
    save_claim_review = SaveClaimReviewMutation.Field()
    deliver_claims_review = DeliverClaimsReviewMutation.Field()
    bypass_claims_review = BypassClaimsReviewMutation.Field()
    skip_claims_review = SkipClaimsReviewMutation.Field()
    process_claims = ProcessClaimsMutation.Field()
    delete_claims = DeleteClaimsMutation.Field()


def on_claim_mutation(sender, **kwargs):
    uuids = kwargs["data"].get("uuids", [])
    if not uuids:
        uuid = kwargs["data"].get("claim_uuid", None)
        uuids = [uuid] if uuid else []
    if not uuids:
        return []
    impacted_claims = Claim.objects.filter(uuid__in=uuids).all()
    for claim in impacted_claims:
        ClaimMutation.objects.create(claim=claim, mutation_id=kwargs["mutation_log_id"])
    return []


def on_claim_after_mutation(sender, **kwargs):
    if kwargs.get("error_messages", None):
        return []
    elif kwargs.get("mutation_class", None) != "CreateClaimMutation":
        return []
    if "data" in kwargs and kwargs["data"].get("autogenerate"):
        try:
            mutation_client_id = kwargs.get("data")["client_mutation_id"]
            mutation_log = MutationLog.objects.filter(
                client_mutation_id=mutation_client_id
            ).first()
            mutation_log.client_mutation_label = kwargs["data"]["client_mutation_label"]
            mutation_log.autogenerated_code = kwargs["data"]["code"]
            mutation_log.save()
            return []
        except KeyError as e:
            logger.error(
                "Client Mutation ID not found in claim signal after mutation, error: ",
                e,
            )
    return []


def bind_signals():
    signal_mutation_module_validate["claim"].connect(on_claim_mutation)
    signal_mutation_module_after_mutating["claim"].connect(on_claim_after_mutation)
