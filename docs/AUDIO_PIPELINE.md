# Audio analysis, interpretation, and report pipeline

This document describes audio pipeline version 1 and report template version 2. The worker is a single-concurrency Python 3.11 CPU process. It consumes authoritative `ihear.jobs` rows through the durable `ihear_jobs` pgmq queue. Database names and SQL function signatures are defined in `docs/DATA_MODEL.md` and the migration is executable truth.

## Evidence boundaries

The pipeline keeps three evidence types separate:

1. Deterministic measurements come from the uploaded PCM16 mono WAV. They include duration, native sample rate, RMS and peak dBFS, clipping fraction, native-rate STFT band energy, and spectral centroid.
2. Model estimates come from Silero VAD and YAMNet after a separate 16 kHz resample. They are estimates, carry model/version provenance, and can be unavailable independently.
3. Astra interpretation is optional, budget-gated, and based only on bounded structured features. It never receives audio and performs no transcription or tool call.

dBFS is an uncalibrated digital level. It must not be described as dB SPL or dB HL and cannot be compared with an audiogram. The system does not infer speech content, speaker identity, intelligibility, hearing-aid gain, or clinical conclusions.

## WAV validation and deterministic DSP

The worker validates the object again after download: RIFF/WAV readable by SciPy, signed 16-bit PCM, one channel, sample rate 8-96 kHz, at least one sample, no more than 2,202,000 bytes, and no more than 10.1 seconds. Failure is visible and terminal after a bounded job transition; the raw object remains for the seven-day terminal-failure retention window.

DSP stays at the captured sample rate. Samples are scaled by 32768. RMS and peak use full scale as their reference. Exact digital silence produces nullable `rms_dbfs`; it is never represented by an invented floor. Clipping is the fraction of PCM values whose magnitude is at least 32767.

The STFT uses a Hann window targeted at 25 ms, rounded up to a power of two, with 50 percent overlap. It does not pad the signal boundary. Mean squared magnitude is accumulated into fixed bands 80-250, 250-500, 500-1000, 1000-2000, 2000-4000, and 4000-8000 Hz. Bands above Nyquist contribute zero. `relative_energy` divides each band by total energy above 20 Hz. Spectral centroid is the power-weighted frequency mean.

Quality flags are deterministic:

- `silence`: RMS is absent or below -60 dBFS.
- `clipping`: at least 1 percent of samples are clipped.
- `too_short`: duration is below 0.5 seconds.
- `very_quiet`: non-silent RMS is below -45 dBFS.

Astra interpretation is held as ambiguous when the recording is silent, shorter than one second, at least 10 percent clipped, Silero is unavailable, or Silero estimates less than 5 percent active frames.

## CPU model inference

Model artifacts are downloaded at runtime and are never committed. `config/models.json` pins the URL, SHA-256 digest, format, version, and license reference. The installer streams to a temporary file, verifies SHA-256 before use, rejects archive traversal and links, and atomically publishes the extracted model directory.

- Silero VAD 6.2.1, MIT, ONNX artifact SHA-256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`. Inference uses ONNX Runtime CPU with one inter-op and one intra-op thread. Audio is polyphase-resampled to 16 kHz, processed in 512-sample frames with the required 64-sample context and recurrent state, and thresholded at probability 0.5.
- Google YAMNet 1, Apache-2.0 reference implementation/model family, TensorFlow SavedModel archive SHA-256 `b80da2a1a56926fb0767205051a200dd7b3beaf3ea1ea126c42a53943996e5e0`. The same 16 kHz waveform is passed to the real SavedModel. The worker averages patch scores and stores the top five of 521 AudioSet categories.

Missing or failed models produce `status: unavailable` with a bounded error. No heuristic or fixture is substituted.

## Durable job protocol and audio custody

The queue message contains only `{jobId, kind, version}`. The database row is authoritative. Event-analysis messages require the configured pipeline version (1), while new report generation requires the configured report version (2). A syntactically valid obsolete report job is claimed: an already-ready cached artifact is reconciled, while a non-ready job is failed with an explicit unsupported-version reason. It is never silently archived or rendered with a different template version. A worker reads one message, creates a fresh random UUID as that claim attempt's immutable SQL ownership identity, claims the row with a lease, and performs one job at a time. The configured `WORKER_ID` remains a human process label and is never reused as lease authority. A heartbeat renews both the unexpired row lease and pgmq visibility. Failed or refused renewal marks ownership lost; the worker abandons stale work and does not write a stale success or failure. Malformed messages are archived. Retryable infrastructure failures use 30, 60, then 120 second exponential backoff (capped at 15 minutes); the database enforces `max_attempts`, archives the prior message, and dead-letters the job as `failed` when attempts are exhausted.

For an event, deterministic analysis is committed with `ihear.persist_analysis` before any Astra reservation. Only after that commit does the worker delete the private Storage audio object and call idempotent `ihear.mark_audio_deleted`. The object path remains as an audit reference and `audio_deleted_at` proves deletion. A retry that finds a ready analysis but no deletion marker closes custody again before interpretation, so a crash between persistence, object deletion, and the marker cannot leak raw audio indefinitely.

Failed event objects are retained for diagnosis for seven days. The worker's hourly bounded cleanup selects at most 50 undeleted objects that either have a ready analysis or belong to a terminal event older than seven days, deletes the object idempotently, and stamps deletion through the trusted SQL function. No raw audio, model weight, API credential, or local database belongs in Git.

## Astra request and accounting

The request follows the official [GPT-6 Astra model contract](https://developers.openai.com/api/docs/models/gpt-6-astra) and [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create). It fixes `model=gpt-6-astra`, `reasoning.effort=low`, `max_output_tokens=1200`, `store=false`, an empty tools array, and strict JSON Schema output. `max_output_tokens` includes visible and reasoning tokens. There is no tool loop or audio input.

The exact compact UTF-8 request body is capped at 6,000 bytes. It contains the current event, explicitly selected and bounded deterministic/model fields, as many as 20 recent events with oldest history removed until the body fits, at most 16 audiogram points per series, a 500-character clinician note, and bounded aid fields. Device capability facts can only come from `config/device-capabilities.json`; tier differences and connected-phone routing stay `unknown`. Output tips are IDs from the same five-item catalog used by the client, and worker-owned text expansion prevents invented advice.

`config/astra-pricing.json` records the verified Standard price below 272k context: USD 10/million uncached input, USD 1/million cached input, USD 12.50/million cache-write input, and USD 50/million output including reasoning. The worker locally prepares the exact body, then the database atomically reserves USD 0.16 and enforces USD 20 global lifetime, USD 3 global day in `Europe/Prague`, and five live event interpretations per patient and patient-local day. Only an eligible reservation permits the worker to send that same body to `POST /v1/responses/input_tokens`; generation is fail-closed unless the authoritative count is at most 8,000 input tokens. Count failure or rejection releases the known no-generation reservation.

Settlement and interpretation persistence share one database transaction. Provider request identity and complete nonnegative usage fields are required; cached plus cache-write input cannot exceed total input. The actual cost rounds up to six decimal places from provider usage. A defensive overage path settles the full actual cost, freezes further reservations, and stores a terminal accounting failure. A definite pre-inference rejection releases the reservation. A timeout, network failure, 429, 5xx, incomplete response, invalid schema or usage, or orphaned existing reservation is conservative `held_ambiguity`: the reservation stays active and the worker never repeats that provider call automatically. Missing `OPENAI_API_KEY` is stored as `unavailable` before the ambiguity gate and without making or reserving a live call.

## Reports and scheduling

PDFs are generated from stored patient feedback, analyses, and persisted interpretations and must remain below the 4,000,000-byte delivery limit. A report is keyed by `(patient_id, input_revision, report_version)`. Its private object path is `{workspace}/{patient}/{report}/{claim-attempt}.pdf`, so stale cleanup can delete only the object written by that attempt. If report persistence succeeds but finishing the job loses its lease, the next attempt reconciles the already-ready report and never regenerates or repoints it. Page refresh and report GET only read state; they never call Astra. The PDF contains searchable text, follow-up and aid context, approved patient tips and interpretation limits, deterministic tables, page numbers, evidence labels, method limits, and a vector RMS chart on a fixed -100 to 0 dBFS axis with actual measured labels. Captured timestamps are rendered in the patient's validated clinic timezone, which is labelled in the report; unknown or unparseable timestamps remain unchanged. When no RMS measurement exists, the report states that explicitly and does not draw a fabricated zero-valued chart.

The worker checks for due follow-up reports once per minute at or after 08:00 in each patient's validated clinic timezone, beginning one local calendar day before the follow-up date. `ihear.ensure_report_job` and database uniqueness make scheduling idempotent. Each scheduling pass is bounded to 50 patients. Profile or analysis changes increment the input revision, so an old cached report cannot masquerade as current.

## Local commands

Build from the repository root:

```sh
docker build -f worker/Dockerfile -t ihear-worker:local .
```

Install and verify model artifacts inside the image:

```sh
docker run --rm -v ihear-models:/models ihear-worker:local python -m ihear_worker.model_download
```

Run deterministic tests without any credential or committed WAV:

```sh
docker build --target test -f worker/Dockerfile -t ihear-worker:test .
docker run --rm ihear-worker:test
```

Production startup requires `DATABASE_URL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY`. `ASTRA_MODEL`, `ASTRA_REASONING_EFFORT`, and `WORKER_CONCURRENCY`, when present, must equal `gpt-6-astra`, `low`, and `1`; startup rejects misleading overrides. `OPENAI_API_KEY` remains optional: without it, DSP, model inference, custody cleanup, and report generation remain operational while interpretation is visibly unavailable.
