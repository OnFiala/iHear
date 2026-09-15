# GPT-6 Astra Challenge readiness

Assessed on September 15, 2026. The owner confirmed that iHear targets the
[GPT-6 Astra Challenge on Product Hunt](https://www.producthunt.com/contests/gpt-6-astra-challenge).
This assessment does not authorize provider activation, public access or entry
submission. Current private deployment evidence is in [STATUS.md](STATUS.md).

## Confirmed organizer information

The [Product Hunt announcement](https://www.producthunt.com/p/producthunt/product-hunt-teams-up-with-openaidevs-for-the-gpt-6-astra-challenge)
invites products built with Astra and directs participants to schedule their
launch for Friday, September 18, 2026. Staff confirm that specific launch day in
the replies. The [OpenAI announcement](https://community.openai.com/t/gpt-6-astra-challenge-on-product-hunt/1396727)
also identifies September 18. The static contest countdown is not reliable
evidence of the exact submission cutoff or time zone.

The contest-specific launch guide has not yet been inspected. The submission
page requires Product Hunt sign-in. Full eligibility, required submission fields,
judging criteria, exact cutoff and terms remain unverified. The public wording
does not establish that an application must call Astra through the API at runtime,
or that every line must be authored exclusively by Astra. Do not invent either
requirement or claim full eligibility from the announcement alone.

## Product evidence

| Area | Evidence and remaining gap |
| --- | --- |
| Patient capture and pairing | Implemented; prior real-worker browser acceptance and two earlier physical iPhone events. Fresh complete physical PWA acceptance remains open. |
| Acoustic analysis | Real DSP, Silero and YAMNet; frequency/time detail is stored for newer results. Fresh private runtime has 28 analyses, 10 using the detailed aggregation. Existing older records cannot acquire missing temporal data after raw-audio deletion. |
| Clinician workflow | Profile/audiogram, compact full-text directory, review and PDF implemented. Six reports exist, including one ready v4 report. |
| Astra recommendations | Strict clinician/patient guidance code and synthetic provider tests exist. API remains intentionally off, with zero calls. Actual API compatibility, latency and output usefulness are not yet demonstrated. |
| Phone reliability | Desktop/WebKit tests cover microphone-state, install help and offline handling. Physical Home Screen installation, reopening, permission persistence and interrupted/offline capture need observation. |
| Reviewer access | Existing application is owner-only. No judge/public route or public-data release is approved. Follow SECURITY.md; do not expose the current private dataset. |
| Contest entry | Target identified; no completed entry, scheduled launch or submission acceptance is evidenced. |

The current product is a working private acoustic prototype. The complete
AI-assisted demonstration remains partial. Public/contest readiness is not passed.
API-off is a gap against iHear's intended AI-assisted experience, not a proven
contest eligibility rule. There is no claim of clinical validation.

## Shortest credible completion path

1. After explicit provider activation approval, run a small synthetic scenario
   set through real Astra with an enforced owner-approved spend ceiling. Inspect
   evidence citations, frequency notes, patient text, failure behavior and actual
   usage. Existing infrastructure and API budgets are different controls; a
   previous USD 5 infrastructure instruction is not proof of a USD 5 API cap.
2. Complete one physical-phone journey: pair, install, reopen, record both
   actions, interrupt/resume, queue offline, see clinician results and export PDF.
   Specifically investigate weak captured TV audio without labeling room loudness
   from an uncalibrated phone signal.
3. Prepare an isolated demonstrable entry and presentation showing the real
   patient-to-clinician result and Astra's documented contribution. Confirm the
   launch-guide requirements and schedule the September 18 launch only after
   owner approval. Public access must pass the separate SECURITY.md gate.

Engineering estimate: roughly one to two focused working days for the bounded
private AI/phone demonstration, assuming provider access and timely device tests
with no material defects. Public exposure, full eligibility and contest submission
are separate dependencies; September 18 readiness is not guaranteed by this estimate.
