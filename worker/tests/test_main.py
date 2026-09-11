from types import SimpleNamespace
from uuid import UUID

from ihear_worker.main import _handle_failure_safely, _new_attempt_database


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
