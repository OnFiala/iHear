from contextlib import contextmanager
from typing import Any, Iterator

from ihear_worker.db import WorkerDatabase


class _Result:
    def __init__(self, rows: list[dict[str, str]] | None = None):
        self._rows = rows or []

    def fetchall(self) -> list[dict[str, str]]:
        return self._rows


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, parameters: tuple[Any, ...]) -> _Result:
        self.calls.append((query, parameters))
        if "from ihear.patients p" in query:
            return _Result([
                {"workspace_id": "workspace", "id": "due-today"},
                {"workspace_id": "workspace", "id": "due-tomorrow"},
            ])
        return _Result()


def test_schedule_due_reports_includes_today_and_tomorrow_after_local_0800() -> None:
    connection = _Connection()
    database = WorkerDatabase("postgresql://unused", "ihear_jobs", "worker")

    @contextmanager
    def fake_connection() -> Iterator[_Connection]:
        yield connection

    database.connection = fake_connection  # type: ignore[method-assign]

    assert database.schedule_due_reports(report_version=2) == 2

    selection_query, selection_parameters = connection.calls[0]
    normalized_query = " ".join(selection_query.split())
    assert "p.follow_up_date <= ((now() at time zone p.timezone)::date + 1)" in normalized_query
    assert "extract(hour from (now() at time zone p.timezone)) >= 8" in normalized_query
    assert selection_parameters == (2, 50)
    assert [parameters for query, parameters in connection.calls if "ensure_report_job" in query] == [
        ("workspace", "due-today", 2),
        ("workspace", "due-tomorrow", 2),
    ]
