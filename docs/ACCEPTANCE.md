# Local acceptance and verification

Evidence date: 2026-09-11. This document separates source checks, real local services, simulated media, physical phone activity and the future public gate. Final integration identity and disposition are in STATUS.md.

## Acceptance matrix

| Gate | Implemented behavior | Evidence |
| --- | --- | --- |
| A | Clinician creates synthetic name, audiogram, per-ear aid/tier and follow-up | Automated UI creation; validated Postgres record. |
| B | Opaque QR/manual code, confirmation, persisted same profile | Browser pairing + reload; two samples received through the separate phone-test profile. Native-camera scan/resume confirmation is a physical check. |
| C | Both large actions capture audio and create events | Browser fake-device PCM and two phone-test events; positive and negative kept separately. |
| D | Negative answers persist | Browser assertion on both answer fields; actual phone event includes answers. |
| E | Audio reaches private Storage and Docker worker | Worker downloaded WAV objects; real feature rows committed and raw objects deleted. |
| F | Native-rate DSP appears in correct clinician card | Known 1 kHz fixture asserts centroid, rate and duration; model statuses are separate estimates. |
| G | Astra available only with credential, bounded preflight/reservation and valid result | No API key: explicit unavailable state, real DSP preserved. Live provider/output-cap validation NOT RUN; no paid calls. |
| H | SQL full-text search, not filtering a loaded page | GIN-backed tsvector query and browser name/note/event-content search checks. |
| I | Searchable-text PDF with real charts | Actual private PDF generated/downloaded; text extraction and rendered pages inspected. |
| J | Event/job/API idempotency | Transactional tests; duplicate HTTP uploads and worker retry tests. |
| K | Offline pending PCM, reopen, foreground retry | IndexedDB and service-worker browser test. Physical iOS offline/eviction behavior remains a manual gate. |
| L | Visitor isolation, private DB and Storage | Separate browser capabilities; SQL anon/authenticated denial; live anon checks against an existing private PDF. |
| M | English responsive UI and keyboard use | Chromium WCAG automated checks on five routes; keyboard skip-link/manual-code journey; 390 px WebKit layout and desktop screenshots. This is not a complete assistive-technology audit. |
| N | No secrets or raw recordings in Git | Explicit path/secret scan before push; local runtime, model weights, fixtures, traces, screenshots and PDFs ignored. |

## Automated checks

- `pnpm typecheck`: passed.
- `pnpm test`: 4 PCM/ring-buffer tests + 9 backend tests passed.
- Rollback-only Postgres integration: passed. Covers workspace scoping, immutable event snapshots, duplicate admission, SQL FTS/filters, budget totals/daily/event boundaries, ambiguous reservations, overage settlement/freeze, queue claim/renewal/expiry, stale report rejection and browser-role denial. Disposable test data is rolled back; the live phone workspace is preserved.
- Live Supabase security test: parent plus five assertions passed against a real private report. An empty anonymous list is RLS filtering, not visibility of objects. No write probe succeeded.
- Supabase database lint and security/performance advisors: no reported issues in the local schema.
- Web production dependency audit: no reported vulnerabilities at the checked lockfile.
- Final worker image suite: 39 tests passed, including empty/silent PDF honesty, clinic timezone, report version routing and old-ready-report reconciliation. Final integrated browser results and runtime identities are in STATUS.md; CPU model measurements are in worker-evidence.md.

Browser automation uses Chrome's fake media device fed a mathematically generated PCM tone. The in-app QR scanner test uses a real encoded QR rendered into a generated YUV camera stream. Neither is represented as an actual phone microphone/camera test. No fixture result is inserted into application analysis tables as a replacement for DSP.

## Observed local services and data sizes

Local services are identified by project `iHear` (Supabase CLI) / `ihear` (Compose). The worker runs `python -m ihear_worker.main`, not the Docker test-stage `pytest` command. The managed web runs on port 3000; Supabase API/DB/Studio on 54321/54322/54323. The phone uses a configured private HTTPS Tailscale Serve origin; no public Funnel.

At the initial six-analysis measurement: Postgres database 12,930,195 bytes; `ihear` tables including indexes 966,656 bytes; mean stored analysis JSON 1,405 bytes; zero retained raw audio objects after successful extraction; one private PDF 4,715 bytes. The API ledger contained zero calls and USD 0 settled. These are a small local snapshot, not a capacity or cloud-performance claim.

## Independent review and repairs

A separate reviewer inspected backend authority, costs, data custody and worker transitions. Root adjudicated and assigned fixes. The review found and drove repairs for:

1. Reupload of a terminal failed duplicate after its original audio had been deleted.
2. Multipart buffering before the size cap.
3. Input-cost reservation without a proved provider token count and actual overage accounting.
4. Raw-audio deletion skipped when retrying after durable analysis.
5. Pre-call preparation failure leaking a reservation.
6. Stale lease terminal writes and missing long-job renewal.
7. Report inputs changing before publication of a requested revision.
8. Reuse of a process identity across claims and shared report-object paths.
9. Missing provider usage being mistaken for zero actual cost.
10. A missing explicit illustrative PDF label and a fallback numeric bar when no RMS measurement existed.
11. Report template version routing, preserved ready historical reports and advance scheduling in clinic-local time.

The current report template is version 3 (Clear Signal); version 2 evidence below is historical. It shows unavailable measurements honestly, displays captured times in the clinic timezone, and begins scheduled preparation at 08:00 one clinic-local calendar day before follow-up. A new result invalidating a requested report produces a visible outdated notice rather than silently offering a stale PDF.

The final review disposition and remaining limitations are recorded in STATUS.md. Static review, local enforcement and live provider evidence are distinct.

Repeated synthetic browser runs reached the configured ten-new-workspaces-per-address/hour limit and correctly received HTTP 429. Only the disposable local test admission counter was cleared for final reruns. The configured ceilings, event data, capabilities and provider ledger were preserved; no live database reset was used.

## Physical iPhone evidence and remaining checks

An owner-provided iPhone was available. The separately issued synthetic phone-test profile received one positive and one negative event, both 10 seconds at 48 kHz with 5 seconds pre / 5 seconds post. Both report the source label `iPhone Microphone` and actual echo cancellation disabled; other unsupported processing settings remain absent and routing is explicitly unknown. Both have real DSP, Silero and YAMNet output. The positive sample had a weak digital signal; its historical quality flag remains stored, but does not establish room quietness. This verifies reception and processing of those samples, not acoustic calibration, device routing or intelligibility.

Await/record owner observation for lock/background, microphone restart and reopening with pairing preserved. Native-camera scanning, standalone installation, offline reopening on physical Safari and storage eviction are not certified by desktop emulation. Browser state contains capabilities and stays private.

### Monday, September 14, 2026: hearing-aid checks

- Record iPhone/iOS/browser mode, actual connected BTE devices and Bluetooth state without inferring tier capabilities.
- Connect/disconnect hearing aids and record available track settings/source label. Compare controlled samples; mark routing unknown unless independently established. Do not claim phone PCM is sound at the aid microphones/eardrum.
- Test initial microphone permission, denial/recovery, phone lock, background/foreground, interrupted stream and explicit restart. Confirm no background-recording promise.
- Inspect native sample rate, exact frame count, pre/post lengths, integrity, silence/clipping flags and foreground prebuffer after each transition.
- Capture both actions in controlled quiet and sound conditions, verify answers and correct profile, repeat offline/foreground upload, then confirm raw-object cleanup and PDF.
- Test both native-camera QR and explicit in-PWA scanner with manual-code fallback.

## Public release gate: NOT RUN

Requires approved Vercel deployment without a login wall, hosted Supabase and Render worker, production QR origin, fresh physical-device capture/reporting, and queue processing while the MacBook is off. No localhost, LAN or development relay may remain in that runtime. Local acceptance cannot pass this separate gate.
