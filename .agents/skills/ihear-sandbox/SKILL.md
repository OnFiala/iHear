---
name: ihear-sandbox
description: Operate or diagnose iHear's dedicated Linux sandbox, including its SSH identity, services, power policy and monitoring dashboard. Use for this project's notebook runtime, not unrelated hosts or UI design.
---

# iHear sandbox

Read `docs/SANDBOX.md` from the repository root. The private machine binding is
`.local/sandbox/host.json`; it records exact authoring/runtime paths, SSH aliases,
the pinned public host fingerprint and private HTTPS origins. It contains no key
material and stays outside Git. If it is missing, retrieve the current iHear
sandbox CORTEX record or ask for the binding; do not infer another laptop or IP.

Read `docs/SECURITY.md` before changing exposure or preparing public artifacts.
Never echo the entire binding, private origins or SSH identity into shared output.
The Linux runtime separately requires ignored `.local/sandbox/runtime.json`,
schema `{ "schema_version": 1, "hostname": "verified-private-hostname" }`, owned
by the runtime operator with mode 0600. Its hostname must match the current host;
do not derive it automatically during startup to bypass identity validation.

On the MacBook authoring host, start with `python3 scripts/sandbox.py status`.
This checks SSH configuration and remote identity before collecting status.
If already operating on the verified Linux host as `ondrej` in
`/home/ondrej/iHear`, use `python3 scripts/linux.py status` and local systemd
inspection; do not SSH back into the same machine or install the MacBook alias.
A connection error is not permission
to disable strict host-key checks, read a private key, or scan unrelated hosts.

- The MacBook repository is the authoring source; the Linux checkout is deployed
  runtime. Check its HEAD and dirty state before a targeted update.
- `scripts/linux.py` owns the Linux Docker stack. The MacBook uses
  `scripts/local.py`. Never reset a database to make startup succeed.
- External interpretation API use is off. Preserve real DSP and report behavior.
- `ihear-stack`, `ihear-web`, and the monitoring units are systemd services.
  Use the exact names and rollback instructions in the runbook; no broad cleanup.
- OpenClaw is paused with its data retained. Re-enabling it, changing firmware,
  exposing public ports, or wiping the machine is separate scope.
- Monitoring contains infrastructure metrics and minimized request metadata.
  Never put recording bytes, names, pairing codes, auth cookies, URL queries or
  provider credentials into logs or telemetry.

Record significant outcomes in CORTEX. Report source, process, behavior and
physical lid/reboot evidence separately; a successful SSH call does not prove
unattended recovery after a power outage.
