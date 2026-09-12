# Owner-only domain operations

This is an additional entry point for `https://ihear.ofops.co` on the existing
verified Linux iHear runtime. Current activation/evidence is in
[STATUS.md](../../docs/STATUS.md); [SECURITY.md](../../docs/SECURITY.md) owns the
access boundary. Anonymous public access is not authorized.

## Frozen installation

The installer pins application HEAD `f3ab5a6fc5813f845ca44eef28f5e621eab907e3`
and Next BUILD_ID `leIR2dbOQwxwEI6VTkMTE`. It uses the existing artifact, database,
worker and disabled interpretation API. The separate operations source revision
must be recorded without changing the private checkout or its artifact manifest.

A root-owned mode-0700 candidate directory contains the exact reviewed files and
the pinned official cloudflared 2026.9.1 Linux amd64 artifact. Its SHA-256 is
`03f1f25d1cc93b9ad6c60569d44060bc4f17ed97075760ed8cfca4b12dcd68cc`.
Verify an explicit archive/file allowlist and every hash before executing root
code. Stage helper hashes are also checked before import. Never execute a copied
vendor command containing a token or place the token in shell arguments/logs.

The scoped connector token must be transferred only to the authorized iHear host,
kept outside Git and installed root-owned mode 0400. The installer validates its
account, tunnel and digest. Its source copy must be removed after successful
installation; preserve only the protected service credential and owner-managed
recovery material. Do not rotate a different tunnel to repair this one.

`install.py` prepares only the new web/tunnel units, exact nginx vhost, protected
binding/origin override, separate log rotation and journal retention. It does not
start or reload services. Its arguments name the stage, binary/token source and
expected credential account/tunnel/digest. Use the reviewed private operator
binding, not guessed host coordinates. The installed validator lives in
`/opt/ihear-domain/scripts/domain_access.py`.

`localPreflightReady` means only local source/configuration checks passed.
`liveAccessVerified` remains false in this helper. Never treat it as authorization
or a substitute for fresh Cloudflare Access and runtime observations.

## Activation acceptance

1. Confirm the exact hostname/all-path Access app has only the verified owner
   allow rule; no Everyone, Bypass or Service Auth rule. Confirm DNS targets only
   the dedicated named tunnel. Confirm required Access JWT validation has the
   exact audience/team and one loopback 8081 route with fixed Host.
2. Verify root source/config/credential binding, unchanged private nginx/Serve,
   clean runtime HEAD/build, no pending data migration, and retained record hashes.
3. Validate systemd units and nginx syntax. Reload unit definitions, start only
   `ihear-domain-web.service`, then reload nginx for the new vhost, then start only
   `ihear-domain-tunnel.service`. Existing private web/worker remain running.
4. Verify loopback listeners, locked web UID with no supplementary groups,
   read-only source, separate cache, hidden operator state, API-disabled state,
   bounded service resources and logs. Verify actual live connector config,
   matching audience/team, token delivery and reject behavior.
5. Test absent/invalid tokens and a non-owner identity, all major paths including
   static/service worker, exact/default hostname behavior, real owner entry,
   custom-domain links, mutation origins, pairing and PDF download. Preserve
   existing workspaces/data; use bounded synthetic acceptance inputs.
6. Test disable-only rollback and the unchanged private route. Enable the two
   new units at boot only after complete acceptance. Record unrun checks openly.

## Disable-only rollback

Stop `ihear-domain-tunnel.service` first. Keep the Access policy and CNAME in place
so the new entry stays closed. Stop `ihear-domain-web.service` when retiring the
new entry. If removing the new nginx vhost, preserve its exact root-owned contents,
remove only `/etc/nginx/conf.d/ihear-domain.conf`, validate nginx and reload it.
Never alter the private 3000/8080 path, Tailscale, database, worker, sibling tunnels
or mail settings. No database restore is part of this rollback.

## Cost boundary

The selected Access Free, Tunnel and Free DNS path adds USD 0. No usage-billed
product or paid add-on is enabled. The owner ceiling is USD 5, but no provider hard
dollar cap was verified/configured. Cloudflare budget alerts do not enforce one.
Any paid feature, plan change or extra audience needs renewed scope assessment.
Unrelated existing account subscriptions and the prior domain registration are
not capped by this configuration.

Cloudflare documents [budget alerts](https://developers.cloudflare.com/billing/manage/budget-alerts/) as informational only. [Seat management](https://developers.cloudflare.com/cloudflare-one/team-and-resources/users/seat-management/) describes Free-plan seat enforcement.
