"""
WO-026: Job handlers executed by the database-backed claim job worker.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from claim.models import ClaimJob

logger = logging.getLogger(__name__)


class _AuditUser:
    """Minimal user stand-in for background workers (audit fields only)."""

    def __init__(self, id_for_audit: int):
        self.id_for_audit = id_for_audit
        self.id = id_for_audit


def _process_claims_payload(payload: Dict[str, Any]) -> List[Any]:
    from claim.services import process_claims_batch

    uuids = payload.get("uuids") or []
    user_id = payload.get("user_id_for_audit")
    if user_id is None:
        raise ValueError("process_claims job payload missing user_id_for_audit")
    return process_claims_batch(uuids, _AuditUser(int(user_id)))


def _generate_report_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_name = payload.get("report_name")
    if not report_name:
        raise ValueError("generate_report job payload missing report_name")
    return {
        "status": "not_implemented",
        "report_name": report_name,
        "message": "Report queue hook reserved for WO-027/WO-028",
    }


JOB_HANDLERS = {
    ClaimJob.JOB_PROCESS_CLAIMS: _process_claims_payload,
    ClaimJob.JOB_GENERATE_REPORT: _generate_report_payload,
}


def execute_job_handler(job: ClaimJob) -> Any:
    handler = JOB_HANDLERS.get(job.job_type)
    if handler is None:
        raise ValueError(f"Unknown claim job type: {job.job_type}")
    logger.info("Executing claim job %s (%s)", job.uuid, job.job_type)
    return handler(job.payload or {})
