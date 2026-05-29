"""
WO-026: Poll and execute pending claim jobs from the database-backed queue.
"""

import logging
import time

from django.core.management.base import BaseCommand

from claim.job_queue import default_queue_name, process_next_job

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Process pending claim jobs from the database-backed queue."

    def add_arguments(self, parser):
        parser.add_argument(
            "queue_name",
            nargs="?",
            default=None,
            help="Queue name to poll (defaults to ClaimConfig.job_queue_name).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one job and exit.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="Seconds to sleep when no jobs are available (ignored with --once).",
        )
        parser.add_argument(
            "--rate-limit",
            type=float,
            default=0.0,
            help="Minimum seconds between job executions.",
        )

    def handle(self, *args, **options):
        queue_name = options["queue_name"] or default_queue_name()
        once = options["once"]
        sleep_seconds = max(float(options["sleep"]), 0.1)
        rate_limit = max(float(options["rate_limit"]), 0.0)

        self.stdout.write(
            self.style.NOTICE(
                f"Claim job worker started (queue={queue_name}, once={once})"
            )
        )

        while True:
            job = process_next_job(queue_name=queue_name)
            if job is not None:
                self.stdout.write(
                    f"Processed job {job.uuid} -> {job.status}"
                )
                if rate_limit:
                    time.sleep(rate_limit)
            elif once:
                break
            else:
                time.sleep(sleep_seconds)
