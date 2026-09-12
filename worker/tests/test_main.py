from types import SimpleNamespace
from uuid import UUID

import pytest

from ihear_worker.main import (
    _handle_failure_safely,
    _job_contract_error,
    _new_attempt_database,
    _parse_queue_payload,
    _schedule_due_reports_safely,
)


def test_every_claim_attempt_gets_a_distinct_uuid_identity() -> None:
    settings = SimpleNamespace(database_url="postgresql://unused", queue_name="ihear_jobs")
    first = _new_attempt_database(settings)
    second = _new_attempt_database(settings)
    assert UUID(first.worker_id).version == 4
    assert UUID(second.worker_id).version == 4
    assert first.worker_id != second.worker_id


def test_expired_lease_failure_transition_cannot_escape_worker_loop() -> None:
    class RejectingProcessor:
        def handle_failure(self, job, error):
            raise RuntimeError("job_lease_not_owned")

    _handle_failure_safely(
        RejectingProcessor(),
        {"id": "job-id"},
        RuntimeError("work failed"),
        SimpleNamespace(lost=False),
        __import__("logging").getLogger("test"),
    )


def test_report_scheduling_failure_is_nonfatal_to_queue_loop(caplog) -> None:
    class SaturatedCoordinator:
        def schedule_due_reports(self, report_version, limit):
            raise RuntimeError("queue_capacity_exceeded")

    logger = __import__("logging").getLogger("test-scheduler")
    assert _schedule_due_reports_safely(SaturatedCoordinator(), 2, 50, logger) == 0
    assert "report scheduling failed: RuntimeError" in caplog.text


def test_queue_versions_are_routed_by_job_kind() -> None:
    settings = SimpleNamespace(pipeline_version=1, report_version=2)
    event_payload = {"kind": "event_analysis", "version": 1}
    report_payload = {"kind": "report", "version": 2}

    assert _job_contract_error(
        {"kind": "event_analysis", "version": 1}, event_payload, settings,
    ) is None
    assert _job_contract_error(
        {"kind": "report", "version": 2}, report_payload, settings,
    ) is None


def test_obsolete_report_version_reaches_processor_for_cache_reconciliation() -> None:
    error = _job_contract_error(
        {"kind": "report", "version": 1},
        {"kind": "report", "version": 1},
        SimpleNamespace(pipeline_version=1, report_version=2),
    )

    assert error is None


def test_malformed_queue_kind_is_rejected_before_claim() -> None:
    with pytest.raises(ValueError, match="invalid queue message contract"):
        _parse_queue_payload({
            "jobId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "kind": "unknown",
            "version": 2,
        })
