# Product specification

iHear is an illustrative, English-first patient PWA and clinician website for exploring everyday listening moments. Clinical interpretation remains with the clinician. This is not a diagnostic service, medical device, fitting prescription or claimed validated clinical tool.

## Journeys
- `/`: introductory landing on the existing owner-only deployment.
- `/clinic`: a visitor's isolated demo directory; full-text search across profiles, notes and event descriptions; date, difficulty and processing filters.
- `/clinic/patients/new`: synthetic name, left/right audiogram, fitted ears and per-ear ALLURE BTE R D tier, follow-up, clinic timezone, optional note.
- `/clinic/patients/[id]`: editable setup, audiogram chart, expiring/revocable QR and manual pairing code, events, independent analysis stages and PDF report.
- `/pair/[token]`: identify the synthetic profile, acknowledge illustrative use and confirm pairing.
- `/app/pair`: explicitly activated camera scanner or manual code entry. Native phone camera links also work.
- `/app`: an unpaired visitor can explicitly start a patient demo without a QR,
  or use a clinician's pairing code. The demo creates a labelled fictional
  profile through the normal owner API and opens the existing acknowledgement
  screen; it does not prefill listening events or bypass patient capabilities.
  Paired visitors open their existing profile, appointment, microphone state,
  two actions and recent moments directly. The originating demo owner can open
  the same profile in the clinician view.
- `/app/events/[id]`: current persisted event state and a bounded approved patient tip if available.

## Capture and feedback
Both “I understand” and “I don’t understand” save real phone-microphone-intended audio. No recording exists before permission, user activation and an active foreground session. Up to five seconds of PCM prebuffer plus post-press capture makes approximately ten seconds; shorter prebuffer extends postcapture. Backgrounding, locking, track interruption or stopping monitoring ends the session visibly.

Negative questions use exactly the approved difficulty and surroundings choices; positive moments need no questionnaire. PCM and capture metadata persist in IndexedDB before upload. Negative drafts survive an unfinished questionnaire. Foreground/online retry sends the same event ID. “Received” appears only after the server acknowledgement. Pending, uploading, queued, analysing, ready and failure states remain distinct.

## Interpretation boundaries
Patient reports, native-rate DSP, Silero speech-activity estimate, YAMNet category estimates and optional Astra interpretation are separate. No transcripts, voice identity/separation claims, uncalibrated dB SPL, audiogram dB HL versus microphone dBFS comparisons, fabricated SNR or intelligibility scores, gain prescriptions or tier guarantees. Device facts are source/version/status tagged. Unknowns remain unknown.

## Persistence, privacy and costs

Patient-demo setup persists its creation attempt and returned profile ID in
tab session storage, scoped to the visitor workspace. A lost creation response
remains visibly uncertain across reload; the user must check the clinician
directory rather than silently create another profile. A known created profile
can resume pairing after owner access and its demo label are checked again.
The label is presentation metadata, not authorization. This is not a global
exactly-once creation guarantee across tabs or cleared browser storage.
Server-issued scoped capabilities replace a visible login; they are not clinical authentication. Private audio buckets and tenant-qualified queries prevent visitors from browsing each other's workspace. Each event stores a profile snapshot. Raw uploaded audio is deleted after successful feature extraction and bounded cleanup handles failures. Runtime data and secrets never enter Git. This describes implementation policy, not a GDPR compliance claim.

Astra is limited to low reasoning, bounded structured inputs and output tokens, and no tools or loops. Global budget caps are USD 20 lifetime and USD 3/day, including development. Per-profile ceiling is five live analysed events/day. Missing credentials and paused budgets preserve real acoustic results. Infrastructure spending is separate from API caps.

## Release boundary
The current application runs on the dedicated private Linux sandbox and owner-only
domain. STATUS.md records the deployed revision and evidence. A public release
must satisfy SECURITY.md, including fresh-device HTTPS capture/report behavior,
isolated data, capacity and recovery. Hosted Vercel/Supabase/Render remains an
alternative proposal rather than a requirement. CHALLENGE.md tracks the separate
GPT-6 Astra Challenge target and remaining submission evidence.
