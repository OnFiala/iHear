# Implementation status

Updated 2026-09-12. **Clear Signal implementation and local verification: PASS.
Private Linux activation: PASS. Owner-only custom domain activation: PASS.
Browser coverage: PASS with one historical QR-fixture retry. Anonymous public
release: NOT RUN.** The selected direction retains the original 3D glass artwork.
The owner can use `https://ihear.ofops.co` through Cloudflare Access. The dedicated
tunnel and isolated origin are active and enabled at boot. Anonymous application
access remains disabled. No paid feature was enabled; interpretation API use
remains intentionally disabled.

The current candidate includes the patient Record/History split, compact clinician
Moments/Profile review, accessible pairing/settings, and PDF template 3. Version 1/2
PDFs remain historical. The visual review also found and fixed a pre-existing date
serialization defect: PostgreSQL DATE must retain its local calendar day instead
of shifting through UTC. Prague, New York and UTC regression cases pass.

Local checks: 19 audio/backend tests, five real Postgres suites, 36 runtime/source
scanner tests and 43 worker tests passed (one model-artifact probe skipped in the
network-isolated unit image). Production build/typecheck passed. The eight linked
browser scenarios passed in 51.9 seconds; the two accessibility/WebKit scenarios
passed separately on the same visual build. Initial runs exposed two stale test
selectors after the UI reshaping; these were corrected without weakening behavior
assertions. The final date/pagination refinements also passed narrow verification: two browser
scenarios, timezone parser regression cases and a three-moment pagination fixture.

## Owner-only custom domain — active, 2026-09-12

The owner approved `ihear.ofops.co` with access restricted to the owner and a
maximum USD 5 cost. Zero Trust Free is active. The chosen Access Free, Tunnel and
Free DNS path costs USD 0 without enabling paid add-ons or usage-billed products.
No native Cloudflare hard dollar spending cap was verified or configured; budget
alerts do not stop billing. This does not cap unrelated existing account services.

The previous wildcard DNS error 1000 is resolved by an explicit proxied CNAME
for this hostname. Its dedicated tunnel routes only to loopback port 8081 with
Protect with Access enabled, the exact application audience/team and a fixed
Host header. A persisted Access application protects all paths with one verified
owner email allow rule and no bypass policy. No wildcard, mail or sibling-tunnel
setting was changed.

After the initial automatic-review hold, the owner explicitly confirmed transfer
of this tunnel credential. Operations source
`3387c92406c100f22e25f67a9357c4de1d06a18e` was installed separately under
`/opt/ihear-domain`; the application checkout and artifact remain frozen at the
revision below. The credential is root-owned 0400 under a root-owned 0700 directory.
Its temporary MacBook source copy was removed. The existing BUILD_ID file mode
was tightened from 0664 to 0644 without changing its contents. No database
migration, worker change or private web restart occurred.

Acceptance evidence:

- Source preparation passed 60 focused tests; the independent source review passed
  its 24-test subset. Installed systemd validation, nginx validation and local
  preflight passed. Source checks are distinct from the live checks below.
- Independent runtime review verified installed hashes, separate locked web UID,
  no supplementary groups, read-only source, separate cache, process limits,
  loopback-only listeners and protected credential metadata. Root additionally
  verified the connector's actual `/config`: exactly one application route,
  required Access with the exact audience/team and a catch-all HTTP 404.
- The owner browser loaded the actual landing page and original artwork, created
  one labelled synthetic profile, generated and redeemed pairing on this exact
  domain, opened the patient interface, and generated/downloaded a real 5,198-byte
  PDF. The empty profile's report contains no invented observations. This run did
  not record audio or use the microphone.
- Eleven anonymous, invalid-cookie/JWT and CORS-preflight checks rejected access
  across application, API and static paths; they passed again after connector
  recovery. A Python default-user-agent error 1010 was excluded from Access proof.
  A second authenticated non-owner identity and a direct connector-level
  invalid-JWT request were not tested.
- Disable-only rollback stopped just the new connector: the owner received 1033,
  while the original private origin remained healthy. Restarting only that
  connector restored the owner profile and landing page. Both new units are
  active and boot-enabled. A host reboot or power-loss test was not repeated.
- All 37 pre-existing patient/event/analysis/report rows retained their hashes.
  The synthetic profile and report add two rows: seven profiles, fourteen events
  and analyses, four reports. Private configurations, web PID and worker image
  remained unchanged.

The initial verification pairing was revoked during cleanup. After the owner
reported pairing trouble, their actual in-app browser showed the patient scanner
page with camera access unavailable. A fresh QR was visibly generated in the
clinician profile; opening its link and confirming the synthetic profile paired
that in-app browser successfully. This replacement pairing remains active for
owner testing. Microphone permission was not granted by the operator. The patient
page consumes a clinician-issued QR/code; it does not generate one. Access still
requires the approved owner identity, including on a phone or other browser.

The domain has its own host-only workspace cookie. Historical workspaces remain
on the original private origin; cookies/data were not remapped. Physical iOS
validation and anonymous public release remain separate milestones. See the
[domain operations runbook](../ops/domain/README.md).

## Current Clear Signal deployment

The private Linux sandbox is running reviewed commit
`f3ab5a6fc5813f845ca44eef28f5e621eab907e3`. It has a clean detached checkout,
a matching protected artifact manifest, Next build `leIR2dbOQwxwEI6VTkMTE`, and
matching prepared/running worker image and platform manifest. Web and worker both
use report template 3; pipeline version 1 is unchanged. The original 3D artwork
served over the private origin matches the source bytes exactly.

Before activation, the existing four profiles, ten events/analyses and two ready
reports were backed up. Web admission stopped; unfinished job/report counts were
zero both before and after stopping the old worker. The reviewed candidate and
forward rollback commit `f930658` were present on Linux before the switch.
Pre-existing patient/event/analysis/report hashes matched after activation.
The additive v3 migration changed defaults only. No reset, unit replacement,
public ingress, API activation or operating-system change was performed.

The deployed browser suite passed 9/10 on its first run; the camera-fixture QR
case timed out while the scanner remained active. An isolated profile-plus-scanner
rerun passed 2/2 in 4.6 seconds on the same commit, without an application change.
All ten scenarios therefore have passing deployed evidence, but this is not a
claim of a single uninterrupted 10/10 run or a diagnosed fix for camera-test
intermittency. Native-camera/physical iOS validation remains separate.

The current-version PDF has three searchable pages and 7,929 bytes. All pages
were inspected; the follow-up date, unavailable interpretation and measured
48 kHz sample information are correct, with no footer-only page or orphaned
moment heading. The final sandbox snapshot has six synthetic profiles, fourteen
ready analyses with both real models ready, three ready PDFs (one v3), zero
unfinished jobs, zero raw-audio objects and zero API usage. Additional rows belong
to these verification workflows. Five app/proxy/monitor units are active; the
web account, read-only source, 768 MiB memory, 150% CPU and 128-task limits remain.

The final source handoff adds documentation only after this runtime commit.
Application, worker, migrations, dependencies and service sources are identical;
the valid runtime manifest is retained rather than changing it without a build.
The prepared rollback is unactivated: its defaults were transactionally tested,
but rollback activation and a physical power-loss test were not performed.

## Previous private sandbox milestone (historical evidence)

The security update is source-reviewed with 26 runtime tests, 10 publication
scanner tests, 18 audio/backend tests, 41 worker unit tests, five real PostgreSQL
integration suites and a separate real scheduler saturation/recovery test passing.
It adds private-origin redaction, observed-IP publication checks, live ingress drift
reporting, owner-only application ingress, a confined web account, request limits
and finite database growth. Live confinement, owner-only ingress, 403/413/429
responses, private client-bundle checks and source/artifact parity passed.
The final bounded burst produced 104 HTTP 200 and 56 HTTP 429 responses, with
no 5xx, from 160 requests at concurrency 16. This is an overload-control probe,
not a public-capacity or volumetric DDoS benchmark.
The private/public boundary and proposed hostname are in [SECURITY.md](SECURITY.md).

The pre-redesign deployed security revision was `57d2c1c1f58e32ebdd4f3858e4287ab10385d5f1`.
The final `main` handoff differs only in documentation; its application, worker,
migrations, service configuration and operating scripts match that runtime source.
The runtime keeps its valid original build manifest and was not restarted again
for this documentation-only handoff.

Browser evidence is deliberately cumulative: the worker repair revision passed
9/10 in one run; the isolated profile/QR-scanner rerun passed 2/2. After the proxy
burst adjustment, two accessibility/layout tests passed, then `/api/session`
returned the expected JSON 429 because repeated test contexts had used all ten
new-workspace admissions in that UTC hour. One setup test failed and seven
dependent tests did not run. The live quota was neither lowered nor reset.
See SANDBOX.md for the preserved failures and final verification boundaries.

The dedicated Ubuntu ThinkPad runs independently of the MacBook. OpenClaw is
disabled/stopped with its data retained. The initial accepted runtime checkout was
`07c57099c1b28ded53f938753e339ee5adc8aaa9`; its protected manifest matches the
then-running worker image and Next build. The following security update changes
the runtime; its deployment and acceptance evidence are recorded separately.
The canonical operating entrypoint is [SANDBOX.md](SANDBOX.md). The final security
snapshot has ten ready real-model analyses, two ready PDFs, no unfinished jobs,
no raw audio objects and no API usage. Existing pre-update data was preserved;
the additional rows belong to synthetic verification workflows.

Initial Linux evidence: 11 runtime-contract tests, 16 monitor tests, 39 isolated x86_64
worker tests and 10 browser end-to-end tests passed. Four synthetic events have
real ready Silero/YAMNet results; one PDF is ready; no raw audio object, unfinished
job or API usage remains. The approved reboot at 13:48:18 UTC returned all services
automatically, with unchanged configuration and retained data/logs, while the lid
stayed closed. Dashboard identity, protected log modes, rotation/ingestion and nine
live route classifications passed. This is a private single-worker sandbox test,
not a public concurrency benchmark or proof of recovery after exhausted battery.

The original milestone evidence below describes the MacBook on 2026-09-11 and must
not be read as additional current Linux or physical-phone proof.

## Source and authority

- Workspace: `/Users/ondrej/iHear`, MacBook development host, user/home `ondrej` / `/Users/ondrej`.
- Verified GitHub account: `OnFiala`, ID `202789334`. Public proprietary repository: https://github.com/OnFiala/iHear. Licensing is in LICENSE; this is not an open-source release.
- `main` is the integrated source. The initial application milestone is preserved on `implementation/local-milestone`; the dedicated sandbox/security work is on `infrastructure/linux-sandbox` and integrated by fast-forward without rewriting history. Use `git rev-parse HEAD` / `git log -1` for the precise checkout revision. The deployed runtime has a separate protected artifact manifest; a GitHub ref alone is not runtime evidence.
- Significant implementation commits include `235b33a` (backend), `25a997b` (attempt fencing), `5f18115` (worker), `8d06a17` (report v2) and `60cbfb0` (local/cloud configuration). The final evidence commit follows these.
- Public source publication and local operation were authorized. Hosted Vercel/Supabase/Render resources, paid provisioning and public application deployment still require owner approval.

## Working behavior

The English landing page, clinician directory/profile editor, opaque QR/manual/scanner pairing, paired patient home, both audio actions, negative questionnaire, pending uploads, event details and report workflow are implemented. Clear Signal uses original glass artwork, white/cobalt/yellow surfaces, local fonts, accessible controls and reduced-motion handling.

Native-rate PCM moves through private Supabase Storage to a single Docker worker. Real NumPy/SciPy calculations and pinned Silero/YAMNet estimates appear in the correct clinician card. Raw audio is deleted after durable feature extraction. Database full-text search includes name, notes and event content; filters run in SQL. Visitor capabilities isolate workspaces and paired patients.

Jobs have bounded retries, renewable leases and a fresh UUID for every claim. Old attempts cannot overwrite newer state or delete another attempt's PDF. DSP survives interpretation failure. Duplicate uploads reuse one event/analysis and never trigger another paid call. Report template v3 preserves historical caches, shows no invented empty-chart measurement, labels illustrative use, uses clinic-local timestamps, and schedules at 08:00 one clinic-local calendar day before follow-up. Changed inputs show an outdated-report notice.

## MacBook development runtime (2026-09-11 evidence)

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

The private Linux sandbox is delivered; its current operations and rollback are
in SANDBOX.md. Interpretation API use remains off under the latest owner decision.
Physical iOS/hearing-aid observations and a real AC-loss/firmware recovery test are
still separate evidence. Future cloud allocation, if authorized later, is one
Vercel application, one Supabase demo project plus isolated preview data, and one
Render Docker worker. CLOUD_MIGRATION.md preserves that future plan and its public
release gate; no cloud resource is required for the current private sandbox.

Local rollback: stop only iHear through the launcher, preserve Supabase data and the API ledger, check out a compatible prior Git revision, align pipeline/report configuration, rebuild, and verify. Keep schema changes additive; do not undo migrations by resetting live local data. The application is deliberately left running for the owner. Temporary browser verification sessions are closed; no delegated agent remains active.
