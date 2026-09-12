# iHear

A quiet way to remember listening moments, and a clearer starting point for a conversation with a hearing-care clinician.

**Illustrative demo only. Use synthetic profiles. This is not a medical device, diagnostic service or fitting prescription.**

One English-first Next.js application provides a patient PWA and clinician interface. Phone audio produces bounded acoustic features; model estimates and optional Astra interpretation remain separate from patient reports and clinician judgment. No speech transcription.

## Source and ownership
This repository is publicly visible proprietary source, **not an open-source release**. You may view and fork it on GitHub under GitHub's terms. Reuse, redistribution, sublicensing or deployment of original code/assets requires written permission, subject to applicable statutory and platform rights. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). This does not establish trademark availability or ownership of ideas.

## Implementation
See [status](docs/STATUS.md), [decisions](docs/DECISIONS.md), [acceptance](docs/ACCEPTANCE.md),
[sandbox operations](docs/SANDBOX.md), [security and public release](docs/SECURITY.md)
and the future [cloud migration](docs/CLOUD_MIGRATION.md).
The working application and reviewed private Linux infrastructure are published
as source; the exact deployed runtime revision is recorded in the sandbox runbook.
No public application has been deployed.

## Run locally

The dedicated always-on Ubuntu sandbox has its own [runbook](docs/SANDBOX.md)
and project skill under `.agents/skills/ihear-sandbox`. It uses systemd, native
Docker, private Tailscale HTTPS and a read-only operations dashboard. Interpretation
API use is currently disabled. The following commands describe the MacBook
development environment.

Prerequisites: Node.js 22+, pnpm 10.33.2, Python 3 for the launcher, and a running Docker Desktop. The Python audio environment is built inside Docker; no host TensorFlow install is needed.

```bash
cd /Users/ondrej/iHear
pnpm install --frozen-lockfile
python3 scripts/local.py start --production
python3 scripts/local.py status
```

Open [the landing page](http://localhost:3000), [clinician demo](http://localhost:3000/clinic) or [patient app](http://localhost:3000/app). Supabase Studio is [local only](http://127.0.0.1:54323). The launcher starts this project's Supabase stack, applies committed migrations, builds the production worker and web application, creates ignored `.env.local` with local keys, and owns its web PID. First image/model downloads take several minutes. It does not authenticate any cloud account.

For live code editing, omit `--production`; stop the managed web process before changing modes. Use production mode for stable offline/PWA verification. If port 3000 belongs to another process, the launcher stops with an explanation instead of killing it.

```bash
python3 scripts/local.py stop
```

Stop preserves local Supabase data and downloaded models. An optional private HTTPS relay is managed separately. To delete **only disposable iHear database data** and invalidate existing pairings, use the explicit reset workflow while the local stack is running:

```bash
python3 scripts/local.py reset --confirm-local-reset
```

Do not run reset during an active phone session or use it against hosted data. Reset is destructive and is not part of ordinary startup. Private Storage cleanup must be checked after a reset; do not treat a schema reset as proof that underlying object bytes were removed.

## Pair a phone

The phone requires a trusted, reachable HTTPS origin. `localhost` on a phone is the phone itself. Set up a private HTTPS relay using your existing Tailscale tailnet, for example with a **free dedicated port**:

```bash
tailscale serve --bg --https=8446 http://127.0.0.1:3000
python3 scripts/local.py stop
python3 scripts/local.py start --production --origin https://YOUR-MACHINE.YOUR-TAILNET.ts.net:8446
```

Keep the actual hostname in ignored `.env.local`. This uses private Serve, not public Funnel, and requires the phone to be connected to that tailnet. Do not overwrite an occupied Serve port. Disable this relay with `tailscale serve --https=8446 off` when finished. The relay and MacBook must remain running during this local milestone.

In the clinician browser, create a synthetic profile and choose **Create pairing QR**. Open it with the phone camera, or use **Scan QR code** / the manual code in the PWA. Confirm the displayed profile and acknowledgement. Enable the microphone, keep the screen in the foreground, wait at least five seconds, then choose either listening action. Negative moments ask two questions. A confirmation of receipt appears only after server acknowledgement.

The original clinician browser owns its isolated demo workspace. Another browser receives a different workspace; a paired phone has only that patient's scope. Losing the owner cookie loses access to that demo workspace. There is intentionally no recovery/login product in this milestone. Pairing links are bearer capabilities, not clinical authentication: do not publish screenshots of live QR codes.

## Verification commands

```bash
pnpm typecheck
pnpm test
pnpm test:db
node scripts/audio-fixture.mjs
pnpm exec playwright install chromium webkit
E2E_BASE_URL=https://YOUR-MACHINE.YOUR-TAILNET.ts.net:8446 pnpm test:e2e
```

Browser tests use installed Google Chrome for deterministic fake-device PCM and a Playwright WebKit build for layout. They create synthetic visitor workspaces in the local stack; they never call Astra when its key is absent. They are not physical Safari certification. The DB test wraps disposable rows in a transaction and rolls it back; the worker unit test command is in [AUDIO_PIPELINE.md](docs/AUDIO_PIPELINE.md). Screenshots, traces and generated PDFs live in ignored `artifacts/`, `test-results/` and `.local/`; they may contain active pairing capabilities and must not be committed.

Repeated full browser runs can reach the ordinary limit of ten new workspaces per source address per hour. A visible HTTP 429 is expected then. Wait for the next window or deliberately clear only the disposable local test counter; do not raise production limits to make a test pass.

`OPENAI_API_KEY` is optional and belongs only to the worker. Configure it only after reviewing the cost and live-validation gates in [cloud migration](docs/CLOUD_MIGRATION.md). No transcript, invented clinical measurement or hidden mock interpretation is substituted when it is absent.
