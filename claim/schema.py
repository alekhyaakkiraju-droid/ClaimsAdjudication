import graphene
import logging
from core.models import MutationLog
from core.schema import (
    signal_mutation_module_validate,
    signal_mutation_module_after_mutating,
)
from core.schema import OrderedDjangoFilterConnectionField, OfficerGQLType
from .models import ClaimMutation, Claim
from graphene_django.filter import DjangoFilterConnectionField
from claim.query_cache import bump_list_cache_version, invalidate_claim_cache
from claim.gql_queries import (
    ClaimAttachmentTypeGQLType,
    ClaimGQLType,
    ClaimAttachmentGQLType,
    ClaimJobGQLType,
)
from claim.schema_resolvers import (
    resolve_claim,
    resolve_claim_attachment_type,
    resolve_claim_attachments,
    resolve_claim_history,
    resolve_claim_job,
    resolve_claim_jobs,
    resolve_claim_officers,
    resolve_claim_with_same_diagnosis,
    resolve_claims,
    resolve_fsp_from_claim,
    resolve_insuree_name_by_chfid,
    resolve_validate_claim_code,
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
    CreateClaimMutation,
)

from location.schema import HealthFacilityGQLType

logger = logging.getLogger(__name__)


class Query(graphene.ObjectType):
    """Claim module GraphQL queries. Permissions via claim/gql_authorization.py."""

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
        description="Paginated claim list with optional filters (row-security aware).",
    )

    claim = graphene.Field(
        ClaimGQLType,
        id=graphene.Int(),
        uuid=graphene.UUID(),
        description="Single claim by database id or UUID.",
    )

    claim_attachments = DjangoFilterConnectionField(
        ClaimAttachmentGQLType,
        description="Claim attachments visible to the caller.",
    )

    claim_officers = DjangoFilterConnectionField(
        OfficerGQLType,
        search=graphene.String(),
        description="Officers eligible for claim feedback (search optional).",
    )

    insuree_name_by_chfid = graphene.String(
        chfId=graphene.String(required=True),
        description="Resolve insuree display name from CHF id during claim entry.",
    )

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

    claim_job = graphene.Field(
        ClaimJobGQLType,
        uuid=graphene.String(required=True),
        description="Return status for a database-backed claim background job.",
    )
    claim_jobs = DjangoFilterConnectionField(
        ClaimJobGQLType,
        description="List claim background jobs (newest first).",
    )

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
        rejection_code=graphene.Int(required=False),
        description="Historical versions of a claim (validity_to set).",
    )

    def resolve_insuree_name_by_chfid(self, info, **kwargs):
        return resolve_insuree_name_by_chfid(info, **kwargs)

    def resolve_validate_claim_code(self, info, **kwargs):
        return resolve_validate_claim_code(info, **kwargs)

    def resolve_claim_job(self, info, uuid, **kwargs):
        return resolve_claim_job(info, uuid, **kwargs)

    def resolve_claim_jobs(self, info, **kwargs):
        return resolve_claim_jobs(info, **kwargs)

    def resolve_claim(self, info, id=None, uuid=None, **kwargs):
        return resolve_claim(info, id=id, uuid=uuid, **kwargs)

    def resolve_claims(self, info, **kwargs):
        return resolve_claims(info, **kwargs)

    def resolve_claim_attachments(self, info, **kwargs):
        return resolve_claim_attachments(info, **kwargs)

    def resolve_claim_officers(self, info, search=None, **kwargs):
        return resolve_claim_officers(info, search=search, **kwargs)

    def resolve_claim_attachment_type(self, info, **kwargs):
        return resolve_claim_attachment_type(info, **kwargs)

    def resolve_fsp_from_claim(self, info, **kwargs):
        return resolve_fsp_from_claim(info, **kwargs)

    def resolve_claim_with_same_diagnosis(self, info, **kwargs):
        return resolve_claim_with_same_diagnosis(info, **kwargs)

    def resolve_claim_history(self, info, **kwargs):
        return resolve_claim_history(info, **kwargs)


class Mutation(graphene.ObjectType):
    """Claim module GraphQL mutations. Errors use OpenIMIS mutation error list shape."""

    create_claim = CreateClaimMutation.Field(
        description="Create a claim in ENTERED status with items/services."
    )
    update_claim = UpdateClaimMutation.Field(
        description="Update an existing claim and child lines."
    )
    create_claim_attachment = CreateAttachmentMutation.Field(
        description="Add an attachment to a claim (file or URL strategy)."
    )
    update_claim_attachment = UpdateAttachmentMutation.Field(
        description="Update attachment metadata or content."
    )
    delete_claim_attachment = DeleteAttachmentMutation.Field(
        description="Soft-delete a claim attachment."
    )
    submit_claims = SubmitClaimsMutation.Field(
        description="Submit one or more claims for validation and CHECKED/REJECTED status."
    )
    select_claims_for_feedback = SelectClaimsForFeedbackMutation.Field(
        description="Mark claims selected for community feedback."
    )
    deliver_claim_feedback = DeliverClaimFeedbackMutation.Field(
        description="Record delivered feedback for a claim."
    )
    bypass_claims_feedback = BypassClaimsFeedbackMutation.Field(
        description="Bypass feedback requirement for claims."
    )
    skip_claims_feedback = SkipClaimsFeedbackMutation.Field(
        description="Skip feedback selection for claims."
    )
    select_claims_for_review = SelectClaimsForReviewMutation.Field(
        description="Select claims for medical review."
    )
    save_claim_review = SaveClaimReviewMutation.Field(
        description="Save in-progress review adjustments."
    )
    deliver_claims_review = DeliverClaimsReviewMutation.Field(
        description="Finalize review for selected claims."
    )
    bypass_claims_review = BypassClaimsReviewMutation.Field(
        description="Bypass review for selected claims."
    )
    skip_claims_review = SkipClaimsReviewMutation.Field(
        description="Skip review selection for claims."
    )
    process_claims = ProcessClaimsMutation.Field(
        description="Process/valuate claims (sync or async via job queue)."
    )
    delete_claims = DeleteClaimsMutation.Field(
        description="Soft-delete claims by UUID."
    )


def on_claim_mutation(sender, **kwargs):
    uuids = kwargs["data"].get("uuids", [])
    if not uuids:
        uuid = kwargs["data"].get("claim_uuid", None)
        uuids = [uuid] if uuid else []
    if not uuids:
        bump_list_cache_version()
        return []
    impacted_claims = Claim.objects.filter(uuid__in=uuids).all()
    invalidate_claim_cache(
        claim_ids=[claim.id for claim in impacted_claims],
        claim_uuids=uuids,
    )
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
