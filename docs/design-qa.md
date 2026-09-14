# Frontend review — 2026-09-14

The owner requested a personal review and implementation by the main model.
No work in this review was delegated. Clear Signal, its original glass illustration
and the two recording actions remain the design foundation.

## Observed defects and repairs

| Surface | Observed defect | Repair |
| --- | --- | --- |
| Patient directory | Avatar, name and fitted-ear text ran together; mobile moment counts had no label. | Explicit identity grouping, readable name, separated metadata and labelled mobile counts. |
| Search and filters | Search icon was not vertically centred; filters mixed visible and hidden labels. | A shared labelled grid and an input-relative icon. |
| Connection failure | Raw “Failed to fetch” appeared alongside “Updates automatically”; an initial failure could claim there were no patients. | Actionable errors, retry and truthful retained-result status; unreadable successful responses now fail. |
| Allure confirmation | Patient instructions filled oversized checkbox cards. Global fieldset and input rules shifted their tops and stretched checkboxes to text-field height. | Short control labels, scoped sibling spacing and correct native checkbox size. |
| Patient home | Installation content pushed the second recording action below the sticky navigation at 390 × 844. | Both actions precede the compact installation offer; instructions and storage caveat remain available. |
| Analysis and guidance | Tiny chart/model captions and long full-width guidance made the hierarchy difficult to scan. | Larger reading text, matching percentage labels and a separate patient-preview column. |
| Patient moment | Header suggested pairing again; a transient error persisted after successful polling. | Keep the direct return to the listening space and clear a recovered error. |

## Current evidence

The live owner directory was captured before changes. A subsequent live-tab reload
was rejected by automatic approval review with a Cloudflare-dashboard access reason.
No dashboard was opened and the rejected live reload was not retried. Personal
visual review continued on the local application, using an explicitly synthetic
profile and saved result fixture. The fixture made no provider calls, stored no
audio, changed no budget, and is not evidence of live AI quality.

Personally inspected: directory, new/editable profile controls, expanded clinician
moment, recording evidence, AI guidance, QR/link pairing, paired patient home,
history and patient result, plus the preserved landing illustration. Before/after
captures remain in ignored local operator evidence, not public Git.

Production build and typecheck passed. All 41 Node tests and 11 production-build
browser scenarios passed. Browser checks cover Chromium and WebKit, automated
WCAG/keyboard checks, geometry at 390/513/768/1280 px, retry and stale results,
Allure confirmation invalidation, patient actions above navigation, installation
help, synthetic microphone permission changes and separation of guidance audiences.
The full audio/worker/database pipeline was not rerun for these frontend changes.
Physical phone installation, OS permission persistence and hearing-aid behaviour
were not tested. Deployment evidence is recorded separately in `STATUS.md`.
