"""
WO-026: Database-backed job queue tests.
"""

from unittest import mock
from uuid import uuid4

from django.test import SimpleTestCase, TestCase, override_settings

from claim.apps import DEFAULT_CFG
from claim.job_queue import (
    enqueue_process_claims,
    get_job_by_uuid,
    is_job_queue_enabled,
    process_next_job,
    should_enqueue_batch,
)
from claim.jobs import execute_job_handler
from claim.models import ClaimJob
from claim.services import process_claims_batch_or_enqueue
from claim.test_helpers import DummyUser


class JobQueueConfigTest(TestCase):
    def test_should_enqueue_respects_threshold(self):
        with mock.patch("claim.job_queue.is_job_queue_enabled", return_value=True):
            with mock.patch("claim.job_queue.async_threshold", return_value=3):
                self.assertFalse(should_enqueue_batch(["a", "b"]))
                self.assertTrue(should_enqueue_batch(["a", "b", "c"]))

    def test_should_enqueue_false_when_disabled(self):
        with mock.patch("claim.job_queue.is_job_queue_enabled", return_value=False):
            self.assertFalse(should_enqueue_batch(["a", "b", "c", "d"]))


@override_settings(
    MODULES={"claim": {**DEFAULT_CFG, "job_queue_async_threshold": 2}}
)
class EnqueueProcessClaimsTest(TestCase):
    def setUp(self):
        from claim.apps import ClaimConfig

        ClaimConfig.job_queue_enabled = True
        ClaimConfig.job_queue_async_threshold = 2

    def test_enqueue_process_claims_persists_payload(self):
        user = DummyUser()
        job = enqueue_process_claims(["uuid-1", "uuid-2"], user, client_mutation_id="cm-1")
        self.assertEqual(job.status, ClaimJob.STATUS_PENDING)
        self.assertEqual(job.job_type, ClaimJob.JOB_PROCESS_CLAIMS)
        self.assertEqual(job.payload["uuids"], ["uuid-1", "uuid-2"])
        self.assertEqual(job.payload["user_id_for_audit"], user.id_for_audit)
        self.assertEqual(job.client_mutation_id, "cm-1")
        job.delete()

    def test_process_claims_batch_or_enqueue_sync_by_default(self):
        user = DummyUser()
        with mock.patch("claim.services.processing.process_claims_batch", return_value=[]) as mock_batch:
            errors, job = process_claims_batch_or_enqueue(["one"], user)
        mock_batch.assert_called_once()
        self.assertEqual(errors, [])
        self.assertIsNone(job)

    def test_process_claims_batch_or_enqueue_async_when_over_threshold(self):
        user = DummyUser()
        with mock.patch("claim.services.processing.process_claims_batch") as mock_batch:
            errors, job = process_claims_batch_or_enqueue(["one", "two"], user)
        mock_batch.assert_not_called()
        self.assertEqual(errors, [])
        self.assertIsNotNone(job)
        self.assertEqual(job.status, ClaimJob.STATUS_PENDING)
        job.delete()


class ClaimJobWorkerTest(TestCase):
    def test_process_next_job_runs_handler_and_marks_completed(self):
        user = DummyUser()
        job = enqueue_process_claims([str(uuid4())], user)
        with mock.patch("claim.services.process_claims_batch", return_value=[]) as mock_batch:
            finished = process_next_job()
        self.assertIsNotNone(finished)
        self.assertEqual(finished.status, ClaimJob.STATUS_COMPLETED)
        self.assertEqual(finished.result, [])
        mock_batch.assert_called_once()
        job.delete()

    def test_process_next_job_retries_then_fails(self):
        job = ClaimJob.objects.create(
            job_type=ClaimJob.JOB_PROCESS_CLAIMS,
            payload={"uuids": [], "user_id_for_audit": 1},
            max_retries=1,
        )
        with mock.patch(
            "claim.services.process_claims_batch",
            side_effect=RuntimeError("boom"),
        ):
            first = process_next_job()
            self.assertEqual(first.status, ClaimJob.STATUS_PENDING)
            self.assertEqual(first.retry_count, 1)
            second = process_next_job()
            self.assertEqual(second.status, ClaimJob.STATUS_FAILED)
            self.assertIn("boom", second.last_error)
        job.delete()

    def test_execute_job_handler_unknown_type(self):
        job = ClaimJob.objects.create(job_type="unknown", payload={})
        with self.assertRaises(ValueError):
            execute_job_handler(job)
        job.delete()

    def test_get_job_by_uuid(self):
        job = ClaimJob.objects.create(
            job_type=ClaimJob.JOB_PROCESS_CLAIMS,
            payload={"uuids": [], "user_id_for_audit": 1},
        )
        self.assertEqual(get_job_by_uuid(str(job.uuid)).id, job.id)
        job.delete()


class JobQueueEnabledTest(SimpleTestCase):
    def test_is_job_queue_enabled_reads_config(self):
        with mock.patch("claim.job_queue._queue_config") as mock_cfg:
            mock_cfg.return_value.job_queue_enabled = True
            self.assertTrue(is_job_queue_enabled())
