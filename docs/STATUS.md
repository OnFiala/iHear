# Implementation status

Updated 2026-09-11. **Local implementation and automated end-to-end verification: PASS. Physical iOS coverage: PARTIAL. Public application release: NOT RUN.** No public application or paid cloud resource was provisioned.

## Source and authority

- Workspace: `/Users/ondrej/iHear`, MacBook development host, user/home `ondrej` / `/Users/ondrej`.
- Verified GitHub account: `OnFiala`, ID `202789334`. Public proprietary repository: https://github.com/OnFiala/iHear. Licensing is in LICENSE; this is not an open-source release.
- `implementation/local-milestone` is the coherent implementation branch, rooted in initial documentation commit `1279a48`. Final integration fast-forwards `main` to the same reviewed handoff commit and publishes both refs without rewriting history. Use `git rev-parse HEAD` / `git log -1` for the precise checkout revision.
- Significant implementation commits include `235b33a` (backend), `25a997b` (attempt fencing), `5f18115` (worker), `8d06a17` (report v2) and `60cbfb0` (local/cloud configuration). The final evidence commit follows these.
- Public source publication and local operation were authorized. Hosted Vercel/Supabase/Render resources, paid provisioning and public application deployment still require owner approval.

## Working behavior

The English landing page, clinician directory/profile editor, opaque QR/manual/scanner pairing, paired patient home, both audio actions, negative questionnaire, pending uploads, event details and report workflow are implemented. The glass design uses original generated art, local fonts, accessible controls and reduced-motion handling.

Native-rate PCM moves through private Supabase Storage to a single Docker worker. Real NumPy/SciPy calculations and pinned Silero/YAMNet estimates appear in the correct clinician card. Raw audio is deleted after durable feature extraction. Database full-text search includes name, notes and event content; filters run in SQL. Visitor capabilities isolate workspaces and paired patients.

Jobs have bounded retries, renewable leases and a fresh UUID for every claim. Old attempts cannot overwrite newer state or delete another attempt's PDF. DSP survives interpretation failure. Duplicate uploads reuse one event/analysis and never trigger another paid call. Report template v2 preserves historical caches, shows no invented empty-chart measurement, labels illustrative use, uses clinic-local timestamps, and schedules at 08:00 one clinic-local calendar day before follow-up. Changed inputs show an outdated-report notice.

## Current local runtime

```bash
cd /Users/ondrej/iHear
pnpm install --frozen-lockfile
python3 scripts/local.py start --production
python3 scripts/local.py status
```

- Web: http://localhost:3000; clinician: http://localhost:3000/clinic; patient entry: http://localhost:3000/app.
- Supabase API/DB/Studio: `127.0.0.1:54321` / `54322` / `54323`.
- Phone origin: the private trusted HTTPS `APP_PUBLIC_ORIGIN` in ignored `.env.local`. Tailscale Serve uses dedicated port 8446; an existing unrelated port 8445 was preserved. No public Funnel. The MacBook and tailnet connection are required for this local runtime.
- Stop: `python3 scripts/local.py stop`. Data and model cache are preserved. The final documented stop/start cycle passed with the phone-test workspace intact. An explicit reset command and its limits are documented in README; never reset an active phone session.
- Docker worker enforces 1 CPU, 2 GiB and concurrency 1. Its command is `python -m ihear_worker.main`, not `pytest`. Production image: `sha256:0435cb662b338d85118dc4afecd6b63dd2d04e1b546d3e0755e82a1dc764cf9d`; 15 source/config checksums match the running container.
- Applied migration head: `20260911182710_default_report_template_version_2.sql`. Pipeline version 1; report version 2. No database reset occurred after physical phone data arrived.

The launcher uses an isolated `.local/docker` client configuration for public pulls after the system credential helper stalled; global Docker configuration was preserved. Local keys and logs stay ignored, with credential-bearing files mode 0600. The web PID is managed separately and unrelated processes are not killed.

## Verification evidence

| Check | Result |
| --- | --- |
| Production build and TypeScript | PASS |
| PCM/ring-buffer tests | 4/4 PASS |
| Backend validation, bounded body, fingerprint and capability tests | 9/9 PASS |
| Rollback-only real Postgres contract integration | 1/1 PASS, including budget boundaries, tenant isolation, lease expiry/reclaim and report version coexistence |
| Live Supabase anonymous DB/Storage denial | Parent + five assertions PASS; an existing private PDF was inaccessible; no probe write succeeded |
| Worker tests in final test image | 39/39 PASS |
| Final production browser suite | 10/10 PASS in 59.6 seconds |
| Clinic-timezone SQL scheduling boundaries | Six fixed-time Prague/New York cases PASS, including 07:59/08:00 and tomorrow/later dates |
| PDF | Final physical-phone report: two searchable pages, 5,015 bytes, 1,907 text characters; both pages visually inspected. Browser report: three pages, 6,449 bytes, 2,304 characters |
| Accessibility/layout | Automated WCAG checks on five public routes and paired microphone-ready home; keyboard journey; 390 px WebKit layout; desktop/mobile screenshots inspected |
| Dependencies/configuration | Frozen pnpm install PASS; web production vulnerability audit reported zero; YAML/JSON and database lint PASS; 53 worker package licenses inventoried |
| Public source hygiene | Staged/tracked path and credential scan PASS; runtime data, audio, weights, traces, capabilities and PDFs excluded |

Chrome tests used generated fake-device PCM and a real encoded QR in a synthetic camera stream. They prove application/media plumbing and DSP against known input, not physical Safari behavior. Independent source/contract review found and drove repairs; all supplied security/cost/custody/report findings are closed. Root separately verified runtime behavior and integration. See ACCEPTANCE.md and worker-evidence.md for scope and limits.

Final small-data snapshot: Postgres 13,372,563 bytes; `ihear` tables/indexes 1,261,568 bytes; 24 ready analyses with mean JSON size 1,396 bytes; four private PDFs totaling 22,566 bytes; zero raw audio objects. There were 28 succeeded jobs and one preserved failed superseded-report job from the deliberate stale-revision exercise, with no outstanding job. This is not a public-capacity benchmark.

## Astra, phone and remaining limits

- `OPENAI_API_KEY` is absent. App Astra ledger: zero calls, USD 0 settled. Current global limits remain USD 20 total / USD 3 daily, not frozen; five live events/profile/day, low reasoning and concurrency 1 are enforced. Real DSP and reports work with visible unavailable interpretation.
- The exact request, input-token preflight, reservation/settlement, ambiguity and overage-freeze paths are tested with controlled responses. Live credentialed generation, provider latency and useful output within 1,200 output tokens are NOT RUN. Do not enable cloud Astra before that bounded validation.
- The physical phone-test profile received one positive and one negative 10-second, 48 kHz sample, each with 5 seconds pre / 5 seconds post. Source metadata says `iPhone Microphone`; actual echo cancellation is disabled, other unsupported settings are absent, and routing remains unknown. Both events are ready with real model/DSP output. The quiet positive event's original paused interpretation is preserved as history; subsequent no-key events explicitly say unavailable.
- Native-camera scan, lock/background/resume, standalone installation and physical Safari offline/storage-eviction behavior still need owner observation. Desktop WebKit is not iOS certification. Hearing-aid tests for Monday 2026-09-14 are documented in ACCEPTANCE.md; no claim is made about connected-aid routing or calibrated acoustics.
- A CPU model probe under a real 1 CPU / 2 GiB limit measured 1.776 seconds cold model load/inference, 0.105 seconds warm inference and 685.9 MiB peak RSS on local aarch64. Repeat on Render before choosing a paid size; these are model-probe measurements, not end-to-end service latency guarantees.
- Worker vulnerability-database audit was not run. Provider blueprint acceptance, hosted permissions, load/capacity and MacBook-off behavior are NOT RUN. Raw failure cleanup requires the worker to run; metadata/report/queue retention needs a capacity decision before broad public use. Owner-cookie loss has no recovery flow in this demo.

## Next authorized work and rollback

There is no remaining local implementation task in this milestone. Optional owner inputs are an app Astra credential for bounded live validation and physical iOS test observations. Future cloud allocation is one Vercel application, one Supabase demo project plus isolated preview data, and one Render Docker worker. Exact variables, migration/seed order, QR re-pairing, model installation, rollback and the separate public-release gate are in CLOUD_MIGRATION.md.

Local rollback: stop only iHear through the launcher, preserve Supabase data and the API ledger, check out a compatible prior Git revision, align pipeline/report configuration, rebuild, and verify. Keep schema changes additive; do not undo migrations by resetting live local data. The application is deliberately left running for the owner. Temporary browser verification sessions are closed; no delegated agent remains active.
