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
- Development implementation branch: implementation/local-milestone, based on an initial main documentation commit. main remains the baseline until reviewed integration.

## C. Open questions and verified limitations
- Actual iPhone/Safari testing requires an available physical phone and trusted reachable HTTPS origin.
- Hearing-aid physical checks start Monday 2026-09-14. Until then use the phone microphone and controlled recordings.
- No OPENAI_API_KEY was present in the task environment at preflight. Real DSP must work without interpretation.
- Docker Desktop is installed but its daemon was initially stopped; startup verification in progress.
- Tier-specific device differences remain unknown unless supported by BTE-specific primary sources.
- Public release gate is not passed by local verification.
