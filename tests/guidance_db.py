"""Local-only, rolled-back integration of the real worker with an explicit provider fixture.

No provider traffic, raw audio or persistent test records. Run in the worker test
image with DATABASE_URL pointing to the local Supabase database on port 54322.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ihear_worker.astra import AstraClient
from ihear_worker.db import WorkerDatabase
from ihear_worker.jobs import JobProcessor
from ihear_worker.report import generate_report

url = os.environ["DATABASE_URL"]
target = urlparse(url)
assert target.hostname in {"127.0.0.1", "localhost", "host.docker.internal"} and target.port == 54322, "Local disposable database only"
root = Path(__file__).resolve().parents[1]
output = root / ".local/guidance-acceptance"
output.mkdir(parents=True, exist_ok=True)
profile = {
    "displayName": "Synthetic guidance fixture",
    "audiogram": {"frequencies": [250, 500, 1000, 2000, 4000, 8000], "left": [20, 25, 35, 40, 50, 55], "right": [20, 25, 30, 40, 45, 50]},
    "aids": {
        "side": "bilateral", "left": {"model": "Widex ALLURE BTE R D", "tier": "220"}, "right": {"model": "Widex ALLURE BTE R D", "tier": "220"},
        "app": {"name": "Widex Allure", "version": "fixture-1.0", "confirmedActions": ["allure_equalizer", "allure_programs"]},
    },
    "followUpDate": "2099-01-01", "note": "Synthetic hearing evaluation: difficulty following television dialogue; no speech recognition test supplied.", "timezone": "Europe/Prague",
}
analysis = {
    "duration_seconds": 10.0, "sample_rate": 48000, "rms_dbfs": -24.5, "peak_dbfs": -8.0, "clipping_fraction": 0.0, "silent": False, "quality_flags": [], "spectral_centroid_hz": 1800,
    "bands": [{"low_hz": low, "high_hz": high, "relative_energy": energy} for low, high, energy in [(80, 250, .04), (250, 500, .08), (500, 1000, .18), (1000, 2000, .28), (2000, 4000, .32), (4000, 8000, .10)]],
    "speech_activity": {"status": "ready", "fraction": .7, "model": "silero-vad", "version": "fixture", "aggregation": "duration_weighted"},
    "acoustic_categories": {"status": "ready", "categories": [{"label": "Speech", "score": .6}, {"label": "Music", "score": .3}], "model": "yamnet", "version": "fixture"},
}
provider_result = {
    "summary": "Synthetic fixture: the patient reports difficulty with TV dialogue. The phone recording contains speech-like activity and energy across several frequency bands.",
    "observations": ["Patient report, audiogram thresholds and phone measurements describe different aspects of the listening situation."],
    "recommendations": [{"text": "Review which voices or scenes are difficult and compare the patient's experience across available listening programs.", "evidence_refs": ["reported_event", "audiogram", "band:4"]}],
    "frequency_notes": [{"band_index": 4, "explanation": "The fixture has energy in this band; this does not establish what reached the ear or which words were understood.", "review_question": "How does the reported dialogue difficulty relate to the audiogram and a speech assessment?"}],
    "patient_summary": "You reported difficulty following the television. This recording alone cannot tell us which words you heard; your listening note helps your audiologist review the situation.",
    "tip_ids": ["share_clinician"], "device_action_ids": ["allure_equalizer"],
    "limitations": ["Explicit synthetic provider fixture; no live AI quality claim.", "Phone levels are uncalibrated and there is no speech recognition test."],
}
calls = []


def fixture_post(request_url, **kwargs):
    assert request_url.startswith("https://provider-fixture.invalid/v1/responses"), "Unexpected external request"
    calls.append(request_url)
    body = json.loads(kwargs["content"])
    assert body["model"] == "gpt-6-astra" and body["reasoning"] == {"effort": "low"}
    assert body["tools"] == [] and body["store"] is False
    assert len(kwargs["content"]) <= 6000
    if request_url.endswith("/input_tokens"):
        return httpx.Response(200, json={"object": "response.input_tokens", "input_tokens": 1500})
    return httpx.Response(200, json={
        "id": "response-explicit-local-fixture", "status": "completed", "service_tier": "default",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(provider_result)}]}],
        "usage": {"input_tokens": 1500, "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0}, "output_tokens": 500},
    })


class NoIO:
    def __getattr__(self, name):
        raise AssertionError(f"This test uses already-persisted fixture analysis; unexpected {name}")


with psycopg.connect(url, row_factory=dict_row) as connection:
    class TransactionDatabase(WorkerDatabase):
        @contextmanager
        def connection(self):
            yield connection

    database = TransactionDatabase(url, "ihear_jobs", str(uuid4()))
    workspace_id = connection.execute("select ihear.create_workspace_with_capability(%s,%s) as id", (os.urandom(32), os.urandom(32))).fetchone()["id"]
    try:
        connection.execute("update ihear.budget_accounts set total_limit_usd=100, daily_limit_usd=100, frozen_at=null, freeze_reason=null where account_key='astra-global'")
        patient_id = connection.execute("select id from ihear.create_patient(%s,%s,%s,%s,%s,%s,%s)", (workspace_id, profile["displayName"], Jsonb(profile["audiogram"]), Jsonb(profile["aids"]), profile["followUpDate"], profile["note"], profile["timezone"])).fetchone()["id"]
        event_id, fingerprint = uuid4(), os.urandom(32)
        capture = {"sampleRate": 48000, "sourceLabel": "Explicit synthetic fixture", "routing": "unknown", "trackSettings": {"autoGainControl": True}}
        path = f"{workspace_id}/{patient_id}/{event_id}.wav"
        connection.execute("select ihear.reserve_event_upload(%s,%s,%s,%s,'difficult','Following one person','Music or TV',%s,%s,%s,%s,%s,960044,10,1)", (event_id, workspace_id, patient_id, os.urandom(32), datetime.now(timezone.utc), Jsonb(capture), path, os.urandom(32), fingerprint))
        connection.execute("select ihear.finalize_event_upload(%s,%s,%s,%s)", (event_id, workspace_id, patient_id, fingerprint))
        job_id = connection.execute("select id from ihear.jobs where event_id=%s and kind='event_analysis'", (event_id,)).fetchone()["id"]
        job = database.claim_job(str(job_id), 180)
        assert job
        analysis_id = database.persist_analysis(str(job_id), "ready", analysis, {"fixture": True, "not_measured_audio": True})
        database.mark_audio_deleted(str(event_id), path)
        settings = SimpleNamespace(device_capabilities=root / "config/device-capabilities.json", openai_api_key="explicit-fixture-only", pipeline_version=1, report_version=4)
        processor = JobProcessor(settings, database, NoIO(), NoIO(), AstraClient("explicit-fixture-only", "https://provider-fixture.invalid/v1"))
        with patch("ihear_worker.astra.httpx.post", fixture_post):
            processor.process(job)
        stored = database.existing_interpretation(analysis_id)
        assert stored and stored["status"] == "ready", connection.execute(
            "select status, error from ihear.interpretations where analysis_id=%s",
            (analysis_id,),
        ).fetchone()
        assert stored["result"]["patient_summary"] == provider_result["patient_summary"]
        assert stored["result"]["frequency_notes"] == provider_result["frequency_notes"]
        assert stored["result"]["device_actions"][0]["id"] == "allure_equalizer"
        assert len(calls) == 2, calls
        usage = connection.execute("select state, actual_usd from ihear.api_usage where event_id=%s", (event_id,)).fetchone()
        assert usage and str(usage["actual_usd"]) == "0.040000", usage
        report_id = connection.execute("select ihear.ensure_report_job(%s,%s,4) as result", (workspace_id, patient_id)).fetchone()["result"]["reportId"]
        report, patient, events = database.report_context({"report_id": report_id, "patient_id": patient_id, "workspace_id": workspace_id})
        assert len(events) == 1 and events[0]["interpretation_prompt_version"] == "ihear-event-v2"
        pdf = generate_report(patient, events, int(report["input_revision"]), device_catalog=json.loads((root / "config/device-capabilities.json").read_text()))
        assert pdf.startswith(b"%PDF")
        (output / "synthetic-guidance-v4.pdf").write_bytes(pdf)
        event = {"id": str(event_id), "patientId": str(patient_id), "kind": "difficult", "difficulty": "Following one person", "environment": "Music or TV", "capturedAt": "2026-09-13T12:00:00Z", "createdAt": "2026-09-13T12:00:00Z", "status": "ready", "capture": capture, "profileSnapshot": profile, "analysis": analysis, "interpretation": {"status": "ready", "promptVersion": "ihear-event-v2", "model": "gpt-6-astra", "result": stored["result"]}}
        (output / "fixture-event.json").write_text(json.dumps(event))
        print(json.dumps({"result": "PASS", "provider": "explicit fixture; zero external calls", "calls_intercepted": len(calls), "interpretation_version": "ihear-event-v2", "report_version": 4, "transaction": "rollback"}))
    finally:
        connection.rollback()
    assert connection.execute("select count(*) as count from ihear.workspaces where id=%s", (workspace_id,)).fetchone()["count"] == 0
