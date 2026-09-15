"use client";
import Link from "next/link";
import type { ReactNode } from "react";
import {
  AudioLines,
  Check,
  CircleAlert,
  Clock3,
  LoaderCircle,
} from "lucide-react";
import type { Analysis, ListeningEvent, ProfileInput } from "@/lib/types";
import { dateLabel } from "@/lib/client/api";
import { BrandMark } from "./brand-mark";
import {
  digitalLevelHeight,
  modelStatus,
  qualityFlagLabel,
} from "@/lib/analysis";
export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="iHear home">
      <BrandMark /><span>iHear</span>
    </Link>
  );
}
export function Header({ patient = false, clinic = false, actions }: {
  patient?: boolean;
  clinic?: boolean;
  actions?: ReactNode;
}) {
  return (
    <header className={`site-header${patient ? " patient-header" : clinic ? " clinic-header" : ""}`}>
      <Brand />
      {actions !== false && <nav aria-label="Main navigation">
        {actions ?? (patient ? (
          <Link href="/app/pair" className="quiet-link">
            Pair profile
          </Link>
        ) : clinic ? (
          <>
            <Link href="/clinic" className="quiet-link">Patients</Link>
            <Link href="/app" className="quiet-link">Patient app</Link>
          </>
        ) : (
          <>
            <Link href="/app" className="quiet-link">
              Patient app
            </Link>
            <Link href="/clinic" className="quiet-link">
              Clinician demo
            </Link>
          </>
        ))}
      </nav>}
    </header>
  );
}
export function Footer() {
  return (
    <footer className="site-footer">
      <span>iHear</span>
      <span>Illustrative demo · Clinical interpretation belongs to your clinician.</span>
    </footer>
  );
}
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="notice error" role="alert">
      <CircleAlert size={20} />
      <span>{message}</span>
    </div>
  );
}
export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={24} />
      {label}
    </div>
  );
}
export function Status({ value }: { value: string }) {
  const labels: Record<string, string> = {
    ready: "Analysed",
    processing: "Processing",
    uploading: "Uploading",
    failed: "Failed",
    queued: "Queued",
    held_budget: "Budget paused",
    held_ambiguity: "Interpretation paused",
  };
  const clean =
    labels[value] || value.replaceAll("_", " ").replaceAll("-", " ");
  return (
    <span
      className={
        "status " +
        (value === "ready" ? "ready" : value === "failed" ? "failed" : "")
      }
    >
      {value === "ready" ? <Check size={13} /> : <Clock3 size={13} />} {clean}
    </span>
  );
}
export function EventList({
  events,
  patient = false,
}: {
  events: ListeningEvent[];
  patient?: boolean;
}) {
  return (
    <div className="event-list">
      {events.map((event) => (
        <Link
          className="event-row"
          key={event.id}
          href={patient ? `/app/events/${event.id}` : `#event-${event.id}`}
        >
          <span className={"moment-icon " + event.kind}>
            {event.kind === "understood" ? (
              <Check size={22} />
            ) : (
              <AudioLines size={22} />
            )}
          </span>
          <span className="event-description">
            <strong>
              {event.kind === "understood"
                ? "I understand"
                : "I don’t understand"}
            </strong>
            <span>
              {dateLabel(event.capturedAt)}
              {event.difficulty ? ` · ${event.difficulty}` : ""}
            </span>
          </span>
          <Status value={event.status} />
        </Link>
      ))}
    </div>
  );
}
export function Audiogram({ data }: { data: ProfileInput["audiogram"] }) {
  const y = (db: number) => 35 + ((db + 10) / 130) * 170;
  const x = (i: number) => 60 + i * 62;
  return (
    <figure className="chart">
      <svg
        viewBox="0 0 420 270"
        role="img"
        aria-label="Clinician-entered synthetic audiogram. Left ear shown with crosses, right ear with circles. Hearing level in dB HL."
      >
        <text x="12" y="16" className="axis-label">
          Hearing level (dB HL)
        </text>
        {[-10, 20, 50, 80, 110].map((db) => (
          <g key={db}>
            <line
              x1="48"
              x2="390"
              y1={y(db)}
              y2={y(db)}
              className="grid-line"
            />
            <text x="38" y={y(db) + 4} textAnchor="end" className="axis-label">
              {db}
            </text>
          </g>
        ))}
        {data.frequencies.map((hz, i) => (
          <text
            key={hz}
            x={x(i)}
            y="232"
            textAnchor="middle"
            className="axis-label"
          >
            {hz >= 1000 ? hz / 1000 + "k" : hz}
          </text>
        ))}
        <polyline
          fill="none"
          stroke="#35657e"
          strokeWidth="2"
          points={data.left.map((db, i) => `${x(i)},${y(db)}`).join(" ")}
        />
        <polyline
          fill="none"
          stroke="#99533d"
          strokeWidth="2"
          points={data.right.map((db, i) => `${x(i)},${y(db)}`).join(" ")}
        />
        {data.left.map((db, i) => (
          <path
            key={"l" + i}
            d={`M${x(i) - 4},${y(db) - 4}l8,8m-8,0l8,-8`}
            stroke="#35657e"
            strokeWidth="2"
          />
        ))}
        {data.right.map((db, i) => (
          <circle
            key={"r" + i}
            cx={x(i)}
            cy={y(db)}
            r="4"
            fill="var(--surface-solid)"
            stroke="#99533d"
            strokeWidth="2"
          />
        ))}
        <text x="150" y="257" className="axis-label">
          Frequency (Hz)
        </text>
      </svg>
      <figcaption>
        <span>× Left ear</span>
        <span>○ Right ear</span>
        <span>Clinician-entered demo data</span>
      </figcaption>
    </figure>
  );
}
export function AcousticResult({ analysis, reviewBandIndices = [] }: { analysis: Analysis; reviewBandIndices?: number[] }) {
  const levelTimeline = analysis.level_timeline;
  const speech = analysis.speech_activity || { status: "not_stored" };
  const categories = analysis.acoustic_categories || { status: "not_stored" };
  return (
    <div className="acoustic-result">
      <div className="acoustic-result-heading acoustic-heading">
        <div>
          <h3>Recording evidence</h3>
          <p className="caption">
            Measurements from the saved phone waveform. dBFS is relative to the
            digital recording limit; it does not measure room loudness or hearing level.
          </p>
        </div>
      </div>
      <div className="metric-grid acoustic-metrics">
        <div>
          <span>Sample duration</span>
          <strong>
            {analysis.duration_seconds.toFixed(1)} <small>s</small>
          </strong>
        </div>
        <div>
          <span>Native sample rate</span>
          <strong>
            {(analysis.sample_rate / 1000).toFixed(1)} <small>kHz</small>
          </strong>
        </div>
        <div>
          <span>Digital RMS level</span>
          <strong>
            {analysis.rms_dbfs === null
              ? "No digital signal"
              : analysis.rms_dbfs.toFixed(1)}{" "}
            <small>{analysis.rms_dbfs !== null ? "dBFS" : ""}</small>
          </strong>
        </div>
        <div>
          <span>Digital peak level</span>
          <strong>
            {typeof analysis.peak_dbfs === "number"
              ? analysis.peak_dbfs.toFixed(1)
              : "Not stored"}{" "}
            <small>{typeof analysis.peak_dbfs === "number" ? "dBFS" : ""}</small>
          </strong>
        </div>
        <div>
          <span>Clipped samples</span>
          <strong>
            {typeof analysis.clipping_fraction === "number"
              ? (analysis.clipping_fraction * 100).toFixed(2)
              : "Not stored"}{" "}
            <small>{typeof analysis.clipping_fraction === "number" ? "%" : ""}</small>
          </strong>
        </div>
        <div>
          <span>Spectral centroid</span>
          <strong>
            {typeof analysis.spectral_centroid_hz === "number"
              ? analysis.spectral_centroid_hz.toFixed(0)
              : "Not stored"}{" "}
            <small>{typeof analysis.spectral_centroid_hz === "number" ? "Hz" : ""}</small>
          </strong>
        </div>
      </div>
      <h4>Digital level over time</h4>
      {levelTimeline?.length ? (
        <div
          className="acoustic-level-timeline"
          role="list"
          aria-label="One-second digital RMS levels relative to full scale"
        >
          {levelTimeline.map((window) => (
            <div
              className="acoustic-level-window"
              key={window.start_seconds}
              role="listitem"
              aria-label={`${window.start_seconds.toFixed(1)} to ${window.end_seconds.toFixed(1)} seconds: RMS ${
                window.rms_dbfs === null ? "not measurable" : `${window.rms_dbfs.toFixed(1)} dBFS`
              }, peak ${
                window.peak_dbfs === null ? "not measurable" : `${window.peak_dbfs.toFixed(1)} dBFS`
              }, ${(window.clipping_fraction * 100).toFixed(2)} percent clipped samples`}
            >
              <span className="acoustic-level-value">
                {window.rms_dbfs === null ? "—" : window.rms_dbfs.toFixed(1)}
              </span>
              <span className="acoustic-level-track" aria-hidden="true">
                <span
                  className="acoustic-level-fill"
                  style={{ height: `${digitalLevelHeight(window.rms_dbfs)}%` }}
                />
              </span>
              <small>{window.start_seconds.toFixed(0)}s</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="caption">Per-second levels were not stored for this earlier analysis.</p>
      )}
      <h4>Relative spectral energy</h4>
      <p className="caption">
        Share of recorded energy by frequency range (Hz). Not calibrated sound pressure or hearing level.
      </p>
      <div
        className="band-chart"
        role="img"
        aria-label="Relative frequency-band energy in the recording"
      >
        {(analysis.bands || []).map((b, index) => (
          <div key={b.low_hz} className={`band${reviewBandIndices.includes(index) ? " band--review" : ""}`}>
            <span className="band-value">
              {(b.relative_energy * 100).toFixed(1)}%
            </span>
            <div className="band-track">
              <span
                style={{ height: Math.max(1, b.relative_energy * 100) + "%" }}
              />
            </div>
            <span className="band-label">
              {b.low_hz >= 1000 ? b.low_hz / 1000 + "k" : b.low_hz}–
              {b.high_hz >= 1000 ? b.high_hz / 1000 + "k" : b.high_hz}
            </span>
            {reviewBandIndices.includes(index) && <span className="band-review-label">AI review</span>}
          </div>
        ))}
      </div>
      {reviewBandIndices.some((index) => Number.isInteger(index) && analysis.bands[index]) && (
        <p className="caption">Marked ranges have an AI review note below. Bar heights remain the measured relative energy.</p>
      )}
      {analysis.quality_flags?.length > 0 && (
        <ul className="notice acoustic-quality-notes">
          {analysis.quality_flags.map((flag) => (
            <li key={flag}>{qualityFlagLabel(flag)}</li>
          ))}
        </ul>
      )}
      <div className="model-results acoustic-model-grid">
        <div>
          <h4>Silero speech estimate</h4>
          <p>
            {speech.status === "ready" && typeof speech.fraction === "number"
              ? `${(speech.fraction * 100).toFixed(0)}% of ${speech.aggregation === "valid-duration-weighted" ? "analysed duration" : "frames"} at or above ${(
                  speech.threshold ?? 0.5
                ).toFixed(2)}`
              : modelStatus(speech.status)}
          </p>
          <span className="caption">
            {typeof speech.mean_probability === "number"
              ? `${speech.aggregation === "valid-duration-weighted" ? "Duration-weighted mean" : "Mean frame"} score ${speech.mean_probability.toFixed(3)}. `
              : ""}
            Speech detection estimate, not a transcript or intelligibility measure.
          </span>
        </div>
        <div>
          <h4>YAMNet audio event scores</h4>
          {categories.categories?.length ? (
            <div className="acoustic-category-list">
              {categories.categories.map((category) => (
                <div className="acoustic-category-row" key={category.label}>
                  <span>{category.label}</span>
                  <span className="acoustic-score-track" aria-hidden="true">
                    <span
                      className="acoustic-score-fill"
                      style={{ width: `${Math.max(0, Math.min(100, category.score * 100))}%` }}
                    />
                  </span>
                  <strong>{category.score.toFixed(3)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p>{modelStatus(categories.status)}</p>
          )}
          <span className="caption">
            Scores are mean model outputs across frames, not probabilities that a sound
            was present. A “Silence” label does not establish that the room was quiet.
          </span>
        </div>
      </div>
      <details className="acoustic-model-windows">
        <summary>Temporal model detail</summary>
        {speech.windows?.length ? (
          <section>
            <h4>Speech estimate by second</h4>
            <div className="acoustic-window-grid">
              {speech.windows.map((window) => (
                <div className="acoustic-model-window" key={window.start_seconds}>
                  <small>{window.start_seconds.toFixed(1)}–{window.end_seconds.toFixed(1)}s</small>
                  <strong>{(window.active_fraction * 100).toFixed(0)}% above threshold</strong>
                  <span>mean score {window.mean_probability.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <p className="caption">Speech timing was not stored for this earlier analysis.</p>
        )}
        {categories.windows?.length ? (
          <section>
            <h4>Top YAMNet label by model frame</h4>
            <div className="acoustic-window-grid">
              {categories.windows.map((window) => {
                const top = window.categories[0];
                return (
                  <div className="acoustic-model-window" key={window.start_seconds}>
                    <small>{window.start_seconds.toFixed(2)}–{window.end_seconds.toFixed(2)}s</small>
                    <strong>{top?.label || "No label stored"}</strong>
                    {top && <span>score {top.score.toFixed(3)}</span>}
                  </div>
                );
              })}
            </div>
            <p className="caption">
              Frames overlap. Each label is the highest model score in that frame and is
              not a certain identification.
            </p>
          </section>
        ) : (
          <p className="caption">YAMNet frame detail was not stored for this earlier analysis.</p>
        )}
      </details>
    </div>
  );
}
