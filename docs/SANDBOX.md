# Dedicated Linux sandbox

The dedicated ThinkPad is a private iHear runtime. The MacBook remains the source
authoring machine. Exact SSH aliases, the pinned public host fingerprint, paths,
tool binaries and private HTTPS origins are recorded in ignored
`.local/sandbox/host.json` and the iHear CORTEX sandbox record. No private key or
service token belongs in this document. The separate Linux binding is ignored
`.local/sandbox/runtime.json`, owned by the operator with mode 0600; it holds only
the schema version and expected hostname. [SECURITY.md](SECURITY.md) owns the
private connection boundary and the public demo gate. The project skill at
`.agents/skills/ihear-sandbox/SKILL.md` loads this runbook for future operations;
a new MCP server would add an unnecessary service and privilege boundary.

## Identity and capacity

- Lenovo ThinkPad E590, Intel i5-8265U, 4 physical cores / 8 threads, x86_64.
- Ubuntu 24.04.4 LTS; operator `ondrej`, home `/home/ondrej`.
- Runtime checkout `/home/ondrej/iHear`; authoring checkout `/Users/ondrej/iHear`.
- 7.5 GiB usable RAM, 4 GiB swap, 238.5 GiB NVMe. Pre-install free disk was
  206 GiB. These are observed host values, not a concurrent-user guarantee.
- Native Docker Engine and Compose; Node and pnpm are installed under
  `/home/ondrej/.local/bin`; Python is `/usr/bin/python3`. pnpm and Supabase CLI
  versions are fixed by the repository lockfile.

Start from the MacBook with `python3 scripts/sandbox.py status`. The helper checks
the effective SSH configuration, remote hostname/user/home and public host-key
fingerprint before inspecting Git, services and resource usage. It performs no
remote mutation. Never disable host-key verification to repair a connection.

## Service ownership and network

| Component | Owner | Listener / storage |
| --- | --- | --- |
| Supabase + worker | `ihear-stack.service`, operator ondrej, local Docker | Supabase published ports only on 127.0.0.1 |
| Next.js | `ihear-web.service`, locked system account ihear-web | 127.0.0.1:3000 |
| App proxy | nginx | 127.0.0.1:8080 |
| Dashboard | `ihear-monitor-dashboard.service`, unprivileged ihear-monitor | 127.0.0.1:9080 |
| Collector | `ihear-monitor-collector.service`, root, triggered by timer | `/var/lib/ihear-monitor/metrics.sqlite` |
| Private ingress | Tailscale Serve | app HTTPS 8446; owner dashboard HTTPS 9443 |
| Domain web | `ihear-domain-web.service`, locked account ihear-domain | 127.0.0.1:3001; separate cache |
| Domain proxy | nginx, exact iHear hostname | 127.0.0.1:8081 |
| Domain ingress | `ihear-domain-tunnel.service`, systemd DynamicUser | outbound Cloudflare Tunnel; owner-only Access |

The Linux Compose overlay connects the worker directly to the existing Supabase
Docker network using container DNS. It does not require Docker Desktop's
`host.docker.internal`. Docker's daemon defaults bind published ports to loopback;
the launcher checks both that prerequisite and the actual resulting port bindings.
UFW allows the two HTTPS ports only on `tailscale0`. No Funnel or anonymous public app
deployment is used. The additional owner-only custom-domain path is documented
in [the domain operations runbook](../ops/domain/README.md). Supabase Studio is
accessible only through an explicit SSH port forward when needed.

The app proxy and dashboard accept only the exact tailnet owner login injected by
Tailscale Serve. Direct loopback requests without that identity receive 403. The dashboard server
cannot bind to a public interface, exposes no controls and opens telemetry SQLite
read-only. The root collector is a separate, root-owned program; its privilege is
needed for bounded local Docker inspection. See `ops/monitor/README.md` for the
complete minimized data contract.

The web account has no Docker or supplementary group and no login shell. systemd
hides operator home directories, mounts the checkout and exact Node executable
read-only, and supplies the mode-0600 environment file through the service manager.
The web account cannot read that file or the operator's SSH state. Persistent
framework writes go to a private cache bind; temporary files use private `/tmp`.
Memory is capped at 768 MiB, CPU at 150% of one core and tasks at 128. Do not add
the account to the operator/Docker groups to repair a permission error.

Private nginx enforces 20 requests/second globally, burst 100, 24 active requests,
bounded timeouts and a 3 MiB body ceiling. Application and database admission add
smaller body limits, scoped rate limits and finite retained-data/queue ceilings.
These are local overload controls. Public volumetric DDoS protection requires the
separate edge/tunnel configuration and acceptance in SECURITY.md.

## Prepare, activate and update

On the verified runtime host, use the dedicated Node/pnpm PATH and a clean source
revision. Do not copy the MacBook's `.env.local`, local database, audio or cookies.
Linux creates its own mode-0600 `.env.local` from the local Supabase stack. The
interpretation API is deliberately disabled; DSP, model inference and PDF reports
remain enabled. Initial preparation downloads public images and model weights.

```bash
cd /home/ondrej/iHear
export PATH=/home/ondrej/.local/bin:$PATH
pnpm install --frozen-lockfile
python3 scripts/linux.py prepare --origin "$IHEAR_PRIVATE_ORIGIN"
sudo python3 ops/linux/install.py
sudo systemctl enable --now ihear-stack.service ihear-web.service nginx.service
sudo systemctl start ihear-monitor-collector.service
sudo systemctl enable --now ihear-monitor-collector.timer ihear-monitor-dashboard.service
```

`IHEAR_PRIVATE_ORIGIN` means the exact app origin in the verified private binding.
The installer validates the protected host binding/path and derives the permitted
app/dashboard login from current Tailscale state. It installs root-owned monitor
sources, nginx configuration, log rotation and systemd units. It does not create
ingress or change the power policy. Validate and inspect accepted Tailscale Serve
configuration after setting the two private ports, as shown in the monitor README.
nginx was absent before this task. Its newly installed distribution default
would expose port 80 on all interfaces; the installer preserves that canonical
symlink at `/etc/nginx/sites-disabled/ihear-distribution-default` before enabling
the private proxy. A conflicting backup causes a stop for manual reconciliation.

Preparation applies committed additive migrations and builds both artifacts.
Routine `start` uses existing images and the already-built Next.js artifact.
No reset is part of startup. `systemctl restart ihear-web` restarts only the web
process; stack maintenance stops the web first, then the stack, preserving data.
Both prepare/start require a clean committed checkout and the exact current
Tailscale node DNS name on HTTPS port 8446. Successful preparation writes mode-0600
`.local/linux-artifacts.json` binding HEAD, worker image ID and Next BUILD_ID.
Startup rejects a missing or mismatched manifest before changing services.
Prepare and start reject Funnel, unexpected Serve hosts/ports/upstreams and unknown
Serve configuration fields. Normal status output reports origin checks as booleans.

With the custom domain active, both web services admit work to the same database
and read the same application artifact. Before rebuilding that artifact, changing
schema or stopping the stack, stop the domain connector and domain web service as
well as the private web. Stopping only `ihear-web` no longer closes all admission.
The domain validator pins the current application HEAD and BUILD_ID; a later app
release must update and independently verify that binding before restarting the
domain services. Follow the domain runbook and preserve the disabled ingress on
failure. A routine application restart is not permission to bypass these pins.

Before any update record remote HEAD, branch/detached state and dirty status.
Preserve and reconcile unexpected changes. Fetch an explicitly reviewed source
revision, prepare it, install changed units if needed, restart only affected
services and verify source/artifact/runtime parity. Do not whole-tree-sync the
MacBook directory. Keep ignored runtime state in place. A published source commit
does not by itself prove that the running process uses it.

## Report-template update and rollback gate

A template switch must not leave an old worker consuming new report jobs (or a
rollback worker consuming unfinished newer reports). Before checkout/build:

1. Verify host binding, clean HEAD, service owner and protected artifact manifest.
   Save a mode-0600 database dump, current environment and artifact manifest in the
   ignored runtime backup directory. Retain existing storage objects and volumes.
2. Stop `ihear-domain-tunnel.service`, `ihear-domain-web.service` and
   `ihear-web.service` to close both entry points. Keep the current
   worker running until all jobs in `queued`, `retry` or `running` and all reports
   in `queued` or `generating` have finished. Do not reset quotas or alter job rows.
3. Stop the worker container gracefully, leaving Supabase up. Recheck both counts
   after the worker stops, because its scheduler is also a producer. If either is
   nonzero, restart the old worker, drain and repeat before changing source.
4. Fetch/check out the reviewed commit and apply its additive migration during
   `scripts/linux.py prepare`. Build artifacts from that clean commit and align
   `REPORT_VERSION`. Version 4 preparation enforces 4 in both web and worker.
5. Advance and verify the root domain HEAD/build binding for this exact release.
   Activate the prepared worker with `scripts/linux.py start`, start both web
   services, verify readiness, then resume the domain connector. Existing systemd/nginx units are reused when unchanged. Verify the
   manifest, prepared/running image identity, Next build and preserved records.
6. Verify real new results and a current-version PDF through the private origin,
   unchanged API-off state, empty work queue and removal of successful raw audio.

Rollback uses the same admission/drain/stop/recheck gate in the other direction.
For this v4 release, prepare a reviewed forward rollback commit restoring the v3
web/worker implementation while retaining every applied migration file. Append
an additive migration restoring report defaults to 3, restore the saved v3
environment, and build matching artifacts with the canonical launcher. Advance
the protected domain HEAD/build binding to those exact rollback artifacts before
reopening ingress. Do not activate an unprepared rollback or reset the database.
A literal old checkout is insufficient because migration reconciliation rejects
applied versions missing from source. Historical ready PDFs and v2 interpretation
records remain retained; a v3 renderer does not show all new guidance fields.

The older `rollback/clear-signal-v2` branch (`f930658`) belongs to the earlier
v3-to-v2 release and is not a rollback candidate for this migration. A later
return to v4 must append a new default-v4 migration. Rollback activation must be
reported separately from preparation or a transaction-only SQL check.

Prepared candidate: `rollback/dual-guidance-v3` at
`38b93f07cca28968dbaa8d3349a75aee99fccd2e`. It preserves the v4 migration and adds
`20260913193644_restore_report_defaults_v3.sql`. Its application matches the prior
v3 source. A local transaction verified report-column and both function defaults
return to 3, then rolled back to 4. This is preparation evidence; the rollback
has not been activated. The private release helper uses this additive rollback,
never a database restore or a literal old checkout.

A failed prepare/start leaves admission closed until the prepared
revision or verified rollback is ready. Never use a database reset as rollback.

## Always-on policy

`/etc/systemd/logind.conf.d/60-ihear-server.conf` ignores lid switches on battery,
external power and a dock, and disables idle sleep. The matching file under
`/etc/systemd/sleep.conf.d` disables suspend, hibernation and hybrid modes. Sleep
targets are masked. OpenClaw's user service is disabled and stopped; its source,
configuration and data are retained.

Original unit/target states were saved under
`/home/ondrej/.local/state/ihear-bootstrap`. Four sleep targets were already
masked before this task; rollback must preserve those existing masks.
Only `suspend-then-hibernate.target` was newly masked.

Software sleep prevention does not establish recovery after exhausted battery,
loss of mains, firmware intervention or a hardware fault. Record a real closed-lid
observation and a controlled reboot separately. Automatic boot when AC returns
is a firmware setting and remains unverified until physically tested. Do not
change firmware remotely by inference. Keep ventilation clear in the server room.

## Monitoring, logs and diagnosis

The dashboard refreshes every 20 seconds and marks samples stale after 90 seconds.
It shows host CPU, RAM, swap, disk, temperature, network rates, lid, battery/AC,
uptime, service/container states, application aggregate counts and sanitized
requests. Missing probes are explicit. Charts retain 30 days of collected data;
the dashboard shows the last 24 hours and the latest 250 request rows.
The dedicated installer overrides the collector's small portable default with
every discovered iHear Supabase container plus the worker, using an exact name
allowlist. Other projects' containers are excluded. Docker utilization is collected
in one bounded batch per sample.
Network rates use observed physical interfaces with a sysfs hardware device;
Docker, veth, loopback and Tailscale interfaces are excluded to avoid double counting.

Browser visitor counts are 30-day random-cookie counts, not identified people.
Cookie deletion, shared browsers and multiple devices affect them. Request rows
contain time, a random request ID, allowlisted route class, method, status,
duration, bytes and browser pseudonym. They contain no names, raw paths, URL
queries, pairing codes, IP addresses, user agents, recording contents or auth
cookies. nginx's app error log is suppressed because it may include raw paths;
failed HTTP status remains visible in the sanitized log.

```bash
systemctl status ihear-web ihear-stack ihear-monitor-dashboard --no-pager
systemctl list-timers ihear-monitor-collector.timer --no-pager
journalctl -u ihear-web -u ihear-stack -u ihear-monitor-collector --since '30 minutes ago'
python3 scripts/linux.py status
docker stats --no-stream
```

Journal inspection is an operator-only diagnostic action. Do not copy raw journal,
Supabase startup output, environment files or database dumps into public reports.
The Supabase CLI prints local service keys; the launcher stores its output in
ignored protected logs. nginx access files rotate daily or at the size check,
keep seven rotations and delay compression so the collector can drain a renamed
file. Docker uses the bounded local log driver. The dashboard is hosted on the
same laptop: if the host/network is down, it cannot report its own outage to you.
An external uptime notifier has not been configured.

## Rollback

Stop only the iHear units and disable only its two Serve ports. Preserve Docker
volumes, `.env.local`, telemetry and the pre-change state records. Restore the
previous compatible source revision, rebuild, and restart its matching units;
never undo schema changes by resetting data. To retire this sandbox entirely,
disable its monitor timer/dashboard, web and stack units and retain their data.
The preserved distribution-default nginx symlink can be moved back to
`/etc/nginx/sites-enabled/default` only if intentionally restoring its port-80
listener; test nginx configuration before restarting.

Power-policy rollback removes only the two `60-ihear-server.conf` files and
unmasks only the newly changed target, then reloads logind during an approved
maintenance window. OpenClaw restoration is a separate owner decision because it
reverses the dedicated-host allocation; its preserved user unit can then be
re-enabled. Packages and original infrastructure records need no destructive
cleanup.

## Acceptance evidence

Initial acceptance on 2026-09-12 used clean runtime commit
`07c57099c1b28ded53f938753e339ee5adc8aaa9`. The later handoff documentation/skill
commit recorded that initial evidence. The security update below supersedes this
source/artifact binding; the closed-lid and reboot observations remain historical.

| Check | Observed result |
| --- | --- |
| Runtime contract | 11/11 isolated Python tests passed |
| Monitor contract | 16/16 tests passed, including identity, ingestion, rotation, unknown states and physical-interface selection |
| Ubuntu x86_64 worker | 39/39 tests passed under 1 CPU / 2 GiB, with no network or runtime credentials |
| Private application | 10/10 existing browser journeys passed: pairing, both PCM actions, real DSP, isolation, search, offline retry, PDF reuse and scanner/revocation |
| Actual model/data state | 4 ready analyses with ready Silero/YAMNet provenance; 1 ready PDF; 0 unfinished jobs, API usage rows or raw audio objects |
| Dashboard ingress | Owner tailnet HTTPS 200; absent/wrong identity on loopback 403; 13 iHear containers observed |
| Logs | Live rotation retained 0640 ownership; 442 source rows matched 442 ingested rows; synthetic private path/query marker absent from log files and telemetry SQLite |
| Route classes | Nine live exact/regex route probes matched the corrected map |
| Closed lid | Owner physically closed the lid; Linux reported closed continuously through setup, DSP work and reboot |
| Approved reboot | Requested 13:48:18 UTC; SSH and all main services verified by 13:50:18 UTC; no manual boot interaction requested; data, env hash and telemetry retained |
| Boot timing | systemd-analyze reported 58.628s (10.062s firmware, 6.702s loader, 1.999s kernel, 39.863s userspace); this excludes shutdown time |

The initial deployed worker image was
`sha256:7712114f462d0ba6dd004ff67cb81c3a813f31d0de20ab328167380cd8eefe3e`;
the Next BUILD_ID was `vByxsc45d-wJkiEcUjAbw`. Both matched its runtime manifest.
The initial migration head was `20260911182710_default_report_template_version_2`.
The Linux database is separate from the MacBook's earlier phone-test database;
no patient data or browser capabilities were copied between them.

After the synthetic workflow, the host used about 2.9 GiB RAM with 4.6 GiB available,
worker usage was 472.5 MiB and the web unit used about 131 MiB. The sampled maximum
during this setup/test window was 3.16 GiB RAM; samples can miss short peaks.
Non-root usable disk space was 192 GiB after installation. The machine is accepted
for this bounded private sandbox, not for an unmeasured public load.

Initial verification logs keep their original coarse `other` classifications
before the route-map repair. Planned maintenance can also leave real 502 rows;
history was preserved rather than cleaned to make the dashboard appear healthier.
Detailed local evidence is in ignored `.local/sandbox/` on the authoring host.

Automatic boot after complete power loss, long-duration thermal behavior and
external outage notifications are unverified/unconfigured. The dashboard itself
cannot send a notification while its host is offline. Physical iOS and hearing-aid
limitations from ACCEPTANCE.md still apply.

## Security integration evidence — 2026-09-12

The security implementation was independently reviewed and installed on the
existing private sandbox. Additive migration
`20260912141939_sandbox_abuse_admission` sets finite database and queue ceilings;
DATA_MODEL.md owns their exact values. The scheduler remains alive at saturation
and resumes when a slot is freed. Browser growth admission and scheduled reports
use consistent global-before-row lock ordering.

| Check | Observed result |
| --- | --- |
| Source checks | 26 runtime-contract tests, 10 publication-scanner tests, 18 audio/backend tests, TypeScript and production build passed; 16 unchanged monitor tests passed in the initial integration |
| Real PostgreSQL | Five integration suites passed on an isolated schema-only database with synthetic fixtures; live patient rows were not copied |
| Actual Python scheduler | A separate integration probe filled the 50-report ceiling, returned normally at saturation, freed a slot and scheduled again despite an exhausted web-growth bucket |
| Ubuntu worker | 41 tests passed in a freshly built x86_64 test image with no network/credentials and 1 CPU / 2 GiB; the separate opt-in database test was run against the isolated database |
| Process confinement | 22 live checks passed: dedicated UID, no Docker group/capabilities, hidden operator home, unreadable environment file, read-only source/Node mounts, writable private cache and expected ingress/client-bundle behavior |
| Owner ingress | Missing and different identities received 403; the owner received 200. Caller-supplied identity headers through Serve could not replace its authenticated owner header |
| Bounded requests | On `57d2c1c`, a 3 MiB + 1 body received 413. 160 GET requests at concurrency 16 produced 104 HTTP 200 and 56 HTTP 429 responses, with no 5xx |
| Client artifacts | 25 built static files contained no checked private DNS name, tailnet IP or owner login |
| Data preservation | Pre-update counts were retained before new tests; final snapshot: 4 synthetic profiles, 10 events/ready real-model analyses, 2 ready PDFs, 0 unfinished jobs, raw audio objects or API usage |
| Runtime binding | Clean source, protected manifest, prepared Next BUILD_ID and the running worker's platform manifest matched; final exact revision and IDs are in ignored operator evidence |

The browser result is cumulative, not a clean ten-test run on the final revision.
At `2b660c2`, nine tests passed and the camera-fixture QR test timed out; a targeted
profile/QR scanner/revocation rerun passed 2/2. The trace also showed a rejected
static asset, but it did not establish that as the cause of the camera timeout.
The proxy burst was raised from 40 to 100 while retaining 20 requests/second,
the 24-active-request ceiling and all backend limits.

At `57d2c1c`, the final full run passed two accessibility/layout tests, then failed
at new-workspace setup with application JSON 429; seven dependent tests did not
run. Read-only database inspection confirmed all ten hourly workspace admissions
had been consumed by repeated new contexts. No rate counter was changed or reset.
All ten scenarios are covered across the recorded successful runs, while the
single-run final-revision browser gate remains PARTIAL. For a future clean run,
wait for the next UTC hourly window and run the suite once. Do not weaken live
admission or recover a capability from traces to make a test pass.

An earlier deployment exposed a real worker packaging failure: a restrictive
checkout umask left newly copied Python files unreadable by the worker UID.
`2b660c2` makes only the copied public worker/config files readable and traversable
before switching to the unprivileged user. A fresh production image imported
the real worker modules as UID 10001, and queued test audio then drained normally.
The original failed run and later QR/quota failures remain in protected operator
evidence; they were not erased or counted as passing tests.

Docker 29's containerd image store distinguishes the top-level OCI index,
platform manifest and container image/config identity. Compare the running
container's `ImageManifestDescriptor.digest` with the prepared image descriptor
for `linux/amd64`; separately compare the image index with the build manifest.
Do not treat inequality between these different types of digest as source drift.

Before applying the security migration, the operator saved a root-only database
dump, source revision, environment, artifact manifest, nginx config and web unit
under `/var/backups/ihear/`; the exact backup directory is kept in protected
operator evidence. Stop only affected iHear services for recovery and preserve
the newer database. Restoring a dump would replace newer data and needs explicit
owner approval. This update did not perform OS upgrades, another reboot, public
DNS changes or Cloudflare activation. SECURITY.md records the remaining public
release prerequisites. Independent source/security review is PASS; the final
single-run browser evidence and public release remain PARTIAL and NO-GO respectively.


## Clear Signal activation — 2026-09-12

The reviewed runtime is `f3ab5a6fc5813f845ca44eef28f5e621eab907e3`.
Next BUILD_ID is `leIR2dbOQwxwEI6VTkMTE`; the prepared/running worker image ID is
`sha256:1194e36656497efb48039bf344232a8bfa6230e3365e4ce45249afe6b0584260`.
The running and prepared platform manifest digests also match. Report version 3
and migration `20260912161759` are active; pipeline remains 1 and API use is off.

The private runtime backup is `.local/backups/clear-signal-20260912/`: database
dump, environment, previous build manifest, previous Next artifacts, record hashes,
deployment log and verified rollback bundle. Files are mode 0600 under a private
directory. The previous worker image is retained as `ihear-worker:before-clear-signal`.
Rollback branch `rollback/clear-signal-v2` at `f930658` is present on both authoring
and runtime hosts. It has not been activated. Preserve its applied migration
history and follow the report-version gate above if rollback is required.

The admitted update preserved all pre-existing patient/event/analysis/report row
hashes. After synthetic verification, 14 real-model analyses and three PDFs are
ready; no unfinished job, raw audio object or API usage remains. Final browser
coverage is 9/10 followed by a 2/2 profile/QR retry on unchanged runtime source.
The QR fixture's first timeout is retained as an intermittent test limitation,
not silently discarded. The current PDF's three pages (7,929 bytes) were inspected.
Source/artifact identity, private ingress, monitoring and confined service limits
pass. Existing security and physical-device limitations still apply.

## Owner-only domain activation — 2026-09-12

The domain operations source is `3387c92406c100f22e25f67a9357c4de1d06a18e`,
installed separately under `/opt/ihear-domain`. The existing app checkout remains
clean at `f3ab5a6fc5813f845ca44eef28f5e621eab907e3` with the same build and worker.
The only existing artifact metadata change was BUILD_ID permissions 0664 to 0644.
The private web was not restarted and all prior data hashes were preserved.
Both new domain units are active and enabled at boot. Stopping just the connector
closed the domain, preserved private service health and was successfully reversed.
No host reboot or OS package upgrade was performed. See [STATUS.md](STATUS.md) for
live owner/edge evidence and remaining verification limits; use the domain runbook
for scoped disable/recovery without altering Tailscale, the database or worker.
