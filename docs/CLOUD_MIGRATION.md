# Cloud migration plan

Prepared on 2026-09-11. **No cloud project, paid worker or public application was provisioned.** The working local stack is Postgres + Storage + pgmq through Supabase CLI, one Docker CPU worker, and one Next.js application. Public GitHub visibility does not constitute a public application release.

## Resources and separation

| Target resource | Purpose | Initial configuration |
| --- | --- | --- |
| Vercel `ihear-web` | Landing, clinician UI, patient PWA and short Node API routes | One Next.js project. `vercel.json` disables Git auto-deployment until release approval. |
| Supabase `ihear-demo` | Durable production-demo data, private objects and jobs | One hosted project in a region near the worker; migrations create `ihear`, pgmq and private buckets. |
| Render `ihear-audio-worker` | DSP, Silero, YAMNet, interpretation, report scheduling and cleanup | One Docker worker, concurrency 1. `render.yaml` proposes Frankfurt, plan `1c-2g`, 1 CPU / 2 GB; auto-deploy off. |

Vercel Preview must use a separate disposable database/project or Supabase preview branch, separate storage and credentials, with `OPENAI_API_KEY` absent. Do not point an unreviewed preview at production data or its budget ledger. One hosted production-demo project is the initial allocation; preview data isolation may require an additional resource. Give an approved preview a fixed HTTPS origin for pairing. Production and preview capabilities do not transfer across origins.

The Render plan is a sizing hypothesis. Repeat the local benchmark on Render's CPU architecture and measure startup, peak RSS, warm event latency and a queued burst before selecting a paid size. The current plan ID and YAML fields are from [Render compute plans](https://render.com/docs/compute-plans) and [Blueprint reference](https://render.com/docs/blueprint-spec). The Dockerfile's final stage is the production worker; its test stage is never the deployed process.

## Environment variables

All credentials are server-only. Never prefix them with `NEXT_PUBLIC_`, put them in Git, paste them into an issue or copy the local generated keys into cloud services.

| Variable | Vercel | Render | Value / contract |
| --- | --- | --- | --- |
| `APP_PUBLIC_ORIGIN` | Required | No | Exact approved HTTPS origin, no trailing slash. QR links and mutation Origin checks use it. |
| `DEV_ALLOWED_ORIGINS` | Empty in cloud | No | Local development only. Never list arbitrary origins in production. |
| `DATABASE_URL` | Required | Required | Hosted connection string with TLS. Web: transaction pooler. Worker: session pooler or direct connection. Copy each provider connection string; do not guess hostnames or passwords. |
| `DATABASE_POOL_MAX` | `3` initially | No | Web connection pool per process, validated 1–10. Account for multiple Vercel instances. |
| `SUPABASE_URL` | Required | Required | Hosted project HTTPS URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret | Secret | Private Storage calls. Never browser-visible. |
| `IHEAR_RATE_LIMIT_SALT` | Secret | No | Independent random value per environment for hashed request-rate identities. |
| `OPENAI_API_KEY` | No | Optional secret | Dedicated bounded demo project credential. Empty keeps real DSP and reports working with explicit unavailable interpretation. |
| `ASTRA_MODEL` | No | `gpt-6-astra` | Fixed reviewed model; unsupported override must fail startup. |
| `ASTRA_REASONING_EFFORT` | No | `low` | No automatic escalation. |
| `WORKER_CONCURRENCY` | No | `1` | One instance, one active job. |
| `AUDIO_BUCKET` | `ihear-audio` | Same | Private, migration-bound name. |
| `REPORT_BUCKET` | `ihear-reports` | Same | Private, migration-bound name. |
| `QUEUE_NAME` | `ihear_jobs` | Same | pgmq queue, migration-bound name. |
| `PIPELINE_VERSION` / `REPORT_VERSION` | `1` / `2` | Same | Schema and idempotency versions. Change code and migration together. |
| `CLINIC_TIMEZONE` | `Europe/Prague` | Same | Profile timezone controls follow-up scheduling; budget day is Europe/Prague. |
| `MODEL_DIR` | No | `/models` | Writable container cache; contains only checksum-verified downloadable weights. |
| `MODEL_MANIFEST` | No | `/app/config/models.json` | Committed artifact manifest. |
| `DEVICE_CAPABILITIES` | No | `/app/config/device-capabilities.json` | Curated sourced family facts and explicit unknowns. |
| `JOB_LEASE_SECONDS` / `JOB_POLL_SECONDS` | No | Defaults `120` / `2` | Bounded job leasing and polling. |
| `TF_NUM_INTRAOP_THREADS` / `TF_NUM_INTEROP_THREADS` | No | `1` / `1` | CPU contention control. BLAS/OpenMP are also limited to one thread. |

Budget ceilings are authoritative database configuration, not ignored environment variables: `ihear.budget_accounts` contains USD 20 total / USD 3 daily; reservation SQL enforces 5 live events per profile/day. Change these only in a reviewed migration with explicit owner authority. Reinitializing a database must not reset an already-used lifetime development budget: export and reconcile the API ledger before activating the same provider credential in another environment. Keep preview keys disabled. API ceilings do not cap Vercel, Supabase, Render, storage or network charges.

The worker prepares a bounded request locally, atomically reserves USD 0.16, then uses the official input-token counting endpoint on that same request. Exhausted budgets prevent even token-count transmission. It refuses generation without a valid count at or below 8,000 input tokens and releases a reservation when preflight proves generation did not begin. Actual-usage settlement, ambiguity holds and a global freeze handle failures or reported overage. See [OpenAI token counting](https://developers.openai.com/api/docs/guides/token-counting). The live preflight and usefulness under the 1,200-output-token cap still require a credentialed validation run. Do not enable cloud Astra until that conditional gate has evidence; never silently raise the ceilings.

## Migration and installation sequence after approval

1. Select a reviewed Git commit. Allocate the named hosted resources, regions and environment separation with owner approval. Keep public traffic and live Astra disabled.
2. In an authorized operator environment, authenticate Supabase CLI, link only the intended project and run `pnpm exec supabase db push --dry-run`, inspect the plan, then `pnpm exec supabase db push`. Use the committed migration sequence; never run a local reset command against hosted data.
3. Verify the `ihear` schema is not exposed through PostgREST, browser roles lack table/function privileges, RLS is enabled, composite workspace keys hold, and private Storage has no permissive browser policies. Migrations create `ihear-audio`, `ihear-reports` and `ihear_jobs`. Do not make the buckets public to fix an access error.
4. There is no private-record seed export. The application ships a labelled curated synthetic showcase, separate from visitor-created workspaces. Create smoke-test profiles through the clinician UI. No `.local`, `.env.local`, browser state, pairing codes, local DB dump, uploaded audio or locally generated PDF is published.
5. Configure Render secrets and manually deploy the selected commit using `render.yaml`. Model installation runs on startup, verifies the committed checksums and can be rerun safely. The cache may be discarded on redeploy; the worker must redownload from the pinned sources. No durable job, audio or report depends on that cache or on local disk. A persistent disk is unnecessary for correctness.
6. Configure Vercel production variables, build the reviewed commit and inspect a restricted candidate. The API accepts a bounded mono PCM WAV under 2.202 MB and a bounded multipart envelope, below the documented [Vercel 4.5 MB function payload limit](https://vercel.com/docs/errors/function_payload_too_large). Audio inference stays in Render. PDF download uses private Storage through the authorized server endpoint.
7. Set the final `APP_PUBLIC_ORIGIN`, enable the intended public domain and create new pairing tokens. Existing local links still point at the MacBook and are not migrated. Cookies and offline profile state are origin-scoped: pair each phone again on production.
8. Run the public-release smoke tests below before announcing the application. Optional Supabase Realtime publication is deferred; current polling already reads the same domain records.

## Free-tier suitability and capacity

As checked on 2026-09-11, [Supabase billing documentation](https://supabase.com/docs/guides/platform/billing-on-supabase) lists 500 MB database, 1 GB Storage and 5 GB egress for Free. It is suitable for a small bounded synthetic pilot only if measured usage remains within quotas and service availability is acceptable. It is not evidence of capacity for an unrestricted public audience.

A measured 10-second mono PCM16 48 kHz test upload is 960,044 bytes. Normal successful extraction deletes that object. The maximum accepted file is 2,202,000 bytes. The first measured two-event PDF is 4,715 bytes; subsequent report sizes depend on event count. Database and current Storage totals are recorded in the acceptance evidence. Retained event metadata, summaries, job rows and report revisions grow even when raw audio is removed. Before release, measure actual growth per profile, terminal queue/archive growth, stale report accumulation and egress under load. Add a reviewed bounded metadata/report retention policy if the measured horizon is too short; do not promise unlimited retention.

## Smoke tests and rollback

- Create one synthetic profile, scan production QR on a fresh phone, confirm pairing, capture both actions, save answers, leave the page, and confirm real DSP and the PDF on the clinician view.
- Confirm actual duration/prebuffer/source metadata, model statuses, raw-object deletion, report reuse, offline foreground retry and one event/job for duplicate uploads.
- Attempt cross-workspace profile/event/report reads and mutations; test anon direct DB/Storage denial against an existing private object.
- With an approved key, exercise a bounded representative Astra sample and assert low reasoning, schema validation, actual token settlement, daily/total/event limits and ambiguity behavior. Do not use the lack of a key as evidence of successful live interpretation.
- Turn the MacBook off and repeat capture, queue processing and report download. Search built/runtime configuration for localhost, private LAN addresses and development-tunnel dependencies.

Rollback: remove public traffic or revert the Vercel alias to the previous verified deployment; stop only this Render worker; preserve Supabase data and ledger. Deploy the preceding compatible worker/web commits and run smoke tests. Use additive schema repair or a provider backup restoration plan, never an unreviewed destructive down migration. Investigate held API reservations before releasing any of them. A cost freeze requires explicit accounting review before unfreezing.

The MacBook-off gate, public-origin fresh-device gate, hosted policy checks and paid-size benchmark remain **NOT RUN** in this local milestone.
