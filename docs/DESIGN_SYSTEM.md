# Design system

Clear Signal is the owner-selected direction from 2026-09-12. A white surface,
cobalt primary action, pale yellow difficult action and dark text support the two
patient choices. On 2026-09-15 the owner requested a more understandable listening
identity and a denser directory. A cobalt ear with two sound waves replaces the
abstract glass hero. The original `docs/design/clear-signal-reference.png` remains
historical direction evidence; it is not the current logo specification.

The ear sits directly on the white page without a tinted enclosing panel.
Pairing, installation help and the patient guidance preview use white surfaces
and fine borders. The expanded clinician moment uses a narrow cobalt edge to
retain its selected state without a large blue fill. Blue and yellow remain on
the two patient actions; chart backgrounds retain their data-reading purpose.

## Implementation
- `src/app/globals.css` owns the shared tokens: ink #17212D, muted #52627A,
  cobalt #184DD8, pale blue #EDF3FF, yellow #F5DEA0 and border #DCE2EC.
- Manrope Variable headings and DM Sans Variable body/UI are locally bundled,
  pinned Fontsource packages under OFL-1.1. No third-party font requests.
- Patient actions use 25 px labels and at least 110 px height. Color always has a
  text label and Lucide icon. Microphone state and Stop remain explicit.
- Record and History are separate views of the same active patient session.
  Pending offline moments, required answers and errors remain accessible.
  About & privacy contains microphone/storage information and re-pairing.
- The clinician directory uses compact rows, a prominent full-text search field,
  collapsible labelled filters with an active count, name/date/moment-count sorting
  and 25-row pages. Profile notes provide context without expanding each row.
  Search accepts partial words and accents may be omitted. It runs in PostgreSQL;
  only sorting and pagination operate on the complete returned match set.
  Patient review opens on Moments; Profile
  holds the audiogram, aids and editor. Pairing and acoustic evidence expand on demand.
- Application headings top out at 40 px; the landing hero keeps its own scale.
  Directory identities group the avatar, readable name and fitted-ear label.
  All filters have visible labels; mobile rows label moment counts explicitly.
- Allure confirmation cards use concise control names, separate from patient
  instructions. Checkbox/radio sizing must not inherit text-input height or
  nested-fieldset sibling spacing.
- Patient recording actions precede the Home Screen offer. Install details
  expand on request and remain available through About & privacy. A moment detail
  returns to the listening space without suggesting that pairing is required again.
- Clinician AI guidance uses 16 px reading text and a separate patient-preview
  column on wider screens. Recorded relative energy uses the same percentage
  representation in the graph and the frequency review. Mobile retains one column.
- Failed directory loads show recovery actions without an empty-patient claim.
  Failed refreshes label retained rows as last-loaded results. Invalid API responses
  must be rejected rather than rendered as successful application data.
- The PDF begins with a chronological listening log and preserves actual DSP,
  model provenance, unavailable/failed interpretation and synthetic audiogram
  evidence in technical details. Report template 4 has a separate cache identity and distinguishes clinician and patient AI guidance.
- Responsive layouts preserve native form controls, visible keyboard focus,
  at least 44 px primary targets, reduced motion and higher contrast preferences.
  There is no essential animation, glass blur or audio-only feedback.
- Scientific charts remain driven by actual data. No raster clinical graphs or
  invented measurements. `design-qa.md` records visual comparison and limitations.

## Asset provenance
`public/listening-ear.webp` was generated on 2026-09-15 with the built-in ImageGen
tool, then resized/encoded to a 960-pixel WebP (103,560 bytes). The transparent
source was inspected. No model identifier is exposed by the tool. The packaged
asset is served directly, avoiding an on-demand image-optimizer dependency for
the single fixed hero. `src/components/brand-mark.tsx` and `public/icon.svg` are
original vector ear-and-sound marks; the 192/512-pixel app icons are deterministic
renders of that SVG. The original glass asset below is retained for history.

New hero prompt:
> Use case: stylized-concept / logo-brand. Create a polished premium 3D brand illustration for iHear, a serious and welcoming hearing-care listening log app. Subject: ONE unmistakable stylized human ear symbol, a simple continuous thick sculpted C-shaped outer ear contour with a short inner fold and a rounded lower lobe, paired with TWO short gentle curved sound waves to its right. The silhouette must immediately read as an ear receiving sound, NOT headphones, a letter C alone, a cochlea, rings or an abstract object. Make the ear upright, near-front view with subtle 10 degree perspective and beveled rounded edges. Material: beautiful matte cobalt blue ceramic (#184dd8), subtle satin highlights, no translucent glass. The two sound arcs use the same cobalt blue. Composition: centered single emblem, fills about 62 percent of a square canvas, all parts comfortably within frame, plenty of clean white negative space. Background: seamless very pale cool white (#f7f9fd) studio floor and backdrop, very soft realistic contact shadow beneath the upright symbol, diffuse editorial daylight. Sophisticated minimal European healthcare identity, calm and exceptionally clean. No text, no letters, no medical cross, no anatomy photograph, no gradients in the background, no decorative blobs, no other objects. This is a standalone website hero asset, NOT a screenshot, NOT a mockup, NOT a presentation sheet.

`public/listening-glass.png` was generated on 2026-09-11 using the built-in OpenAI Image Generation tool. Availability was verified by a successful generation. The tool does not expose its selected model identifier; no unverified model name is claimed. The source image is copied into the repository, not referenced from a machine-private generated-image folder.

Prompt:
> Use case: stylized-concept. Asset type: original iHear landing hero supporting artwork, landscape 3:2. Primary request: a quiet, refined sculptural composition suggesting a listening moment, two organically curved translucent glass ribbons floating near one another above a warm ivory surface, subtle sage green and pale peach light passing through frosted glass, rounded and soft, generous negative space, premium editorial art, natural soft shadows, calm daylight. No text, no lettering, no logos, no people, no ears, no medical devices, no graphs, no clinical diagram. Not a UI screenshot. Delicate luminous edges but strong visible silhouettes, restrained depth, tactile matte backdrop.

`public/icon.svg` is original code-drawn app artwork; PNG app icons are deterministic renders of it. Lucide icons retain their ISC license. No manufacturer logos or product imagery are used. Generated artwork is subject to applicable OpenAI service terms and the project's original-asset notice; no warranty of exclusive copyright or trademark rights is made.
