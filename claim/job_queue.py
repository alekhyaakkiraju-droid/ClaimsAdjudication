"""
WO-026: Database-backed job queue for long-running claim operations.

Uses the claim_ClaimJob table (SQL Server backed) with graceful fallback to
synchronous execution when queuing is disabled or below the async threshold.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from django.db import transaction
from django.utils import timezone

from claim.models import ClaimJob

logger = logging.getLogger(__name__)


def _queue_config():
    from claim.apps import ClaimConfig

    return ClaimConfig


def is_job_queue_enabled() -> bool:
    return bool(getattr(_queue_config(), "job_queue_enabled", True))


def async_threshold() -> int:
    return int(getattr(_queue_config(), "job_queue_async_threshold", 0) or 0)


def max_retries() -> int:
    return int(getattr(_queue_config(), "job_queue_max_retries", 3))


def default_queue_name() -> str:
    return str(getattr(_queue_config(), "job_queue_name", "default") or "default")


def should_enqueue_batch(uuids: Sequence[str]) -> bool:
    if not is_job_queue_enabled():
        return False
    threshold = async_threshold()
    if threshold <= 0:
        return False
    return len(uuids or []) >= threshold


def enqueue_process_claims(
    uuids: Sequence[str],
    user,
    *,
    client_mutation_id: Optional[str] = None,
    priority: int = 0,
) -> ClaimJob:
    job = ClaimJob.objects.create(
        job_type=ClaimJob.JOB_PROCESS_CLAIMS,
        status=ClaimJob.STATUS_PENDING,
        queue_name=default_queue_name(),
        priority=priority,
        payload={
            "uuids": [str(u) for u in (uuids or [])],
            "user_id_for_audit": getattr(user, "id_for_audit", None),
        },
        max_retries=max_retries(),
        audit_user_id=getattr(user, "id_for_audit", None),
        client_mutation_id=client_mutation_id,
    )
    logger.info(
        "Enqueued process_claims job %s for %s claims",
        job.uuid,
        len(uuids or []),
    )
    return job


def enqueue_generate_report(
    report_name: str,
    report_params: dict,
    user,
    *,
    client_mutation_id: Optional[str] = None,
    priority: int = 0,
) -> ClaimJob:
    return ClaimJob.objects.create(
        job_type=ClaimJob.JOB_GENERATE_REPORT,
        status=ClaimJob.STATUS_PENDING,
        queue_name=default_queue_name(),
        priority=priority,
        payload={
            "report_name": report_name,
            "params": report_params or {},
            "user_id_for_audit": getattr(user, "id_for_audit", None),
        },
        max_retries=max_retries(),
        audit_user_id=getattr(user, "id_for_audit", None),
        client_mutation_id=client_mutation_id,
    )


def _acquire_next_job(queue_name: str) -> Optional[ClaimJob]:
    with transaction.atomic():
        qs = ClaimJob.objects.filter(
            status=ClaimJob.STATUS_PENDING,
            queue_name=queue_name,
        ).order_by("-priority", "created")
        try:
            job = qs.select_for_update(skip_locked=True).first()
        except Exception:
            job = qs.select_for_update().first()
        if job is None:
            return None
        job.status = ClaimJob.STATUS_RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
        return job


def _mark_completed(job: ClaimJob, result: Any) -> ClaimJob:
    job.status = ClaimJob.STATUS_COMPLETED
    job.result = result
    job.last_error = None
    job.completed_at = timezone.now()
    job.save(update_fields=["status", "result", "last_error", "completed_at"])
    return job


def _mark_failed(job: ClaimJob, exc: BaseException, *, retry: bool) -> ClaimJob:
    job.last_error = str(exc)
    if retry:
        job.status = ClaimJob.STATUS_PENDING
        job.retry_count += 1
        job.started_at = None
        job.save(update_fields=["status", "last_error", "retry_count", "started_at"])
        logger.warning(
            "Claim job %s failed (retry %s/%s): %s",
            job.uuid,
            job.retry_count,
            job.max_retries,
            exc,
        )
    else:
        job.status = ClaimJob.STATUS_FAILED
        job.completed_at = timezone.now()
        job.save(
            update_fields=["status", "last_error", "completed_at"]
        )
        logger.error("Claim job %s failed permanently: %s", job.uuid, exc)
    return job


def process_next_job(*, queue_name: Optional[str] = None) -> Optional[ClaimJob]:
    from claim.jobs import execute_job_handler

    queue = queue_name or default_queue_name()
    job = _acquire_next_job(queue)
    if job is None:
        return None
    try:
        result = execute_job_handler(job)
        return _mark_completed(job, result)
    except Exception as exc:
        can_retry = job.retry_count < job.max_retries
        return _mark_failed(job, exc, retry=can_retry)


def get_job_by_uuid(job_uuid: str) -> Optional[ClaimJob]:
    if not job_uuid:
        return None
    return ClaimJob.objects.filter(uuid=str(job_uuid)).first()


def job_status_summary(job: ClaimJob) -> dict:
    return {
        "uuid": str(job.uuid),
        "job_type": job.job_type,
        "status": job.status,
        "retry_count": job.retry_count,
        "last_error": job.last_error,
        "created": job.created,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "client_mutation_id": job.client_mutation_id,
    }
