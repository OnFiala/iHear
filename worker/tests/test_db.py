from contextlib import contextmanager
from typing import Any, Iterator

import psycopg

from ihear_worker.db import WorkerDatabase


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _Connection:
    def __init__(
        self,
        rejected_patient: str | None = None,
        due_patients: list[dict[str, str]] | None = None,
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.rejected_patient = rejected_patient
        self.due_patients = due_patients or [
            {"workspace_id": "workspace", "id": "due-today"},
            {"workspace_id": "workspace", "id": "due-tomorrow"},
        ]

    def execute(self, query: str, parameters: tuple[Any, ...] = ()) -> _Result:
        self.calls.append((query, parameters))
        if "from ihear.patients p" in query:
            return _Result(self.due_patients)
        if "ensure_scheduled_report_job" in query:
            if parameters[1] == self.rejected_patient:
                raise psycopg.errors.RaiseException("queue_capacity_exceeded")
            return _Result([{"result": {"enqueued": True}}])
        return _Result()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield


def test_schedule_due_reports_includes_today_and_tomorrow_after_local_0800() -> None:
    connection = _Connection()
    database = WorkerDatabase("postgresql://unused", "ihear_jobs", "worker")

    @contextmanager
    def fake_connection() -> Iterator[_Connection]:
        yield connection

    database.connection = fake_connection  # type: ignore[method-assign]

    assert database.schedule_due_reports(report_version=2) == 2

    assert "lock_sandbox_capacity" in connection.calls[0][0]
    selection_query, selection_parameters = next(
        call for call in connection.calls if "from ihear.patients p" in call[0]
    )
    normalized_query = " ".join(selection_query.split())
    assert "p.follow_up_date <= ((now() at time zone p.timezone)::date + 1)" in normalized_query
    assert "extract(hour from (now() at time zone p.timezone)) >= 8" in normalized_query
    assert selection_parameters == (2, 50)
    assert [
        parameters for query, parameters in connection.calls
        if "ensure_scheduled_report_job" in query
    ] == [
        ("workspace", "due-today", 2),
        ("workspace", "due-tomorrow", 2),
    ]


def test_schedule_due_reports_keeps_49_successes_when_the_50th_hits_capacity() -> None:
    due = [
        {"workspace_id": "workspace", "id": f"due-{index}"}
        for index in range(1, 51)
    ]
    connection = _Connection(rejected_patient="due-50", due_patients=due)
    database = WorkerDatabase("postgresql://unused", "ihear_jobs", "worker")

    @contextmanager
    def fake_connection() -> Iterator[_Connection]:
        yield connection

    database.connection = fake_connection  # type: ignore[method-assign]

    assert database.schedule_due_reports(report_version=2) == 49
    assert [
        parameters[1] for query, parameters in connection.calls
        if "ensure_scheduled_report_job" in query
    ] == [f"due-{index}" for index in range(1, 51)]
