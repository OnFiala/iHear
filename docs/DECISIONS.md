# Decisions

## A. Owner-approved decisions
Approved in the implementation brief on 2026-09-11.

2026-09-12 updates supersede the corresponding initial choices: operate without
the interpretation API for now; use the existing Ubuntu ThinkPad as a dedicated
private iHear sandbox; pause OpenClaw while preserving its data; prevent lid and
idle sleep; provide a private host/application operations dashboard. The MacBook
remains the authoring source. Store exact private machine identity in a project
binding, with a project skill and `docs/SANDBOX.md` as the operating entrypoint.
The infrastructure update initially preserved the UI. The owner subsequently
selected direction 2 (Clear Signal) with the original 3D glass artwork and
authorized implementation and deployment on the existing private sandbox. This
changes the visual layer and PDF template; it does not authorize public ingress.

The owner additionally required the sandbox decision to be integrated into the
main project and runtime, with direct connection details excluded from public
artifacts and explicit protection against abuse before Product Hunt exposure.
`docs/SECURITY.md` owns this boundary. The current sandbox stays private; public
source publication does not authorize public application activation. A protected
public domain through an outbound tunnel is a proposal pending public isolation,
edge controls, capacity and deployment approval. Read-only account inspection
confirmed both owner domains and the existing Cloudflare zone for `ofops.co`;
`ihear.ofops.co` was initially proposed. The owner then explicitly requested this
domain, rejected access for everyone, and approved Zero Trust Free with a maximum
USD 5 cost. The owner subsequently explicitly confirmed the scoped tunnel
credential transfer after the automatic-review hold. Owner-only Access, the
dedicated tunnel/DNS route and isolated origin are now active; both new units are
boot-enabled after live owner flow and disable-only rollback verification. This
supersedes the initial no-login public-demo intent for the current deployment. It does not approve anonymous
access, paid add-ons, or changes to sibling services.

- Product name iHear; English-first application, documentation and reports.
- Patient PWA and clinician web interface in one application. Public demo without a login screen.
- Local implementation first; future public runtime independent of the MacBook.
- Vercel web, Supabase hosted database/storage/jobs, separate CPU worker (Render target).
- Astra API, low reasoning only, explicit cost ceilings. No speech transcription.
- Clinician-created profiles with QR onboarding. Patient actions: “I understand” and “I don’t understand”.
- Clear Signal white/cobalt/yellow interface with original glass landing artwork; supersedes the initial soft liquid-glass UI.
- Illustrative Widex ALLURE BTE R D 110/220/330/440 scope. Clinical interpretation remains with the clinician.
- Public proprietary GitHub repository OnFiala/iHear; no public application deployment in this milestone.
- USD 20 total / USD 3 daily Astra ceilings; 5 live analysed events per profile/day; worker concurrency 1; 10-second audio target.

## 2026-09-13 clarification: AI interpretation for clinician and patient

The owner clarified that the intended AI layer combines acoustic analysis,
patient-reported listening outcomes, hearing evaluation/audiogram, and the exact
hearing-aid type. Its purpose includes analysis and useful recommendations; it
must not be reduced to a generic summary merely because it is not a professional
hearing-aid fitting prescription.

The intended product has two outputs from the same evidence:

- Clinician: a detailed account of observations, relevant audiogram/hearing
  evaluation context, possible explanations for difficult listening moments,
  and recommendations for the audiologist to assess. Separate observed data
  from model inference, identify uncertainty and missing inputs, and link each
  recommendation to its supporting evidence.
- Patient: a concise explanation and practical advice about functions available
  on their exact device, including supported user adjustments in the Widex
  Allure app. Candidate actions can include using available programs, equalizer,
  directional focus or the manufacturer's own sound assistant. Show only actions
  whose compatibility and availability have been established for that model,
  technology level, app version and configured programs. Do not generalize an
  Allure AI RIC-only feature to the BTE family.

Hearing-aid fitting prescriptions and automatic changes to professional fitting
remain outside this clarified purpose. REM is not an implementation prerequisite
for explanatory analysis or documented user-control guidance; where an inference
requires calibrated at-ear output or validated fitting targets, report that
missing evidence rather than invent it. Direct control of the Allure app from
iHear has not been verified. The initial product interpretation of the owner's
request is guidance for a patient-performed change, not a claim of integration.

Manufacturer evidence checked on 2026-09-13:
[Widex Allure app](https://www.widex.com/en/hearing-aids/apps/allure-app/) documents
programs, equalizer, Direction Focus, AI Sound Assistant and AI Quick Assistant.
The same page limits Clarity Boost to Allure AI RIC; generic app documentation
alone does not prove that every feature is present on a given patient's BTE.

The versioned implementation and its verification are tracked in STATUS.md.
Implementation or synthetic-fixture acceptance does not establish clinical
validity. The existing API-off decision, private access and cost boundaries remain
unchanged; this clarification does not activate a provider or transmit patient data.

## B. Engineering choices made by Codex
- One Next.js App Router application, TypeScript, CSS; Python CPU worker.
- Local Supabase Postgres, private Storage and pgmq; no SQLite fallback.
- Opaque random, hashed server-side capabilities in HttpOnly cookies: workspace owner and patient-scoped pairing. No browser service key.
- Separate durable DSP, interpretation and report records. Transactional job idempotency by event and pipeline version.
- JSON profile snapshots stored with events; original audiograms are clinician-entered synthetic examples.
- `main` integrates reviewed work without rewriting history. `implementation/local-milestone` preserves the first application milestone; `infrastructure/linux-sandbox` carries the subsequent dedicated runtime and security changes. Runtime identity is checked separately against its protected artifact manifest.
- A private Tailscale Serve HTTPS origin supports cross-device local testing. It is neither a public deployment nor a future runtime dependency.
- Jobs use renewable Postgres leases and pgmq visibility, bounded retries, independent DSP persistence and idempotent audio deletion. Stale report revisions cannot publish as current.
- Each claim uses a fresh immutable UUID as lease authority. PDF paths include that attempt UUID; a late process cannot delete or publish another attempt's file. Already-ready reports reconcile completion without regeneration.
- Exact provider input-token preflight, bounded structured output, transactional global reservation, conservative ambiguity holds and a freeze on reported overage guard Astra calls. Refreshes and report downloads make no generation calls.
- All visitor workspaces are isolated by server-issued capabilities; the landing showcase is immutable synthetic content. There is no owner-cookie recovery feature in this milestone.
- Report generation uses stored acoustic features and interpretations; it incurs no additional Astra call. A scheduling sweep prepares due follow-up reports in the profile timezone and reuses an unchanged input revision.

- Historical Clear Signal decision: report template 3 introduced a new cache identity. Before changing worker/report
  versions in either direction, stop web admission, drain unfinished jobs with
  the current worker, stop that worker, and check the queue again. Historical
  PDFs remain intact; no reset or destructive migration is part of this change.

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
