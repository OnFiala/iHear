from __future__ import annotations

from importlib.metadata import version
import json
import logging
from typing import Any, Callable

import httpx

from .astra import (
    MAXIMUM_COST_USD, MODEL, PROMPT_VERSION, AmbiguousProviderFailure, AstraClient,
    AstraCostExceeded, AstraRejected, AstraUnavailable, build_event_input, prepare_request,
)
from .config import Settings
from .db import ReportInputStale, WorkerDatabase
from .lease import LeaseLost
from .dsp import AudioValidationError, analyze_deterministic, decode_pcm16_mono_wav, interpretation_is_ambiguous, resample_for_models
from .models import ModelSuite
from .report import generate_report
from .storage import PrivateStorage


logger = logging.getLogger("ihear_worker")
MAX_REPORT_BYTES = 4_000_000


class JobProcessor:
    def __init__(
        self,
        settings: Settings,
        database: WorkerDatabase,
        storage: PrivateStorage,
        models: ModelSuite,
        astra: AstraClient,
    ):
        self.settings = settings
        self.database = database
        self.storage = storage
        self.models = models
        self.astra = astra
        self.device_catalog = (
            json.loads(settings.device_capabilities.read_text(encoding="utf-8"))
            if settings.device_capabilities.exists() else {}
        )

    def process(self, job: dict[str, Any], lease_guard: Callable[[], None] | None = None) -> None:
        guard = lease_guard or (lambda: None)
        guard()
        if job["kind"] == "event_analysis":
            self._process_event(job, guard)
        elif job["kind"] == "report":
            self._process_report(job, guard)
        else:
            raise ValueError(f"Unsupported job kind: {job['kind']}")

    def _process_event(self, job: dict[str, Any], guard: Callable[[], None]) -> None:
        event, history = self.database.event_context(job)
        guard()
        existing_analysis = self.database.existing_analysis(job)
        if existing_analysis:
            analysis_id = existing_analysis["id"]
            analysis = existing_analysis["result"]
        else:
            audio_bytes = self.storage.download(self.settings.audio_bucket, event["audio_object_path"])
            audio = decode_pcm16_mono_wav(audio_bytes)
            analysis = analyze_deterministic(audio)
            waveform_16khz = resample_for_models(audio)
            speech, categories = self.models.infer(waveform_16khz)
            guard()
            analysis["speech_activity"] = speech
            analysis["acoustic_categories"] = categories
            provenance = {
                "pipeline_version": self.settings.pipeline_version,
                "dsp": {"numpy": version("numpy"), "scipy": version("scipy"), "rate": "native"},
                "model_input_sample_rate": 16000,
                "silero_vad": {"version": speech.get("version"), "status": speech.get("status")},
                "yamnet": {"version": categories.get("version"), "status": categories.get("status")},
            }
            analysis_id = self.database.persist_analysis(job["id"], "ready", analysis, provenance)

        # Analysis is durable before raw-audio custody closes. This runs for both
        # a newly persisted analysis and a retry that found the ready analysis.
        if event.get("audio_object_path") and not event.get("audio_deleted_at"):
            guard()
            self.storage.delete(self.settings.audio_bucket, event["audio_object_path"])
            guard()
            self.database.mark_audio_deleted(event["id"], event["audio_object_path"])

        existing_interpretation = self.database.existing_interpretation(analysis_id)
        guard()
        if existing_interpretation and existing_interpretation["status"] in {
            "ready", "held_ambiguity", "held_budget", "unavailable", "skipped", "failed"
        }:
            self.database.finish_job(job["id"], {
                "analysisId": analysis_id,
                "interpretationId": existing_interpretation["id"],
                "interpretationStatus": existing_interpretation["status"],
            })
            return

        base_provenance = {
            "model": MODEL,
            "prompt_version": PROMPT_VERSION,
            "reasoning_effort": "low",
            "tools": [],
            "max_output_tokens": 1200,
        }
        if not self.settings.openai_api_key:
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "unavailable", None, base_provenance,
                "OPENAI_API_KEY is not configured",
            )
            self.database.finish_job(job["id"], {"analysisId": analysis_id, "interpretationId": interpretation_id, "interpretationStatus": "unavailable"})
            return
        if interpretation_is_ambiguous(analysis):
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "held_ambiguity", None, base_provenance,
                "Deterministic evidence is insufficient for bounded interpretation",
            )
            self.database.finish_job(job["id"], {"analysisId": analysis_id, "interpretationId": interpretation_id, "interpretationStatus": "held_ambiguity"})
            return

        idempotency_key = f"event:{event['id']}:analysis:{analysis_id}:{MODEL}:{PROMPT_VERSION}"
        try:
            payload = build_event_input(event, analysis, history, self.device_catalog)
            local_request = prepare_request(payload)
        except (ValueError, AstraRejected) as exc:
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "failed", None, base_provenance,
                f"Preflight rejected bounded Astra input: {_bounded_error(exc)}",
            )
            self.database.finish_job(job["id"], {
                "analysisId": analysis_id,
                "interpretationId": interpretation_id,
                "interpretationStatus": "failed",
            })
            return
        base_provenance["request_body_bytes"] = len(local_request[1])
        guard()
        reservation = self.database.reserve_budget(job, MAXIMUM_COST_USD, idempotency_key)
        reservation_status = reservation.get("status")
        if reservation_status in {"held_budget", "held_budget_frozen", "held_event_limit", "held_ambiguity"}:
            interpretation_status = "held_ambiguity" if reservation_status == "held_ambiguity" else "held_budget"
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id,
                interpretation_status,
                None, {**base_provenance, "reservation_status": reservation_status}, reservation_status,
            )
            self.database.finish_job(job["id"], {"analysisId": analysis_id, "interpretationId": interpretation_id, "interpretationStatus": interpretation_status})
            return
        if reservation_status == "existing":
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "held_ambiguity", None,
                {**base_provenance, "reservation_status": "existing", "reservation_state": reservation.get("state")},
                "A prior reservation exists without a durable interpretation; provider retry is forbidden",
                reservation.get("usageId"),
            )
            self.database.finish_job(job["id"], {"analysisId": analysis_id, "interpretationId": interpretation_id, "interpretationStatus": "held_ambiguity"})
            return
        if reservation_status != "reserved" or not reservation.get("usageId"):
            raise RuntimeError(f"Unexpected budget reservation status: {reservation_status}")

        usage_id = str(reservation["usageId"])
        try:
            guard()
        except LeaseLost:
            try:
                self.database.release_budget(usage_id)
            except Exception as exc:
                logger.error("known no-call reservation release failed: %s", type(exc).__name__)
            raise
        try:
            prepared_request = self.astra.prepare(payload, prepared_request=local_request)
        except (AstraUnavailable, AstraRejected) as exc:
            self.database.release_budget(usage_id)
            guard()
            unavailable = isinstance(exc, AstraUnavailable)
            interpretation_status = "unavailable" if unavailable else "failed"
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, interpretation_status, None,
                {**base_provenance, "input_token_preflight": "failed_closed"},
                _bounded_error(exc), usage_id,
            )
            self.database.finish_job(job["id"], {
                "analysisId": analysis_id,
                "interpretationId": interpretation_id,
                "interpretationStatus": interpretation_status,
            })
            return
        base_provenance["preflight_input_tokens"] = prepared_request.input_tokens
        try:
            guard()
        except LeaseLost:
            try:
                self.database.release_budget(usage_id)
            except Exception as exc:
                logger.error("known no-call reservation release failed: %s", type(exc).__name__)
            raise
        try:
            result = self.astra.interpret(prepared_request, idempotency_key)
        except AstraCostExceeded as exc:
            reason = "Provider usage exceeded the pre-reserved request envelope; account frozen"
            self.database.settle_budget_overage(
                usage_id, exc.actual_cost_usd, exc.provider_request_id, reason,
            )
            guard()
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "failed", None,
                {
                    **base_provenance,
                    "provider_request_id": exc.provider_request_id,
                    "usage": exc.usage,
                    "cost_accounting": "overage_settled_account_frozen",
                },
                f"{reason}: {exc.actual_cost_usd}", usage_id,
            )
        except AstraUnavailable as exc:
            self.database.release_budget(usage_id)
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "unavailable", None, base_provenance, str(exc), usage_id,
            )
        except AstraRejected as exc:
            self.database.release_budget(usage_id)
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "failed", None, base_provenance, str(exc), usage_id,
            )
        except Exception as exc:
            interpretation_id = self.database.persist_interpretation(
                job["id"], analysis_id, "held_ambiguity", None,
                {**base_provenance, "provider_outcome": "unknown"}, _bounded_error(exc), usage_id,
            )
        else:
            guard()
            interpretation_id = self.database.settle_and_persist_interpretation(
                job["id"], analysis_id, usage_id, result.actual_cost_usd,
                result.provider_request_id, result.result,
                {**base_provenance, "provider_request_id": result.provider_request_id, "usage": result.usage},
            )
        final = self.database.existing_interpretation(analysis_id)
        guard()
        self.database.finish_job(job["id"], {
            "analysisId": analysis_id,
            "interpretationId": interpretation_id,
            "interpretationStatus": final["status"] if final else "unknown",
        })

    def _process_report(self, job: dict[str, Any], guard: Callable[[], None]) -> None:
        report, patient, events = self.database.report_context(job)
        if int(report["report_version"]) != int(job["version"]):
            raise ValueError("Report row version disagrees with authoritative job row")
        if report.get("status") == "ready" and report.get("object_path"):
            guard()
            self.database.finish_job(job["id"], {
                "reportId": report["id"],
                "objectPath": report["object_path"],
                "inputRevision": report["input_revision"],
                "reconciled": True,
            })
            return
        if int(job["version"]) != self.settings.report_version:
            raise ValueError(
                f"Unsupported report version {job['version']}; "
                f"worker expects version {self.settings.report_version}"
            )
        contents = generate_report(patient, events, int(report["input_revision"]))
        if len(contents) > MAX_REPORT_BYTES:
            raise RuntimeError("Generated report exceeds the 4 MB delivery limit")
        object_path = (
            f"{job['workspace_id']}/{job['patient_id']}/{report['id']}/"
            f"{self.database.worker_id}.pdf"
        )
        guard()
        self.storage.upload_pdf(self.settings.report_bucket, object_path, contents)
        try:
            guard()
            self.database.persist_report(job["id"], object_path)
        except Exception:
            self.storage.delete(self.settings.report_bucket, object_path)
            raise
        guard()
        self.database.finish_job(job["id"], {
            "reportId": report["id"], "objectPath": object_path,
            "inputRevision": report["input_revision"], "bytes": len(contents),
        })

    def handle_failure(self, job: dict[str, Any], error: Exception) -> None:
        message = _bounded_error(error)
        if isinstance(error, (AudioValidationError, LookupError, ReportInputStale, ValueError)):
            if job["kind"] == "event_analysis" and not self.database.existing_analysis(job):
                self.database.persist_analysis(
                    job["id"], "failed", None,
                    {"pipeline_version": self.settings.pipeline_version}, message,
                )
            self.database.fail_job(job["id"], message)
            return
        delay = min(900, 30 * (2 ** max(0, int(job.get("attempt_count", 1)) - 1)))
        self.database.retry_job(job["id"], message, delay)

    def cleanup_terminal_audio(self, retention_days: int = 7, limit: int = 50) -> int:
        cleaned = 0
        for candidate in self.database.terminal_audio_cleanup_candidates(retention_days, limit):
            self.storage.delete(self.settings.audio_bucket, candidate["audio_object_path"])
            self.database.mark_audio_deleted(candidate["id"], candidate["audio_object_path"])
            cleaned += 1
        return cleaned


def _bounded_error(error: Exception) -> str:
    return f"{type(error).__name__}: {str(error).replace(chr(10), ' ').strip()}"[:500]
