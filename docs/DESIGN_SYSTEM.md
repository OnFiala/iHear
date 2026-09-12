# Design system

Clear Signal is the owner-selected direction from 2026-09-12. A white surface,
cobalt primary action, pale yellow difficult action and dark text support the two
patient choices. The original three-dimensional glass illustration stays on the
landing page. The approved combined visual is `docs/design/clear-signal-reference.png`.

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
- The clinician directory uses rows. Patient review opens on Moments; Profile
  holds the audiogram, aids and editor. Pairing and acoustic evidence expand on demand.
- The PDF begins with a chronological listening log and preserves actual DSP,
  model provenance, unavailable/failed interpretation and synthetic audiogram
  evidence in technical details. Report template 3 has a separate cache identity.
- Responsive layouts preserve native form controls, visible keyboard focus,
  at least 44 px primary targets, reduced motion and higher contrast preferences.
  There is no essential animation, glass blur or audio-only feedback.
- Scientific charts remain driven by actual data. No raster clinical graphs or
  invented measurements. `design-qa.md` records visual comparison and limitations.

## Asset provenance
`public/listening-glass.png` was generated on 2026-09-11 using the built-in OpenAI Image Generation tool. Availability was verified by a successful generation. The tool does not expose its selected model identifier; no unverified model name is claimed. The source image is copied into the repository, not referenced from a machine-private generated-image folder.

Prompt:
> Use case: stylized-concept. Asset type: original iHear landing hero supporting artwork, landscape 3:2. Primary request: a quiet, refined sculptural composition suggesting a listening moment, two organically curved translucent glass ribbons floating near one another above a warm ivory surface, subtle sage green and pale peach light passing through frosted glass, rounded and soft, generous negative space, premium editorial art, natural soft shadows, calm daylight. No text, no lettering, no logos, no people, no ears, no medical devices, no graphs, no clinical diagram. Not a UI screenshot. Delicate luminous edges but strong visible silhouettes, restrained depth, tactile matte backdrop.

`public/icon.svg` is original code-drawn app artwork; PNG app icons are deterministic renders of it. Lucide icons retain their ISC license. No manufacturer logos or product imagery are used. Generated artwork is subject to applicable OpenAI service terms and the project's original-asset notice; no warranty of exclusive copyright or trademark rights is made.
