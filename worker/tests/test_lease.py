import logging
import threading
import time

import pytest

from ihear_worker.lease import LeaseHeartbeat, LeaseLost


class RenewalDatabase:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.called = threading.Event()

    def renew_job_lease(self, job_id, lease_seconds):
        self.called.set()
        if self.error:
            raise self.error
        return self.result


@pytest.mark.parametrize(
    "database",
    [RenewalDatabase(result=False), RenewalDatabase(error=RuntimeError("database unavailable"))],
)
def test_heartbeat_marks_false_or_failed_renewal_as_lost(database) -> None:
    with LeaseHeartbeat(database, "job-1", 120, logging.getLogger("test"), interval_seconds=0.01) as lease:
        assert database.called.wait(0.5)
        for _ in range(100):
            if lease.lost:
                break
            time.sleep(0.001)
        with pytest.raises(LeaseLost):
            lease.assert_owned()


def test_heartbeat_keeps_owned_lease_live() -> None:
    database = RenewalDatabase(result=True)
    with LeaseHeartbeat(database, "job-1", 120, logging.getLogger("test"), interval_seconds=0.01) as lease:
        assert database.called.wait(0.5)
        lease.assert_owned()
        assert lease.lost is False
