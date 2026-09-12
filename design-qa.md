# Clear Signal visual verification

final result: passed

## Visual truth and evidence

The owner selected `docs/design/clear-signal-reference.png` (1586 × 992 px design
board) and retained `public/listening-glass.png` as the original 3D artwork.
The board is an illustration of several screens, not a pixel-exact production
viewport. Its phone panel is approximately 340 × 844 px; browser evidence is
390 × 844 CSS pixels at density 1. Comparisons use corresponding content regions
and account for that aspect-ratio difference; no device bezel is app content.

Rendered evidence (ignored local artifacts):
- `artifacts/patient-ready.png`: paired patient, microphone on, two saved moments;
  390 × 844 CSS/pixel viewport. `patient-mobile.png` covers microphone disabled.
- `artifacts/clinician-compact.png`: 1440 × 1000 viewport, selected difficult moment,
  acoustic disclosure closed. `clinician-results.png` opens actual DSP evidence;
  full-page capture height expands with real content.
- `artifacts/webkit-pairing-mobile.png`: 390 × 844 WebKit, reduced motion.
- `.local/clear-signal/report-pagination.pdf` and `final-report-1.png` through
  `final-report-3.png`: three-moment synthetic PDF; A4 rendered at 990 × 1400 px.
- Codex in-app browser: landing at 1280 × 720; clinician/new-profile flow at the
  same viewport; final clinician profile at 768 × 1024. Actual calendar date matches
  the form and PDF after the serialization repair.

The source board, patient/clinic captures and PDF render were supplied together in
the final visual-comparison input. Focused readable captures cover action labels,
identity/date, microphone Stop, selected moment context and PDF technical tables.
Different synthetic names, dates, event order/count and success messages are live
content; no invented values were added to match the illustration.

## Comparison history

1. Initial capture: P2 clinic tab count touched its label; the explanatory heading
   ran into its text. Added explicit flex spacing and a separate heading line.
   Final clinician captures show distinct tab count and readable explanation.
2. Initial selected moment exposed the full technical block immediately. Restored
   the reference's compact context view with an Acoustic details disclosure.
   `clinician-compact.png` and `clinician-results.png` verify both real states.
3. Source review found hidden unavailable interpretation and missing re-pairing.
   Restored status in expanded clinic/patient details and PDF, and re-pairing in
   About & privacy. Browser assertions verify visible content, not only API state.
4. PDF comparison exposed an orphaned moment heading. Keep-with-next prevents it;
   a pagination fixture then exposed a footer-only page before the appendix.
   Replacing the trailing standalone spacer with flowable spacing removed it.
   Final three-page fixture has substantive text on every page, with headings
   attached to evidence. Parameterized PDF regression cases cover both densities.
5. Cross-surface comparison found the web showing the preceding follow-up day.
   The Date serializer now preserves PostgreSQL calendar days. Parser tests and
   the final two browser scenarios verify the displayed date matches the input.

## Required fidelity surfaces

- Typography: local Manrope headings and DM Sans UI/body, correct weight hierarchy,
  25 px patient actions, readable secondary copy. Long synthetic patient names fit
  the desktop header. PDF uses searchable built-in Helvetica: an intentional
  portable report choice, not a claim of font-identical screenshot reproduction.
- Spacing/layout: white surfaces, restrained 8 px corners, separated rows and cobalt
  selected tabs. Record and History are real alternative views. Persistent phone
  navigation remains visible at 390 × 844; tablet and mobile grids do not overlap.
- Color: cobalt primary action, pale yellow difficult action, dark ink and muted
  blue-gray text. Disabled buttons differ intentionally; enabled actions preserve
  contrast. No decorative gradients or glass panels were substituted for the UI.
- Imagery: the original 3:2 glass raster is unchanged, sharp and consistently
  cropped on the landing page. The whole mockup is never used as an app screen.
- Copy: short English labels, visible pending/error states, one privacy disclosure.
  Actual evidence and unavailable interpretation remain explicit in the detail.
- Icons: a consistent Lucide family with readable text labels. Small semantic
  differences from the generated mock's icons are acceptable refinements (P3).
- Accessibility: five public routes and paired microphone-on home pass automated
  WCAG checks. Keyboard skip link, forms, tab arrow/Home navigation, re-pairing,
  reduced motion and WebKit width checks pass. No color-only or audio-only action.

## Interaction evidence and limits

Eight linked browser scenarios pass: create/pair, both PCM actions and required
answers, real DSP, search, capability denial, offline reopen/retry, PDF caching,
idempotent concurrent upload and real QR-camera-fixture revocation. Two public
accessibility/layout scenarios pass separately on the same visual implementation;
final date/control refinements pass two focused browser scenarios. Test captures
use synthetic media and do not certify physical iOS or hearing-aid routing.

The PDF retains more evidence than the small board thumbnail: method labels,
measurement availability and a technical appendix. This is intentional to preserve
the existing product contract. A sparse final method page for some report lengths
is a P3 pagination refinement. No actionable P0/P1/P2 visual finding remains.

## Completion checklist

- [x] Original art retained; fonts/colors/layout compared against selected board.
- [x] Phone, clinician, pairing, details and PDF inspected as rendered output.
- [x] Initial visual and behavior findings corrected and rechecked.
- [x] Relevant automated behavior/accessibility and pagination checks pass.
- [x] Remaining physical-device and public-release limits remain explicit.


## Deployed follow-up

The same visual is deployed at commit `f3ab5a6`. Private browser evidence passed
9/10, with the simulated-camera QR case passing in an isolated 2/2 rerun. No UI
change was made between those runs; camera-fixture intermittency remains explicit.
`.local/clear-signal/linux-first-run/` retains the first deployed screenshots/PDF
and QR failure trace; `.local/clear-signal/linux-report-1.png` through
`linux-report-3.png` show all pages of the final current-version PDF. Its heading
stays with its evidence, every page contains substantive text, and the calendar
follow-up date matches the web. The served original 3D artwork matches source bytes.
