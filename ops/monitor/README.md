# iHear operations monitor

This is a small, read-only operations surface for the dedicated Ubuntu host. It uses Python's standard library, one bounded SQLite database, and an nginx JSONL access log. It does not contact an interpretation API and exposes no remote controls.

## Trust and privacy boundary

The dashboard must listen on `127.0.0.1:9080`. Tailscale Serve is the only intended ingress. The server refuses to start on another bind address and requires an exact `Tailscale-User-Login` match on every HTML and API request. A missing `IHEAR_MONITOR_ALLOWED_LOGIN` fails startup. This header is safe only behind loopback-bound Tailscale Serve, which removes spoofed identity headers before adding the authenticated user's login.

The app proxy listens on `127.0.0.1:8080`. Its JSONL log contains only time, request ID, method, an allowlisted route class, status, duration, response bytes, and a random-looking 30-day visitor cookie. The cookie provides no authentication. The log contains no raw path or query, IP address, user agent, name, health payload, body, credential, or capability cookie. The collector rejects fields outside this contract.

“Browser visitors” is therefore a browser-cookie count, not a count of identified people. Deleted cookies, multiple browsers, and shared browsers affect it.

## Installed layout and requirements

- Python 3.12, nginx, Docker Engine, PostgreSQL `psql` inside `supabase_db_iHear`, systemd, and Tailscale.
- Install `collector.py`, `server.py`, and `store.py` as root-owned `0644` files under `/usr/local/lib/ihear-monitor`.
- Create system user/group `ihear-monitor`, `/var/lib/ihear-monitor` owned `root:ihear-monitor` mode `0750`, and the SQLite file owned `root:ihear-monitor` mode `0640`.
- Create `/var/log/ihear` owned by nginx's log-writing account and readable by group `ihear-monitor`; rotate `access.jsonl` with rename/create, then signal nginx. The cursor follows the old inode and drains it before the new file.
- Install the nginx template after validating it with `nginx -t`. It binds only to loopback and proxies to Next.js on `127.0.0.1:3000`.
- Install the systemd templates under `/etc/systemd/system`. The collector timer runs every 20 seconds as root because it reads Docker state; the dashboard runs as the dedicated unprivileged account and opens SQLite read-only.

`/etc/ihear/monitor.env` must be root-owned and not world-readable:

```sh
IHEAR_MONITOR_ALLOWED_LOGIN=exact-login-from-current-tailnet-owner
IHEAR_MONITOR_DB=/var/lib/ihear-monitor/metrics.sqlite
IHEAR_ACCESS_LOG=/var/log/ihear/access.jsonl
IHEAR_DB_CONTAINER=supabase_db_iHear
```

After the owner login is verified from current tailnet state, the intended private ingress is:

```sh
sudo tailscale serve --bg --https=9443 http://127.0.0.1:9080
sudo tailscale serve --bg --https=8446 http://127.0.0.1:8080
```

Verify the accepted Serve configuration with `tailscale serve status`; do not infer it from command success. Activate the dashboard service and collector timer only after file ownership, exact-login authentication, nginx configuration, and loopback listeners are checked.

## Availability semantics

Host CPU, memory, swap, disk, network rate, uptime, thermal, battery, AC, and lid signals are read from `/proc` and `/sys` when Linux exposes them. Docker, database, systemd, and access-log probes report `available`, `partial`, `unavailable`, `invalid_response`, or `gap`. Systemd details are bounded state/result enums; raw journal messages are deliberately excluded because they can contain URLs, identifiers, and credentials. Missing measurements are SQLite `NULL` and display as **Unknown**, never zero. The dashboard marks a sample stale after 90 seconds. History and sanitized request rows are retained for 30 days. Each collector run reads at most 2,000 log lines or 2 MB, and commits cursor movement with inserts so replay cannot double-count a line.

The database query returns aggregate event, job, and report status counts only. It selects no identifiers, names, notes, audio metadata, analysis contents, errors, credentials, or capability material.

The source default observes six expected containers: the database, Kong, Storage, Auth, Realtime, and the iHear worker. That is intentionally honest partial coverage of the Supabase stack. On the prepared host, set `IHEAR_MONITOR_CONTAINERS` in `monitor.env` to the discovered iHear-only allowlist if additional Supabase dependencies should appear. Container names not explicitly configured are not claimed as monitored.

## Local checks

Run from this directory:

```sh
python3 -m unittest discover -s tests -v
```
