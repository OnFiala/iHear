from __future__ import annotations

import json
import logging
import signal
import time
from uuid import UUID, uuid4

from .astra import AstraClient
from .config import Settings
from .db import WorkerDatabase
from .jobs import JobProcessor
from .lease import LeaseHeartbeat, LeaseLost
from .model_download import install_models
from .models import ModelSuite
from .storage import PrivateStorage


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({"level": record.levelname, "message": record.getMessage()}, separators=(",", ":"))


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # httpx logs full request URLs at INFO. Model and storage URLs can contain
    # signed query values or capability-identifying object paths.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _new_attempt_database(settings: Settings) -> WorkerDatabase:
    return WorkerDatabase(settings.database_url, settings.queue_name, str(uuid4()))


def _handle_failure_safely(
    processor: JobProcessor, job: dict, error: Exception, lease: LeaseHeartbeat,
    logger: logging.Logger,
) -> None:
    if lease.lost:
        logger.warning("skipped stale failure write for job %s", job["id"])
        return
    try:
        processor.handle_failure(job, error)
    except Exception as transition_exc:
        # Ownership may have expired immediately before the heartbeat observed
        # it. SQL remains authoritative; rejection must not kill the loop.
        logger.error(
            "job %s failure transition rejected: %s",
            job["id"], type(transition_exc).__name__,
        )


def main() -> None:
    _configure_logging()
    logger = logging.getLogger("ihear_worker")
    settings = Settings.from_env()
    try:
        installed = install_models(settings.model_manifest, settings.model_dir)
        logger.info("verified models available: %s", ",".join(sorted(installed)))
    except Exception as exc:
        logger.error("model installation unavailable: %s", type(exc).__name__)

    coordinator = WorkerDatabase(settings.database_url, settings.queue_name, settings.worker_id)
    storage = PrivateStorage(settings.supabase_url, settings.supabase_service_role_key)
    models = ModelSuite(settings.model_manifest, settings.model_dir)
    astra = AstraClient(settings.openai_api_key)
    maintenance = JobProcessor(settings, coordinator, storage, models, astra)
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    next_schedule = 0.0
    next_cleanup = 0.0
    try:
        while not stopping:
            now = time.monotonic()
            if now >= next_schedule:
                scheduled = coordinator.schedule_due_reports(settings.report_version, limit=50)
                if scheduled:
                    logger.info("scheduled %d due reports", scheduled)
                next_schedule = now + 60
            if now >= next_cleanup:
                cleaned = maintenance.cleanup_terminal_audio(retention_days=7, limit=50)
                if cleaned:
                    logger.info("removed %d expired terminal audio objects", cleaned)
                next_cleanup = now + 3600

            message = coordinator.read_message(settings.lease_seconds)
            if not message:
                time.sleep(settings.poll_seconds)
                continue
            payload = message.payload
            try:
                job_id = str(UUID(str(payload.get("jobId"))))
                if payload.get("kind") not in {"event_analysis", "report"} or payload.get("version") != 1:
                    raise ValueError("invalid queue message contract")
            except (ValueError, TypeError, AttributeError):
                coordinator.archive_unusable_message(message.message_id)
                logger.error("archived invalid queue message %d", message.message_id)
                continue
            # A stable WORKER_ID is only a human label. Every claim gets a fresh,
            # immutable UUID so a prior attempt cannot pass ownership checks after
            # another attempt reclaims the same job.
            database = _new_attempt_database(settings)
            job = database.claim_job(job_id, settings.lease_seconds)
            if not job:
                continue
            processor = JobProcessor(settings, database, storage, models, astra)
            if job["kind"] != payload["kind"] or int(job["version"]) != payload["version"]:
                try:
                    database.fail_job(job["id"], "Queue payload disagrees with authoritative job row")
                except Exception as exc:
                    logger.error("job %s mismatch transition failed: %s", job["id"], type(exc).__name__)
                continue
            with LeaseHeartbeat(database, job["id"], settings.lease_seconds, logger) as lease:
                try:
                    processor.process(job, lease.assert_owned)
                    logger.info("completed %s job %s", job["kind"], job["id"])
                except LeaseLost:
                    logger.warning("abandoned stale job %s after lease loss", job["id"])
                except Exception as exc:
                    logger.error("job %s failed: %s", job["id"], type(exc).__name__)
                    _handle_failure_safely(processor, job, exc, lease, logger)
    finally:
        storage.close()


if __name__ == "__main__":
    main()
