# iHear operating contract
Read this file at the start of every task. Canonical status: docs/STATUS.md; owner decisions: docs/DECISIONS.md.

For the dedicated Ubuntu notebook runtime, use `.agents/skills/ihear-sandbox/SKILL.md`
and `docs/SANDBOX.md`; exact private host identity is in ignored `.local/sandbox/host.json`.
The MacBook is the authoring source and `/home/ondrej/iHear` is the Linux runtime.
Security and public-exposure authority live in `docs/SECURITY.md`. The notebook is
the default private sandbox; a Product Hunt mention does not make it publicly deployed.
Never publish actual sandbox IP/DNS/SSH identity or operator captures. Use ignored
private bindings and placeholders. Run `scripts/check_public_source.py --require-binding`
and the exact committed-tree check before publication. Linux host validation uses
ignored `.local/sandbox/runtime.json`; ordinary diagnostics must redact private origins.

- All product UI, documentation, comments, fixtures, errors and reports are English. Progress to Ondrej is Czech.
- Preserve the two-action patient experience. No unrelated features, frameworks or infrastructure.
- Never invent measurements, device capabilities or clinical claims. Keep reports, DSP, model estimates and interpretation distinct. Clinical interpretation belongs to the clinician.
- No transcripts, speaker identity, fabricated SNR/intelligibility, uncalibrated SPL, dBFS/dB HL comparisons, fitting prescriptions or tier guarantees.
- No silent mock substitution. Missing models/credentials and failed/incomplete inference must be visible. Astra reasoning is always low; never escalate automatically.
- No credentials, real patient data, captured audio, local databases or model weights in Git. Audio storage is private; visitor workspaces are isolated.
- Never modify Auralis, CORTEX or sibling projects. Required CORTEX governance records are allowed.
- GitHub is canonical for source, migrations, configuration, design provenance, meaningful decisions and verification. Use small commits; preserve history.
- Local runtime and public GitHub publication are authorized. Public application deployment, paid resources and cloud authorization require separate owner approval.
- Keep docs/STATUS.md accurate; distinguish source, automated checks, simulated audio, physical iPhone tests and cloud release evidence.
- Use managed independent review for security, cost accounting and data custody. Workers own disjoint files and preserve others' changes.
