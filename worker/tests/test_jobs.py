from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from ihear_worker.astra import AstraCostExceeded, AstraRejected
from ihear_worker.jobs import JobProcessor


class FakeDatabase:
    def __init__(self):
        self.persisted = []
        self.finished = []
        self.reserve_calls = 0

    def event_context(self, job):
        return ({
            "id": "11111111-1111-1111-1111-111111111111",
            "kind": "difficult", "difficulty": "speech", "environment": "cafe",
            "captured_at": "2026-09-11T10:00:00Z", "profile_snapshot": {},
            "audio_object_path": "unused.wav", "audio_deleted_at": "2026-09-11T10:01:00Z",
        }, [])

    def existing_analysis(self, job):
        return {
            "id": "22222222-2222-2222-2222-222222222222",
            "result": {
                "duration_seconds": 10.0, "silent": False, "clipping_fraction": 0,
                "speech_activity": {"status": "ready", "fraction": 0.7},
            },
        }

    def existing_interpretation(self, analysis_id):
        return None

    def reserve_budget(self, job, maximum_cost, idempotency_key):
        self.reserve_calls += 1
        return {"status": "existing", "usageId": "33333333-3333-3333-3333-333333333333", "state": "reserved"}

    def persist_interpretation(self, *args):
        self.persisted.append(args)
        return "44444444-4444-4444-4444-444444444444"

    def finish_job(self, job_id, result):
        self.finished.append((job_id, result))


class FailIfCalledAstra:
    def prepare(self, *args, **kwargs):
        return SimpleNamespace(input_tokens=100, encoded=b"{}")

    def interpret(self, *args, **kwargs):
        raise AssertionError("existing reservation must not call Astra")


def test_existing_orphan_reservation_never_repeats_provider_call(tmp_path: Path) -> None:
    device_catalog = tmp_path / "device.json"
    device_catalog.write_text("{}", encoding="utf-8")
    database = FakeDatabase()
    processor = JobProcessor(
        SimpleNamespace(
            device_capabilities=device_catalog,
            openai_api_key="configured",
            pipeline_version=1,
        ),
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        FailIfCalledAstra(),
    )
    job = {
        "id": "55555555-5555-5555-5555-555555555555",
        "kind": "event_analysis", "version": 1,
        "workspace_id": "66666666-6666-6666-6666-666666666666",
        "patient_id": "77777777-7777-7777-7777-777777777777",
        "event_id": "11111111-1111-1111-1111-111111111111",
    }
    processor.process(job)
    assert database.reserve_calls == 1
    assert database.persisted[0][2] == "held_ambiguity"
    assert database.finished[0][1]["interpretationStatus"] == "held_ambiguity"


class MissingKeyDatabase(FakeDatabase):
    def existing_analysis(self, job):
        analysis = super().existing_analysis(job)
        analysis["result"]["speech_activity"]["fraction"] = 0.0
        return analysis


def test_missing_key_is_unavailable_even_when_evidence_is_ambiguous(tmp_path: Path) -> None:
    device_catalog = tmp_path / "device.json"
    device_catalog.write_text("{}", encoding="utf-8")
    database = MissingKeyDatabase()
    processor = JobProcessor(
        SimpleNamespace(
            device_capabilities=device_catalog,
            openai_api_key=None,
            pipeline_version=1,
        ),
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        FailIfCalledAstra(),
    )
    processor.process({
        "id": "55555555-5555-5555-5555-555555555555",
        "kind": "event_analysis", "version": 1,
        "workspace_id": "66666666-6666-6666-6666-666666666666",
        "patient_id": "77777777-7777-7777-7777-777777777777",
        "event_id": "11111111-1111-1111-1111-111111111111",
    })
    assert database.reserve_calls == 0
    assert database.persisted[0][2] == "unavailable"
    assert database.finished[0][1]["interpretationStatus"] == "unavailable"


class OverageDatabase(FakeDatabase):
    def __init__(self):
        super().__init__()
        self.settled_overage = None
        self.interpretation_status = None

    def existing_interpretation(self, analysis_id):
        if self.interpretation_status:
            return {"id": "44444444-4444-4444-4444-444444444444", "status": self.interpretation_status}
        return None

    def reserve_budget(self, job, maximum_cost, idempotency_key):
        self.reserve_calls += 1
        return {"status": "reserved", "usageId": "33333333-3333-3333-3333-333333333333"}

    def settle_budget_overage(self, *args):
        self.settled_overage = args

    def persist_interpretation(self, *args):
        self.persisted.append(args)
        self.interpretation_status = args[2]
        return "44444444-4444-4444-4444-444444444444"


class OverageAstra:
    def prepare(self, *args, **kwargs):
        return SimpleNamespace(input_tokens=100, encoded=b"{}")

    def interpret(self, *args, **kwargs):
        raise AstraCostExceeded(
            Decimal("0.160013"), "resp_overage", {"input_tokens": 8001, "output_tokens_including_reasoning": 1200},
        )


def test_completed_provider_overage_is_settled_frozen_and_terminal(tmp_path: Path) -> None:
    device_catalog = tmp_path / "device.json"
    device_catalog.write_text("{}", encoding="utf-8")
    database = OverageDatabase()
    processor = JobProcessor(
        SimpleNamespace(
            device_capabilities=device_catalog,
            openai_api_key="configured",
            pipeline_version=1,
        ),
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        OverageAstra(),
    )
    processor.process({
        "id": "55555555-5555-5555-5555-555555555555",
        "kind": "event_analysis", "version": 1,
        "workspace_id": "66666666-6666-6666-6666-666666666666",
        "patient_id": "77777777-7777-7777-7777-777777777777",
        "event_id": "11111111-1111-1111-1111-111111111111",
    })
    assert database.settled_overage[:3] == (
        "33333333-3333-3333-3333-333333333333", Decimal("0.160013"), "resp_overage",
    )
    assert database.persisted[0][2] == "failed"
    assert database.finished[0][1]["interpretationStatus"] == "failed"


class TokenRejectDatabase(OverageDatabase):
    def __init__(self):
        super().__init__()
        self.released = []

    def release_budget(self, usage_id):
        self.released.append(usage_id)


class TokenRejectAstra:
    def prepare(self, *args, **kwargs):
        raise AstraRejected("Astra input requires 8001 tokens; reserved limit is 8000")

    def interpret(self, *args, **kwargs):
        raise AssertionError("generation must not run after token-count rejection")


def test_token_count_runs_after_reservation_and_releases_before_terminal_failure(tmp_path: Path) -> None:
    device_catalog = tmp_path / "device.json"
    device_catalog.write_text("{}", encoding="utf-8")
    database = TokenRejectDatabase()
    processor = JobProcessor(
        SimpleNamespace(
            device_capabilities=device_catalog,
            openai_api_key="configured",
            pipeline_version=1,
        ),
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        TokenRejectAstra(),
    )
    processor.process({
        "id": "55555555-5555-5555-5555-555555555555",
        "kind": "event_analysis", "version": 1,
        "workspace_id": "66666666-6666-6666-6666-666666666666",
        "patient_id": "77777777-7777-7777-7777-777777777777",
        "event_id": "11111111-1111-1111-1111-111111111111",
    })
    assert database.reserve_calls == 1
    assert database.released == ["33333333-3333-3333-3333-333333333333"]
    assert database.persisted[0][2] == "failed"
    assert database.finished[0][1]["interpretationStatus"] == "failed"


class CustodyDatabase(MissingKeyDatabase):
    def __init__(self):
        super().__init__()
        self.marked = []

    def event_context(self, job):
        event, history = super().event_context(job)
        event["audio_deleted_at"] = None
        return event, history

    def mark_audio_deleted(self, event_id, object_path):
        self.marked.append((event_id, object_path))


class RetryDeleteStorage:
    def __init__(self):
        self.calls = 0

    def delete(self, bucket, path):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary storage failure")


def test_ready_analysis_retries_raw_audio_custody_close(tmp_path: Path) -> None:
    device_catalog = tmp_path / "device.json"
    device_catalog.write_text("{}", encoding="utf-8")
    database = CustodyDatabase()
    storage = RetryDeleteStorage()
    processor = JobProcessor(
        SimpleNamespace(
            device_capabilities=device_catalog,
            openai_api_key=None,
            pipeline_version=1,
            audio_bucket="ihear-audio",
        ),
        database,
        storage,
        SimpleNamespace(),
        FailIfCalledAstra(),
    )
    job = {
        "id": "55555555-5555-5555-5555-555555555555",
        "kind": "event_analysis", "version": 1,
        "workspace_id": "66666666-6666-6666-6666-666666666666",
        "patient_id": "77777777-7777-7777-7777-777777777777",
        "event_id": "11111111-1111-1111-1111-111111111111",
    }
    with pytest.raises(RuntimeError, match="temporary storage failure"):
        processor.process(job)
    processor.process(job)
    assert storage.calls == 2
    assert database.marked == [("11111111-1111-1111-1111-111111111111", "unused.wav")]
    assert database.persisted[0][2] == "unavailable"


class ReadyReportDatabase:
    worker_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    def __init__(self):
        self.finished = []

    def report_context(self, job):
        return (
            {
                "id": job["report_id"],
                "input_revision": 7,
                "report_version": 1,
                "status": "ready",
                "object_path": "workspace/patient/report/prior-attempt.pdf",
            },
            {"display_name": "unused"},
            [],
        )

    def finish_job(self, job_id, result):
        self.finished.append((job_id, result))


class FailIfReportStorageCalled:
    def upload_pdf(self, *args, **kwargs):
        raise AssertionError("ready report retry must not upload")

    def delete(self, *args, **kwargs):
        raise AssertionError("ready report retry must not delete")


def test_ready_report_retry_reconciles_existing_object_without_regeneration() -> None:
    database = ReadyReportDatabase()
    processor = JobProcessor(
        SimpleNamespace(device_capabilities=Path("/nonexistent"), report_version=2),
        database, FailIfReportStorageCalled(), SimpleNamespace(), SimpleNamespace(),
    )
    processor.process({
        "id": "job-id",
        "kind": "report",
        "report_id": "report-id",
        "version": 1,
        "workspace_id": "workspace",
        "patient_id": "patient",
    })
    assert database.finished == [(
        "job-id",
        {
            "reportId": "report-id",
            "objectPath": "workspace/patient/report/prior-attempt.pdf",
            "inputRevision": 7,
            "reconciled": True,
        },
    )]


class NewReportDatabase(ReadyReportDatabase):
    def __init__(self):
        super().__init__()
        self.persisted_path = None

    def report_context(self, job):
        return (
            {
                "id": job["report_id"],
                "input_revision": 7,
                "report_version": 2,
                "status": "pending",
                "object_path": None,
            },
            {"display_name": "Synthetic"},
            [],
        )

    def persist_report(self, job_id, object_path):
        self.persisted_path = object_path


class RecordingReportStorage:
    def __init__(self):
        self.uploaded = None

    def upload_pdf(self, bucket, path, contents):
        self.uploaded = (bucket, path, len(contents))

    def delete(self, *args, **kwargs):
        raise AssertionError("successful report must not delete")


def test_new_report_object_is_scoped_to_claim_attempt() -> None:
    database = NewReportDatabase()
    storage = RecordingReportStorage()
    processor = JobProcessor(
        SimpleNamespace(report_bucket="ihear-reports", device_capabilities=Path("/nonexistent"), report_version=2),
        database,
        storage,
        SimpleNamespace(),
        SimpleNamespace(),
    )
    processor.process({
        "id": "job-id",
        "kind": "report",
        "report_id": "report-id",
        "version": 2,
        "workspace_id": "workspace",
        "patient_id": "patient",
    })
    expected = "workspace/patient/report-id/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.pdf"
    assert database.persisted_path == expected
    assert storage.uploaded[0:2] == ("ihear-reports", expected)
    assert storage.uploaded[2] < 4_000_000


class ObsoletePendingReportDatabase(ReadyReportDatabase):
    def __init__(self):
        super().__init__()
        self.failed = None

    def report_context(self, job):
        return (
            {
                "id": job["report_id"],
                "input_revision": 7,
                "report_version": 1,
                "status": "pending",
                "object_path": None,
            },
            {"display_name": "Synthetic"},
            [],
        )

    def fail_job(self, job_id, error):
        self.failed = (job_id, error)


def test_pending_obsolete_report_is_failed_without_rendering_template_two() -> None:
    database = ObsoletePendingReportDatabase()
    processor = JobProcessor(
        SimpleNamespace(device_capabilities=Path("/nonexistent"), report_version=2),
        database,
        FailIfReportStorageCalled(),
        SimpleNamespace(),
        SimpleNamespace(),
    )
    job = {
        "id": "old-report-job",
        "kind": "report",
        "report_id": "report-id",
        "version": 1,
        "workspace_id": "workspace",
        "patient_id": "patient",
    }

    with pytest.raises(ValueError, match="Unsupported report version 1") as exc_info:
        processor.process(job)
    processor.handle_failure(job, exc_info.value)

    assert database.failed == (
        "old-report-job",
        "ValueError: Unsupported report version 1; worker expects version 2",
    )
