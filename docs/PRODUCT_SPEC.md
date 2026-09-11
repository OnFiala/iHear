# Product specification

iHear is an illustrative, English-first patient PWA and clinician website for exploring everyday listening moments. Clinical interpretation remains with the clinician. This is not a diagnostic service, medical device, fitting prescription or claimed validated clinical tool.

## Journeys
- `/`: public landing and immutable curated synthetic showcase.
- `/clinic`: a visitor's isolated demo directory; full-text search across profiles, notes and event descriptions; date, difficulty and processing filters.
- `/clinic/patients/new`: synthetic name, left/right audiogram, fitted ears and per-ear ALLURE BTE R D tier, follow-up, clinic timezone, optional note.
- `/clinic/patients/[id]`: editable setup, audiogram chart, expiring/revocable QR and manual pairing code, events, independent analysis stages and PDF report.
- `/pair/[token]`: identify the synthetic profile, acknowledge illustrative use and confirm pairing.
- `/app/pair`: explicitly activated camera scanner or manual code entry. Native phone camera links also work.
- `/app`: paired profile, appointment, microphone state, two actions and recent moments.
- `/app/events/[id]`: current persisted event state and a bounded approved patient tip if available.

## Capture and feedback
Both “I understand” and “I don’t understand” save real phone-microphone-intended audio. No recording exists before permission, user activation and an active foreground session. Up to five seconds of PCM prebuffer plus post-press capture makes approximately ten seconds; shorter prebuffer extends postcapture. Backgrounding, locking, track interruption or stopping monitoring ends the session visibly.

Negative questions use exactly the approved difficulty and surroundings choices; positive moments need no questionnaire. PCM and capture metadata persist in IndexedDB before upload. Negative drafts survive an unfinished questionnaire. Foreground/online retry sends the same event ID. “Received” appears only after the server acknowledgement. Pending, uploading, queued, analysing, ready and failure states remain distinct.

## Interpretation boundaries
Patient reports, native-rate DSP, Silero speech-activity estimate, YAMNet category estimates and optional Astra interpretation are separate. No transcripts, voice identity/separation claims, uncalibrated dB SPL, audiogram dB HL versus microphone dBFS comparisons, fabricated SNR or intelligibility scores, gain prescriptions or tier guarantees. Device facts are source/version/status tagged. Unknowns remain unknown.

## Persistence, privacy and costs
Server-issued scoped capabilities replace a visible login; they are not clinical authentication. Private audio buckets and tenant-qualified queries prevent visitors from browsing each other's workspace. Each event stores a profile snapshot. Raw uploaded audio is deleted after successful feature extraction and bounded cleanup handles failures. Runtime data and secrets never enter Git. This describes implementation policy, not a GDPR compliance claim.

Astra is limited to low reasoning, bounded structured inputs and output tokens, and no tools or loops. Global budget caps are USD 20 lifetime and USD 3/day, including development. Per-profile ceiling is five live analysed events/day. Missing credentials and paused budgets preserve real acoustic results. Infrastructure spending is separate from API caps.

## Release boundary
This milestone is local. A later Vercel + hosted Supabase + Render release must pass a fresh-device HTTPS capture/report test and continue processing with the MacBook off. No local test is evidence of that gate.
