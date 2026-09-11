from __future__ import annotations

import logging
import threading
from typing import Any


class LeaseLost(RuntimeError):
    pass


class LeaseHeartbeat:
    def __init__(
        self, database: Any, job_id: str, lease_seconds: int, logger: logging.Logger,
        interval_seconds: float | None = None,
    ) -> None:
        self._database = database
        self._job_id = job_id
        self._lease_seconds = lease_seconds
        self._logger = logger
        self._interval = interval_seconds or max(1.0, min(30.0, lease_seconds / 3))
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"lease-{job_id}", daemon=True)

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def __enter__(self) -> "LeaseHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self._interval + 1.0))

    def assert_owned(self) -> None:
        if self.lost:
            raise LeaseLost("Job lease was lost; stale work was abandoned")

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                renewed = self._database.renew_job_lease(self._job_id, self._lease_seconds)
            except Exception as exc:
                self._logger.error(
                    "job %s lease renewal failed: %s", self._job_id, type(exc).__name__,
                )
                self._lost.set()
                return
            if not renewed:
                self._logger.warning("job %s lease ownership was lost", self._job_id)
                self._lost.set()
                return
