# Security and public demo boundary

The dedicated Linux notebook is the current **private iHear sandbox**. It is not
an Internet-facing Product Hunt demo. The MacBook is the canonical authoring
source. [SANDBOX.md](SANDBOX.md) owns operations and runtime evidence; this document
owns exposure, information boundaries and the public-release gate.

## Information that stays private

Never publish the sandbox's real IP addresses, complete DNS names, SSH aliases,
host-key fingerprints, private-key locations, owner login, pairing capabilities,
runtime environment, database dumps, raw logs, audio, or host-binding files.
Use placeholders in source, documentation, issues, PRs, screenshots and videos.
Record exact connection metadata only in ignored mode-0600
`.local/sandbox/host.json` on the authoring machine and private CORTEX records.
The Linux host uses its separate mode-0600 `.local/sandbox/runtime.json` for
hostname validation. Neither file contains private-key material.

Normal startup and status outputs must not print private origins or dump the
binding. Operator transcripts and browser captures can still contain capabilities
or connection information; do not publish a task transcript or screenshot without
reviewing it. A QR code is a capability, even when its text is not visible.

Before each source publication, stage the intended files and run:

```bash
python3 scripts/check_public_source.py --require-binding
python3 scripts/check_public_source.py --require-binding --ref HEAD
```

This checks tracked content and sensitive artifact paths, including exact private
binding values, without printing matches. The exact committed tree check is the
publication check; the working-tree check helps catch mistakes while editing.
It is a focused safeguard, not general secret detection, OCR or proof that an old
public copy can be recalled. Review commit history and visual artifacts separately.

DNS-name secrecy is not an authentication boundary. Tailscale's trusted HTTPS
certificates publish their full certificate names in Certificate Transparency.
The existing HTTPS name therefore cannot be promised secret or retrospectively
erased from public certificate records. Tailscale still restricts network access;
the owner identity gate is a separate control. This is documented by
[Tailscale's HTTPS guidance](https://tailscale.com/docs/how-to/set-up-https-certificates).

The reachable-history audit examined 259 blobs, including the security changes.
No complete private tailnet address, observed host IP address, SSH alias, key
fingerprint or key path was found. A short machine
label appeared in older source; it was removed from current source. Existing
public history was preserved. This is not a claim that a historical label or
previously shared transcript can be made secret again.

## Private ingress and resource controls

App, database, storage API and dashboard host listeners stay on loopback. Tailscale
Serve provides the private HTTPS ingress; UFW denies other incoming and routed
traffic apart from the documented SSH recovery paths. SSH passwords and root
login are disabled. The dashboard remains separate from the application and
available only to the configured owner identity.

The app nginx proxy also requires that owner's authenticated Tailscale identity.
The installer renders the exact login into a root-owned mode-0600 config. A missing
or different identity receives 403, including a Funnel request with no identity.
The proxy strips identity headers before forwarding to Next.js. Tailscale Serve
removes caller-supplied identity headers before injecting its own; the application
must remain behind this trusted loopback boundary. See the
[Tailscale Serve identity contract](https://tailscale.com/docs/features/tailscale-serve).

The private app admits an aggregate 20 requests/second with burst 40 and at most
24 active requests. Exceeding admission returns 429. Limits use a shared server
key, so new visitor cookies and spoofed forwarded IPs cannot create fresh buckets.
Request headers, idle connections, body reads and upstream connections have timeouts;
the 3 MiB proxy body cap precedes the smaller validated audio limit. These protect
the local application from excess work; they do not provide volumetric DDoS
protection for the network uplink. nginx's semantics are documented in
[request limiting](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)
and [connection limiting](https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html).

Application capabilities, tenant isolation, mutation Origin checks, private
Storage and bounded audio validation remain required behind the proxy. Proxy
authentication does not replace them. Admission must also cover repeated uploads,
profile changes and report revisions; retained rows and pending work need finite
ceilings. Rejection must preserve existing data and valid cached reports.

Telemetry contains only the minimized fields documented in
[the monitor contract](../ops/monitor/README.md). Application errors must not dump
SQL parameters, private paths, URLs or raw exception objects into logs. Logs and
metrics have bounded retention; operational journals remain private.

## Proposed public entry point — not activated

Read-only account inspection on 2026-09-12 confirmed that the owner holds
`ofops.co` and `ofops.online` at Active24, both with displayed expiry 2027-02-10.
`ofops.co` is already active on Cloudflare Free. `ihear.ofops.co` has no explicit
DNS record and currently inherits wildcard records. It is the proposed app
hostname; no DNS record, existing tunnel or mail setting was changed. Account
access is verified, but it does not approve public activation or paid features.

For a future public demo on this host, use an owner-approved public domain through
Cloudflare's protected edge and an outbound Cloudflare Tunnel. No DNS A/AAAA
record may point to the server's real address. No router port forwarding, public
SSH, database, Studio or dashboard listener is allowed. The tunnel must expose
only the reviewed application vhost and reject unmatched hostnames and paths.
Admin access continues through Tailscale.

This is a proposed alternative to the earlier hosted Vercel/Supabase/Render
allocation in [CLOUD_MIGRATION.md](CLOUD_MIGRATION.md), not an approved cloud
resource or deployment. Cloudflare documents an outbound-only tunnel as a way
to avoid a publicly routable origin in its
[origin protection guidance](https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/).
Hiding the origin does not protect an already-known home WAN address from attacks
that saturate the ISP link, and a tunnel alone does not bound application work.

Public activation requires all of the following evidence:

1. Owner-selected domain/account and explicit deployment approval; inspect the
   actual plan's available DDoS, WAF, bot and rate controls. No assumed paid feature.
2. Exact public hostname, tunnel routing and edge policy reviewed and tested.
   Public requests must never receive private DNS names in QR links, redirects,
   JSON, client bundles, headers or error pages. Do not expose the current private
   app origin by simply proxying it to a public URL.
3. Preserve the private sandbox data. Decide whether public data uses a fresh
   isolated runtime or an explicitly approved promotion; never copy current
   capabilities, audio, environment secrets or patient data into a public demo.
4. Run the public web process with no Docker socket/group, operator SSH state or
   sibling application access. A compromised web process must not become the host
   operator. Verify network and filesystem containment, backups and recovery.
5. Verify request/queue/storage ceilings, synthetic-data retention policy and
   recovery after reaching a limit. Measure a bounded concurrent workload on the
   actual host. Single-worker functional tests do not establish public capacity.
6. Audit worker/OS/container dependencies; verify externally observed exposure,
   certificate/DNS state, an external outage alert and an immediate public-ingress
   disable procedure. Test the disabled response without deleting data.

**Public release remains NO-GO until this gate is satisfied.** No Funnel,
Cloudflare account/tunnel, public DNS change, paid resource or public application
activation is authorized by a passing private test or source publication.

The 2026-09-12 installed-host audit found 105 upgradable Ubuntu packages, with
89 entries listing a security pocket, including SSH/TLS runtime components.
No OS package upgrade or additional reboot was performed during the application
security update. Package maintenance, restart planning and post-update recovery
verification remain prerequisites for public activation. This inventory is not a
claim that every pending package maps to a confirmed exploitable vulnerability.

## Recovery

Disable only the affected ingress before diagnosis if abuse or unexpected exposure
is observed. Preserve data and evidence. Use the source/config rollback in
SANDBOX.md; do not restore permissive public ingress to recover availability.
There is no promise of absolute security or uninterrupted service from this
single notebook.
