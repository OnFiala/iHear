# Decisions

## A. Owner-approved decisions
Approved in the implementation brief on 2026-09-11.
- Product name iHear; English-first application, documentation and reports.
- Patient PWA and clinician web interface in one application. Public demo without a login screen.
- Local implementation first; future public runtime independent of the MacBook.
- Vercel web, Supabase hosted database/storage/jobs, separate CPU worker (Render target).
- Astra API, low reasoning only, explicit cost ceilings. No speech transcription.
- Clinician-created profiles with QR onboarding. Patient actions: “I understand” and “I don’t understand”.
- Soft liquid-glass style, gentle accessible animation.
- Illustrative Widex ALLURE BTE R D 110/220/330/440 scope. Clinical interpretation remains with the clinician.
- Public proprietary GitHub repository OnFiala/iHear; no public application deployment in this milestone.
- USD 20 total / USD 3 daily Astra ceilings; 5 live analysed events per profile/day; worker concurrency 1; 10-second audio target.

## B. Engineering choices made by Codex
- One Next.js App Router application, TypeScript, CSS; Python CPU worker.
- Local Supabase Postgres, private Storage and pgmq; no SQLite fallback.
- Opaque random, hashed server-side capabilities in HttpOnly cookies: workspace owner and patient-scoped pairing. No browser service key.
- Separate durable DSP, interpretation and report records. Transactional job idempotency by event and pipeline version.
- JSON profile snapshots stored with events; original audiograms are clinician-entered synthetic examples.
- Development implementation branch: `implementation/local-milestone`, based on the initial main documentation commit `1279a48`. Reviewed local integration fast-forwards `main`; both refs publish the same milestone without rewriting remote history.
- A private Tailscale Serve HTTPS origin supports cross-device local testing. It is neither a public deployment nor a future runtime dependency.
- Jobs use renewable Postgres leases and pgmq visibility, bounded retries, independent DSP persistence and idempotent audio deletion. Stale report revisions cannot publish as current.
- Each claim uses a fresh immutable UUID as lease authority. PDF paths include that attempt UUID; a late process cannot delete or publish another attempt's file. Already-ready reports reconcile completion without regeneration.
- Exact provider input-token preflight, bounded structured output, transactional global reservation, conservative ambiguity holds and a freeze on reported overage guard Astra calls. Refreshes and report downloads make no generation calls.
- All visitor workspaces are isolated by server-issued capabilities; the landing showcase is immutable synthetic content. There is no owner-cookie recovery feature in this milestone.
- Report generation uses stored acoustic features and interpretations; it incurs no additional Astra call. A scheduling sweep prepares due follow-up reports in the profile timezone and reuses an unchanged input revision.

## C. Open questions and verified limitations
- Two physical phone samples were received and processed through a trusted private HTTPS origin. Native-camera scanning, lock/resume, standalone mode and physical Safari offline/eviction behavior still need owner observations; desktop browser automation does not certify them.
- Hearing-aid physical checks start Monday 2026-09-14. Until then use the phone microphone and controlled recordings.
- No OPENAI_API_KEY was present in the task environment at preflight. Real DSP must work without interpretation.
- Docker Desktop and the local Supabase stack are running; source and runtime checks are recorded in ACCEPTANCE.md.
- No-key operation and mocked provider/budget failures are tested. Live token preflight, output usefulness under the 1,200-token cap and paid-call latency remain untested without a credential.
- A small local 1 CPU / 2 GB worker benchmark does not establish Render sizing or public concurrency capacity.
- Raw audio is deleted after successful feature extraction. Failed/abandoned audio has a seven-day cleanup horizon while the worker runs; retained metadata, report revisions and queue archives need a capacity-based retention decision before broad public use.
- Tier-specific device differences remain unknown unless supported by BTE-specific primary sources.
- Public release gate is not passed by local verification.
