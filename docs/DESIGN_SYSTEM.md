# Design system

A quiet, soft glass interface supports two unmistakable patient actions. Warm ivory background, sage positive action, peach difficult action, dark green text, generously rounded controls. Text labels and icons always accompany color.

## Implementation
- CSS lives in src/app/globals.css. Glass uses translucent surfaces, a restrained border, soft depth and backdrop blur.
- Older-adult patient controls use 25-27 px action text, approximately 163-174 px action cards, and explicit microphone state. Native form controls and visible keyboard focus remain usable.
- Responsive clinician cards, one-column phone flows, no essential animation or audio cues.
- Short transitions; prefers-reduced-motion disables animation. Opaque fallback for unsupported blur, reduced transparency and higher contrast preferences.
- Manrope Variable and DM Sans Variable are locally bundled, OFL-1.1 fonts via pinned Fontsource packages. No third-party font requests.
- Actual charts are SVG/CSS driven by synthetic audiogram values and real DSP results. No raster clinical graphs.

## Asset provenance
`public/listening-glass.png` was generated on 2026-09-11 using the built-in OpenAI Image Generation tool. Availability was verified by a successful generation. The tool does not expose its selected model identifier; no unverified model name is claimed. The source image is copied into the repository, not referenced from a machine-private generated-image folder.

Prompt:
> Use case: stylized-concept. Asset type: original iHear landing hero supporting artwork, landscape 3:2. Primary request: a quiet, refined sculptural composition suggesting a listening moment, two organically curved translucent glass ribbons floating near one another above a warm ivory surface, subtle sage green and pale peach light passing through frosted glass, rounded and soft, generous negative space, premium editorial art, natural soft shadows, calm daylight. No text, no lettering, no logos, no people, no ears, no medical devices, no graphs, no clinical diagram. Not a UI screenshot. Delicate luminous edges but strong visible silhouettes, restrained depth, tactile matte backdrop.

`public/icon.svg` is original code-drawn app artwork; PNG app icons are deterministic renders of it. Lucide icons retain their ISC license. No manufacturer logos or product imagery are used. Generated artwork is subject to applicable OpenAI service terms and the project's original-asset notice; no warranty of exclusive copyright or trademark rights is made.
