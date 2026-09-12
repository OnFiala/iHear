# Dedicated Linux sandbox

The dedicated ThinkPad is a private iHear runtime. The MacBook remains the source
authoring machine. Exact SSH aliases, the pinned public host fingerprint, paths,
tool binaries and private HTTPS origins are recorded in ignored
`.local/sandbox/host.json` and the iHear CORTEX sandbox record. No private key or
service token belongs in this document. The project skill at
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
| Next.js | `ihear-web.service`, operator ondrej | 127.0.0.1:3000 |
| App proxy | nginx | 127.0.0.1:8080 |
| Dashboard | `ihear-monitor-dashboard.service`, unprivileged ihear-monitor | 127.0.0.1:9080 |
| Collector | `ihear-monitor-collector.service`, root, triggered by timer | `/var/lib/ihear-monitor/metrics.sqlite` |
| Private ingress | Tailscale Serve | app HTTPS 8446; owner dashboard HTTPS 9443 |

The Linux Compose overlay connects the worker directly to the existing Supabase
Docker network using container DNS. It does not require Docker Desktop's
`host.docker.internal`. Docker's daemon defaults bind published ports to loopback;
the launcher checks both that prerequisite and the actual resulting port bindings.
UFW allows the two HTTPS ports only on `tailscale0`. No Funnel or public app
deployment is used. Supabase Studio is accessible only through an explicit SSH
port forward when needed.

The dashboard accepts only the exact tailnet owner login injected by Tailscale
Serve. Direct loopback requests without that identity receive 403. Its server
cannot bind to a public interface, exposes no controls and opens telemetry SQLite
read-only. The root collector is a separate, root-owned program; its privilege is
needed for bounded local Docker inspection. See `ops/monitor/README.md` for the
complete minimized data contract.

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
The installer validates the dedicated hostname/path and derives the permitted
dashboard login from current Tailscale state. It installs root-owned monitor
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

Before any update record remote HEAD, branch/detached state and dirty status.
Preserve and reconcile unexpected changes. Fetch an explicitly reviewed source
revision, prepare it, install changed units if needed, restart only affected
services and verify source/artifact/runtime parity. Do not whole-tree-sync the
MacBook directory. Keep ignored runtime state in place. A published source commit
does not by itself prove that the running process uses it.

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

Deployment and behavioral verification are in progress. Final evidence will
record the source revision, Linux worker image, bound listeners, current host
utilization, real DSP/report workflow, dashboard authentication/log contract,
reboot and physical-lid coverage. This paragraph must be updated before handoff.
