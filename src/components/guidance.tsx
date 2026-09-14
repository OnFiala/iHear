import type { ListeningEvent, ProfileInput } from "@/lib/types";
import {
  actionsForProfile,
  supportsAllureActions,
  sameAppConfiguration,
  type AllureActionId,
} from "@/lib/device-guidance";
import { tips } from "@/lib/types";

type GuidanceProps = {
  event: ListeningEvent;
  aids?: ProfileInput["aids"];
};

function readyResult(event: ListeningEvent) {
  return event.status === "ready" && event.interpretation?.status === "ready"
    ? event.interpretation.result
    : null;
}

function actionState(event: ListeningEvent, aids?: ProfileInput["aids"]) {
  const result = readyResult(event);
  const snapshotAids = event.profileSnapshot.aids;
  const currentAids = aids ?? event.currentAids;
  if (!currentAids) return { actions: [], configurationChanged: true };
  const configurationChanged = !sameAppConfiguration(snapshotAids, currentAids);
  if (
    !result ||
    configurationChanged ||
    !supportsAllureActions(snapshotAids) ||
    !supportsAllureActions(currentAids)
  ) return { actions: [], configurationChanged };
  const requested = new Set(result.device_action_ids ?? []);
  const currentlyAllowed = new Set(actionsForProfile(currentAids).map(({ id }) => id));
  return {
    actions: actionsForProfile(snapshotAids).filter(
      (action) => requested.has(action.id as AllureActionId) && currentlyAllowed.has(action.id),
    ),
    configurationChanged,
  };
}

function frequencyRange(event: ListeningEvent, index: number) {
  const band = event.analysis?.bands[index];
  if (!band) return null;
  return {
    label: `${band.low_hz.toLocaleString("en")}–${band.high_hz.toLocaleString("en")} Hz`,
    energy: band.relative_energy,
  };
}

function evidenceLabel(event: ListeningEvent, reference: string): string {
  const labels: Record<string, string> = {
    reported_event: "Patient report",
    audiogram: "Audiogram at recording time",
    clinician_note: "Profile note",
    phone_audio: "Phone recording measurements",
    speech_estimate: "Speech activity estimate",
    sound_categories: "Sound category estimates",
    prior_events: "Earlier listening moments",
  };
  if (/^band:\d+$/.test(reference)) {
    const range = frequencyRange(event, Number(reference.slice(5)));
    return range ? `${range.label} recorded band` : "Recorded band unavailable";
  }
  return labels[reference] ?? "Evidence unavailable";
}

export function ClinicianGuidance({ event, aids }: GuidanceProps) {
  const result = readyResult(event);
  if (!result) return null;
  const { actions, configurationChanged } = actionState(event, aids);
  return (
    <section className="guidance-panel clinic-guidance" aria-label="AI guidance">
      <div className="guidance-heading">
        <div>
          <span className="eyebrow">AI interpretation</span>
          <h3>Clinical review guidance</h3>
        </div>
        <span className="guidance-status">Ready</span>
      </div>
      <p className="guidance-boundary">
        AI-generated discussion support. It combines the recorded acoustic
        analysis, patient report and stored profile snapshot; it does not make
        a fitting change or replace clinical judgement.
      </p>
      {result.summary && <p className="guidance-summary">{result.summary}</p>}
      <div className="guidance-columns">
        <div className="guidance-clinician-content">
          {!!result.observations?.length && (
            <section className="guidance-section">
              <h4>AI observations</h4>
              <ul>{result.observations.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </section>
          )}
          {!!result.recommendations?.length && (
            <section className="guidance-section">
              <h4>Recommendations to review</h4>
              <ul>{result.recommendations.map((item, index) => (
                <li key={index}>
                  <p>{item.text}</p>
                  <p className="caption">Based on: {item.evidence_refs.map((reference) => evidenceLabel(event, reference)).join(" · ")}</p>
                </li>
              ))}</ul>
            </section>
          )}
          {!!result.frequency_notes?.length && (
            <section className="guidance-section">
              <h4>Frequency-range review</h4>
              <div className="guidance-frequency-list">
                {result.frequency_notes.map((note, index) => {
                  const range = Number.isInteger(note.band_index) ? frequencyRange(event, note.band_index) : null;
                  if (!range) return null;
                  return (
                    <article className="guidance-frequency" key={`${note.band_index}-${index}`}>
                      <strong>{range?.label ?? `Band ${note.band_index + 1}`}</strong>
                      {range && (
                        <span>
                          Recorded measurement: {(range.energy * 100).toFixed(1)}% of relative spectral energy
                        </span>
                      )}
                      <p><b>AI note:</b> {note.explanation}</p>
                      <p><b>Review question:</b> {note.review_question}</p>
                    </article>
                  );
                })}
              </div>
            </section>
          )}
        </div>
        <div className="guidance-patient-content">
          {(result.patient_summary || actions.length > 0) && (
            <section className="guidance-preview">
              <h4>Patient view preview</h4>
              {result.patient_summary && <p>{result.patient_summary}</p>}
              {actions.map((action) => (
                <div className="guidance-action-preview" key={action.id}>
                  <strong>{action.title}</strong>
                  <span>{action.instruction}</span>
                </div>
              ))}
            </section>
          )}
          {configurationChanged && !!result.device_action_ids?.length && (
            <p className="guidance-config-changed">
              App configuration has changed since this moment. Confirm the controls
              before trying these suggestions.
            </p>
          )}
        </div>
      </div>
      {!!result.limitations?.length && (
        <section className="guidance-limitations">
          <h4>Limits and missing evidence</h4>
          {result.limitations.map((item, index) => <p key={index}>{item}</p>)}
        </section>
      )}
      {(event.interpretation?.promptVersion || event.interpretation?.model) && (
        <p className="caption guidance-provenance">
          {event.interpretation.promptVersion && `Prompt ${event.interpretation.promptVersion}`}
          {event.interpretation.promptVersion && event.interpretation.model && " · "}
          {event.interpretation.model && `Model ${event.interpretation.model}`}
        </p>
      )}
    </section>
  );
}

export function PatientGuidance({ event, aids }: GuidanceProps) {
  const result = readyResult(event);
  if (!result) return null;
  const { actions, configurationChanged } = actionState(event, aids);
  const gentleTips = (result.tip_ids ?? []).filter((id) => tips[id]).slice(0, 1);
  if (!result.patient_summary && !gentleTips.length && !actions.length) return null;
  return (
    <section className="patient-guidance" aria-label="Your guidance">
      {result.patient_summary && (
        <section className="glass patient-guidance-summary">
          <span className="eyebrow">AI listening note</span>
          <h2>What may help next</h2>
          <p>{result.patient_summary}</p>
          <p className="caption">Generated from this listening moment to support a conversation with your audiologist.</p>
        </section>
      )}
      {gentleTips.map((id) => (
        <section className="glass tip-card" key={id}>
          <span className="eyebrow">A gentle suggestion</span>
          <p>{tips[id]}</p>
        </section>
      ))}
      {!!actions.length && (
        <section className="patient-device-actions">
          <h2>Controls confirmed in your Allure app</h2>
          <p className="caption">
            These are controls your clinician confirmed for this profile. Choose
            any change yourself in the Widex Allure app.
          </p>
          {actions.map((action) => (
            <article className="glass patient-device-action" key={action.id}>
              <h3>{action.title}</h3>
              <p>{action.instruction}</p>
              <a className="caption" href={action.source} target="_blank" rel="noreferrer">
                Widex app guide
              </a>
            </article>
          ))}
        </section>
      )}
      {configurationChanged && !!result.device_action_ids?.length && (
        <p className="caption patient-guidance-config-changed">
          App configuration has changed since this moment. Confirm the controls
          before trying these suggestions.
        </p>
      )}
    </section>
  );
}
