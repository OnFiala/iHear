import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ClinicianGuidance, PatientGuidance } from "../src/components/guidance";
import type { ListeningEvent, ProfileInput } from "../src/lib/types";

const aids: ProfileInput["aids"] = {
  side: "bilateral",
  left: { model: "Widex ALLURE BTE R D", tier: "220" },
  right: { model: "Widex ALLURE BTE R D", tier: "220" },
  app: {
    name: "Widex Allure",
    version: "1.2.3",
    confirmedActions: ["allure_equalizer"],
  },
};

function event(overrides: Partial<ListeningEvent> = {}): ListeningEvent {
  return {
    id: "event-1",
    patientId: "patient-1",
    kind: "difficult",
    difficulty: "Several people talking",
    environment: "Background conversation",
    capturedAt: "2026-09-13T10:00:00Z",
    createdAt: "2026-09-13T10:00:00Z",
    status: "ready",
    capture: {},
    currentAids: aids,
    profileSnapshot: {
      displayName: "Alex Morgan",
      audiogram: { frequencies: [500, 1000], left: [30, 35], right: [30, 35] },
      aids,
      followUpDate: "2026-09-28",
      note: "",
      timezone: "Europe/Prague",
    },
    analysis: {
      duration_seconds: 10,
      sample_rate: 48000,
      rms_dbfs: -30,
      peak_dbfs: -12,
      clipping_fraction: 0,
      silent: false,
      quality_flags: [],
      bands: [
        { low_hz: 250, high_hz: 500, relative_energy: 0.2 },
        { low_hz: 500, high_hz: 1000, relative_energy: 0.67 },
      ],
      spectral_centroid_hz: 1200,
      speech_activity: { status: "unavailable" },
      acoustic_categories: { status: "unavailable" },
    },
    interpretation: {
      status: "ready",
      promptVersion: "v2",
      model: "example-model",
      result: {
        summary: "The recording may be worth discussing.",
        observations: ["Observation for the clinician."],
        recommendations: [{ text: "Review this at the next appointment.", evidence_refs: ["reported_event", "band:1"] }],
        frequency_notes: [
          {
            band_index: 1,
            explanation: "AI explanation.",
            review_question: "What changed?",
          },
        ],
        patient_summary: "Try a quieter position when practical.",
        tip_ids: ["face_speaker"],
        device_action_ids: ["allure_equalizer"],
        limitations: ["No calibrated at-ear output was available."],
      },
    },
    ...overrides,
  };
}

test("patient guidance exposes only the concise summary, safe tip, and confirmed control", () => {
  const html = renderToStaticMarkup(createElement(PatientGuidance, { event: event() }));
  assert.match(html, /Try a quieter position/);
  assert.match(html, /equalizer/i);
  assert.match(html, /face the person/);
  assert.doesNotMatch(html, /Review this at the next appointment/);
  assert.doesNotMatch(html, /Observation for the clinician/);
});

test("guidance does not render before a ready interpretation", () => {
  const html = renderToStaticMarkup(
    createElement(PatientGuidance, {
      event: event({ interpretation: { status: "unavailable", result: null } }),
    }),
  );
  assert.equal(html, "");
});

test("clinician guidance links the AI frequency note to the measured band", () => {
  const html = renderToStaticMarkup(createElement(ClinicianGuidance, { event: event(), aids }));
  assert.match(html, /500–1,000 Hz/);
  assert.match(html, /relative energy 0.67/);
  assert.match(html, /AI explanation/);
  assert.match(html, /Review this at the next appointment/);
});

test("a changed app configuration suppresses historic control cards", () => {
  const currentAids: ProfileInput["aids"] = {
    ...aids,
    app: { ...aids.app!, version: "2.0" },
  };
  const html = renderToStaticMarkup(
    createElement(ClinicianGuidance, { event: event(), aids: currentAids }),
  );
  assert.doesNotMatch(html, /Controls confirmed in your Allure app/);
  assert.match(html, /App configuration has changed since this moment/);
});
