import base64

from django.conf import settings
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes

import core
from location.models import LocationManager
from report.services import ReportService

from .apps import ClaimConfig
from .models import ClaimAttachment
from .reports import claim
from .rest_authorization import ClaimRestPermission
from .services import ClaimReportService


@api_view(["GET"])
@permission_classes([ClaimRestPermission("print")])
def print(request):
    report_service = ReportService(request.user)
    report_data_service = ClaimReportService(request.user)
    data = report_data_service.fetch(request.GET["uuid"])
    return report_service.process("claim_claim", data, claim.template)


@api_view(["GET", "POST"])
@permission_classes([ClaimRestPermission("attach")])
def attach(request):
    queryset = ClaimAttachment.objects.filter(*core.filter_validity())
    if settings.ROW_SECURITY:
        queryset = LocationManager().build_user_location_filter_query(
            request.user._u,
            prefix="health_facility__location",
            queryset=queryset.select_related("claim"),
            loc_types=["D"],
        )
    attachment = queryset.filter(id=request.GET["id"]).first()
    if not attachment:
        return HttpResponse(status=404)

    if ClaimConfig.claim_attachments_root_path and attachment.url is None:
        return HttpResponse(status=404)

    if not ClaimConfig.claim_attachments_root_path and attachment.document is None:
        return HttpResponse(status=404)

    response = HttpResponse(
        content_type=(
            "application/x-binary" if attachment.mime is None else attachment.mime
        )
    )
    response["Content-Disposition"] = "attachment; filename=%s" % attachment.filename
    if ClaimConfig.claim_attachments_root_path:
        with open(
            "%s/%s" % (ClaimConfig.claim_attachments_root_path, attachment.url), "rb"
        ) as f:
            response.write(f.read())
    else:
        response.write(base64.b64decode(attachment.document))
    return response
