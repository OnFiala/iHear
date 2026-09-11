# Architecture and integration contract

One Next.js App Router app, server-only Postgres/Storage access, Python CPU worker, local Supabase Docker stack. No cloud provisioning in the local milestone. All user-facing strings English.

## Shared wire contract
JSON APIs under /api. Responses are JSON with errors `{error: string}` and meaningful HTTP status. Server-issued HttpOnly SameSite=Lax capabilities. Mutations require the configured same Origin; no client workspace selectors can expand authority.

- GET /api/session returns `{workspaceId, patient: Patient|null}`. Creates isolated workspace owner session if absent; paired patients have patient-only scope. Landing showcase is static synthetic, immutable via APIs.
- GET /api/patients?q=&status=&difficulty=&followUp= returns `{patients: Patient[]}` using database full-text search, not client filtering.
- POST /api/patients body ProfileInput returns `{patient}`.
- GET /api/patients/:id returns `{patient, events: ListeningEvent[], pairing: {url,code,expiresAt}|null}`; owner only. QR issuance via POST /api/patients/:id/pairing; rotate revokes previous token and paired capabilities. DELETE same route revokes.
- PATCH /api/patients/:id body ProfileInput updates profile, keeps historical event snapshots unchanged.
- GET /api/pair/:token returns only `{displayName,expiresAt}` for a valid token, never audiogram. POST same path `{acknowledged:true}` issues patient capability and returns `{patient}`. Manual pairing accepts same opaque token (display a grouped base32/hex code). Pairing must not confer workspace-owner authority.
- GET /api/events returns `{events}` for paired patient. GET /api/events/:id returns `{event}` within scope.
- POST /api/events multipart fields `metadata` JSON and `audio` PCM16 mono WAV Blob. metadata: `{id:uuid, patientId:uuid, kind:'understood'|'difficult', difficulty:string|null, environment:string|null, capturedAt:ISO, capture:{sampleRate:number,preSeconds:number,postSeconds:number,trackSettings:object,sourceLabel:string,routing:'unknown'|'phone-confirmed',interrupted:boolean}}`. Server validates enum, real header, byte size <= 2,202,000 bytes, duration <=10.1s; snapshots current profile server-side. Duplicate event ID does not insert/requeue/charge twice; incompatible duplicate returns conflict. Negative answers required. Server acknowledges only after storage persisted and job enqueued durably.
- POST /api/patients/:id/report ensures a report job exists for relevant input revision and returns `{status,reportId}`. GET same path returns `{status,url?:string}`. PDF download route authorizes scope and streams private bucket object. Page refresh/report GET never invokes Astra.

## Client data shapes
`ProfileInput`: `{displayName:string,audiogram:{frequencies:number[],left:number[],right:number[]},aids:{side:'left'|'right'|'bilateral',left:{model:string,tier:string}|null,right:{model:string,tier:string}|null},followUpDate:'YYYY-MM-DD',note:string,timezone:string}`.
`Patient`: ProfileInput plus `{id,workspaceId,createdAt,eventCount?:number,latestStatus?:string}`.
`ListeningEvent`: `{id,patientId,kind,difficulty,environment,capturedAt,createdAt,status:'queued'|'analysing'|'ready'|'failed',capture,profileSnapshot,analysis:object|null,interpretation:{status:string,result:object|null}|null,error?:string|null}`.
Deterministic analysis uses `duration_seconds`, `sample_rate`, `rms_dbfs` (nullable silence), `peak_dbfs`, `clipping_fraction`, `silent`, `quality_flags`, `bands:[{low_hz,high_hz,relative_energy}]`, `spectral_centroid_hz`, `speech_activity:{status, fraction?}`, `acoustic_categories:{status, categories?:[{label,score}]}`. Model estimates include versions and provenance.

## Database/worker coordination
docs/DATA_MODEL.md contains the exact implemented SQL contract. Tables in private `ihear` schema: workspaces, capabilities, patients, pairing_tokens, events, analyses, interpretations, reports, jobs, api_usage/budget reservations. Durable Supabase pgmq messages reference job IDs. Worker reads Postgres using DATABASE_URL and private storage using SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY. AUDIO_BUCKET=ihear-audio; REPORT_BUCKET=ihear-reports; QUEUE_NAME=ihear_jobs; PIPELINE_VERSION=1. Worker leases jobs, persists DSP before interpretation, deletes audio after successful extraction, bounds retries and retains terminal failure. Report invalidation must cover event analysis and profile changes. Clinic timezone defaults Europe/Prague.


Worker heartbeats renew both the database lease and pgmq visibility. All mutations require current ownership, and expired workers cannot finish/retry/fail jobs. Report publication checks the current input revision. DSP persists before interpretation; retry and reconciliation close raw-audio custody even after a crash between feature persistence and deletion.
