"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronDown,
  ClipboardList,
  Download,
  Info,
  Link2,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import QRCode from "qrcode";
import { api, dateLabel } from "@/lib/client/api";
import type {
  Patient,
  ProfileInput,
  ListeningEvent,
  Pairing,
} from "@/lib/types";
import { difficulties, frequencies } from "@/lib/types";
import {
  Header,
  Footer,
  ErrorBox,
  Loading,
  Status,
  Audiogram,
  AcousticResult,
} from "./shared";
const sample: ProfileInput = {
  displayName: "",
  audiogram: {
    frequencies,
    left: [25, 30, 40, 45, 55, 60],
    right: [20, 25, 35, 40, 50, 55],
  },
  aids: {
    side: "bilateral",
    left: { model: "Widex ALLURE BTE R D", tier: "220" },
    right: { model: "Widex ALLURE BTE R D", tier: "220" },
  },
  followUpDate: "2026-09-28",
  note: "",
  timezone: "Europe/Prague",
};
export function ClinicDirectory() {
  const [patients, setPatients] = useState<Patient[]>([]),
    [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [difficulty, setDifficulty] = useState(""),
    [followUp, setFollowUp] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [version, setVersion] = useState(0);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(
      async () => {
        try {
          await api("/api/session");
          const result = await api<{ patients: Patient[] }>(
            `/api/patients?${new URLSearchParams({ q, status, difficulty, followUp })}`,
          );
          if (active) {
            setPatients(result.patients);
            setError("");
          }
        } catch (e) {
          if (active) setError((e as Error).message);
        } finally {
          if (active) setLoading(false);
        }
      },
      q ? 250 : 0,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [q, status, difficulty, followUp, version]);
  useEffect(() => {
    const id = setInterval(() => setVersion((v) => v + 1), 8000);
    return () => clearInterval(id);
  }, []);
  return (
    <>
      <Header clinic />
      <main
        tabIndex={-1}
        id="main"
        className="clinic-main clinic-directory page-width"
      >
        <div className="page-title-row clinic-directory-header">
          <h1>Patients</h1>
          <Link
            href="/clinic/patients/new"
            className="button"
          >
            <Plus size={19} />
            New patient
          </Link>
        </div>
        <p className="clinic-demo-note">
          Illustrative demo. Use synthetic patient information only.
        </p>
        <div className="directory-toolbar clinic-directory-toolbar">
          <label className="search-box">
            <Search size={20} />
            <input
              type="search"
              placeholder="Search names, notes or listening moments"
              aria-label="Search patients and event content"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <div className="filter-row">
            <SlidersHorizontal size={18} aria-hidden />
            <label>
              <span className="sr-only">Result status</span>
              <select
                aria-label="Result status"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">Any result</option>
                <option value="ready">Ready</option>
                <option value="queued">Queued</option>
                <option value="analysing">Analysing</option>
                <option value="failed">Failed</option>
              </select>
            </label>
            <label>
              <span className="sr-only">Reported difficulty</span>
              <select
                aria-label="Reported difficulty"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
              >
                <option value="">Any difficulty</option>
                {difficulties.map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
            <label className="date-filter">
              <span>Follow-up by</span>
              <input
                type="date"
                aria-label="Follow-up by"
                value={followUp}
                onChange={(e) => setFollowUp(e.target.value)}
              />
            </label>
          </div>
        </div>
        {error && <ErrorBox message={error} />}
        <div className="list-heading clinic-list-heading">
          <span>
            {patients.length} {patients.length === 1 ? "patient" : "patients"}
          </span>
          <span aria-live="polite">Updates automatically</span>
        </div>
        {loading ? (
          <Loading label="Loading patients…" />
        ) : patients.length === 0 ? (
          <section className="empty-state compact clinic-empty-state">
            <h2>
              {q || status || difficulty || followUp
                ? "No matching patients"
                : "No patients yet"}
            </h2>
            <p>
              {q || status || difficulty || followUp
                ? "Try another search or clear your filters."
                : "Create a synthetic patient profile to begin."}
            </p>
            <Link
              className="button"
              href="/clinic/patients/new"
            >
              <Plus size={18} />
              New patient
            </Link>
          </section>
        ) : (
          <div className="patient-grid clinic-patient-list">
            <div className="clinic-patient-columns" aria-hidden="true">
              <span>Patient</span>
              <span>Follow-up</span>
              <span>Moments</span>
              <span>Status</span>
              <span />
            </div>
            {patients.map((p, i) => (
              <Link
                className="patient-card clinic-patient-row"
                href={"/clinic/patients/" + p.id}
                key={p.id}
              >
                <span className="clinic-patient-identity">
                  <span className={"avatar " + (i % 2 ? "peach" : "sage")}>
                    {p.displayName
                      .split(" ")
                      .map((n) => n[0])
                      .slice(0, 2)
                      .join("")}
                  </span>
                  <span>
                    <strong>{p.displayName}</strong>
                    <small>
                      <AudioAid side={p.aids.side} />
                      {p.aids.side === "bilateral"
                        ? "Both ears"
                        : p.aids.side === "left"
                          ? "Left ear"
                          : "Right ear"}
                    </small>
                  </span>
                </span>
                <span className="clinic-patient-followup">
                  <CalendarDays size={15} />
                  {dateLabel(p.followUpDate)}
                </span>
                <span className="clinic-patient-count">
                  {p.eventCount || 0}
                </span>
                <span className="clinic-patient-status">
                  {p.latestStatus ? (
                    <Status value={p.latestStatus} />
                  ) : (
                    <span className="caption">No moments</span>
                  )}
                </span>
                <ArrowRight
                  className="clinic-patient-arrow"
                  size={19}
                  aria-hidden="true"
                />
              </Link>
            ))}
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}
function AudioAid({ side }: { side: string }) {
  return (
    <span className="ear-mark" aria-hidden>
      {side === "bilateral" ? "L + R" : side === "left" ? "L" : "R"}
    </span>
  );
}
export function PatientForm({
  initial,
  onSaved,
}: {
  initial?: Patient;
  onSaved?: (p: Patient) => void;
}) {
  const [value, setValue] = useState<ProfileInput>(initial || sample),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  function field<K extends keyof ProfileInput>(name: K, data: ProfileInput[K]) {
    setValue((v) => ({ ...v, [name]: data }));
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/api/session");
      const result = await api<{ patient: Patient }>(
        initial ? "/api/patients/" + initial.id : "/api/patients",
        { method: initial ? "PATCH" : "POST", body: JSON.stringify(value) },
      );
      if (onSaved) onSaved(result.patient);
      else window.location.href = "/clinic/patients/" + result.patient.id;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <form className="patient-form clinic-form" onSubmit={submit}>
      <section className="glass form-section clinic-form-section">
        <h2>Patient</h2>
        <div className="form-grid">
          <label>
            Name
            <input
              required
              maxLength={80}
              autoComplete="off"
              placeholder="Alex Morgan"
              value={value.displayName}
              onChange={(e) => field("displayName", e.target.value)}
            />
            <span className="caption">Use a synthetic name.</span>
          </label>
          <label>
            Follow-up date
            <input
              type="date"
              required
              value={value.followUpDate}
              onChange={(e) => field("followUpDate", e.target.value)}
            />
          </label>
          <label className="wide">
            Note <span className="optional">optional</span>
            <textarea
              maxLength={500}
              rows={2}
              placeholder="Context to review at the next visit"
              value={value.note}
              onChange={(e) => field("note", e.target.value)}
            />
          </label>
          <label>
            Clinic timezone
            <select
              value={value.timezone}
              onChange={(e) => field("timezone", e.target.value)}
            >
              <option>Europe/Prague</option>
              <option>Europe/London</option>
              <option>America/New_York</option>
              <option>UTC</option>
            </select>
          </label>
        </div>
      </section>
      <section className="glass form-section clinic-form-section">
        <h2>Audiogram</h2>
        <p className="caption">
          Synthetic clinician-entered thresholds in dB HL. These values are not
          a fitting recommendation.
        </p>
        <div className="audiogram-form-layout">
          <div className="audiogram-inputs">
            <table>
              <thead>
                <tr>
                  <th scope="col">Hz</th>
                  <th scope="col">× Left ear</th>
                  <th scope="col">○ Right ear</th>
                </tr>
              </thead>
              <tbody>
                {frequencies.map((hz, i) => (
                  <tr key={hz}>
                    <th scope="row">{hz.toLocaleString("en")}</th>
                    {(["left", "right"] as const).map((ear) => (
                      <td key={ear}>
                        <input
                          aria-label={`${ear === "left" ? "Left" : "Right"} ear ${hz} Hz dB HL`}
                          type="number"
                          required
                          min={-10}
                          max={120}
                          step={5}
                          value={value.audiogram[ear][i]}
                          onChange={(e) =>
                            field("audiogram", {
                              ...value.audiogram,
                              [ear]: value.audiogram[ear].map((v, j) =>
                                i === j ? Number(e.target.value) : v,
                              ),
                            })
                          }
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Audiogram data={value.audiogram} />
        </div>
      </section>
      <section className="glass form-section clinic-form-section">
        <h2>Hearing aids</h2>
        <div className="form-grid">
          <label className="wide">
            Fitted ears
            <select
              value={value.aids.side}
              onChange={(e) => {
                const side = e.target.value as ProfileInput["aids"]["side"];
                field("aids", {
                  side,
                  left:
                    side === "right"
                      ? null
                      : value.aids.left || {
                          model: "Widex ALLURE BTE R D",
                          tier: "220",
                        },
                  right:
                    side === "left"
                      ? null
                      : value.aids.right || {
                          model: "Widex ALLURE BTE R D",
                          tier: "220",
                        },
                });
              }}
            >
              <option value="bilateral">Both ears</option>
              <option value="left">Left ear</option>
              <option value="right">Right ear</option>
            </select>
          </label>
          {(["left", "right"] as const).map(
            (ear) =>
              value.aids[ear] && (
                <fieldset key={ear}>
                  <legend>
                    {ear === "left" ? "Left" : "Right"} hearing aid
                  </legend>
                  <label>
                    Model
                    <select value={value.aids[ear]!.model} onChange={() => {}}>
                      <option>Widex ALLURE BTE R D</option>
                    </select>
                  </label>
                  <label>
                    Tier
                    <select
                      value={value.aids[ear]!.tier}
                      onChange={(e) =>
                        field("aids", {
                          ...value.aids,
                          [ear]: { ...value.aids[ear]!, tier: e.target.value },
                        })
                      }
                    >
                      {["110", "220", "330", "440"].map((t) => (
                        <option key={t}>{t}</option>
                      ))}
                    </select>
                  </label>
                </fieldset>
              ),
          )}
        </div>
        <p className="caption">
          Illustrative device scope. Tier-specific differences are not inferred.
        </p>
      </section>
      {error && <ErrorBox message={error} />}
      <div className="form-footer">
        <p>Illustrative demo. Do not enter real patient information.</p>
        <button className="button" type="submit" disabled={saving}>
          {saving
            ? "Saving…"
            : initial
              ? "Save changes"
              : "Create patient"}
          <ArrowRight size={18} />
        </button>
      </div>
    </form>
  );
}
export function NewPatient() {
  return (
    <>
      <Header clinic />
      <main
        tabIndex={-1}
        id="main"
        className="form-main clinic-form-page page-width"
      >
        <Link className="back-link" href="/clinic">
          <ArrowLeft size={17} />
          Patients
        </Link>
        <div className="page-title-row clinic-form-header">
          <h1>New patient</h1>
        </div>
        <PatientForm />
      </main>
      <Footer />
    </>
  );
}
export function PatientCard({ id }: { id: string }) {
  const [patient, setPatient] = useState<Patient | null>(null),
    [events, setEvents] = useState<ListeningEvent[]>([]),
    [pairing, setPairing] = useState<Pairing | null>(null),
    [qr, setQr] = useState(""),
    [error, setError] = useState(""),
    [editing, setEditing] = useState(false),
    [activeTab, setActiveTab] = useState<"moments" | "profile">("moments"),
    [pairingOpen, setPairingOpen] = useState(false),
    [pairingBusy, setPairingBusy] = useState(false),
    [report, setReport] = useState<{ status: string; url?: string } | null>(
      null,
    ),
    [reportBusy, setReportBusy] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await api<{
          patient: Patient;
          events: ListeningEvent[];
          pairing: Pairing | null;
        }>("/api/patients/" + id);
        if (active) {
          setPatient(result.patient);
          setEvents(result.events);
          if (result.pairing) setPairing(result.pairing);
          setError("");
        }
        const rep = await api<{ status: string; url?: string }>(
          "/api/patients/" + id + "/report",
        );
        if (active) setReport(rep);
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [id]);
  useEffect(() => {
    if (pairing)
      void QRCode.toDataURL(pairing.url, {
        width: 320,
        margin: 2,
        color: { dark: "#234638", light: "#ffffff" },
        errorCorrectionLevel: "M",
      }).then(setQr);
    else setQr("");
  }, [pairing]);
  async function createPairing() {
    setPairingBusy(true);
    try {
      const result = await api<{ pairing?: Pairing } & Pairing>(
        "/api/patients/" + id + "/pairing",
        { method: "POST", body: "{}" },
      );
      setPairing(result.pairing || result);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPairingBusy(false);
    }
  }
  async function revoke() {
    setPairingBusy(true);
    try {
      await api("/api/patients/" + id + "/pairing", { method: "DELETE" });
      setPairing(null);
      setQr("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPairingBusy(false);
    }
  }
  async function requestReport() {
    setReportBusy(true);
    try {
      const result = await api<{ status: string }>(
        "/api/patients/" + id + "/report",
        { method: "POST", body: "{}" },
      );
      setReport(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setReportBusy(false);
    }
  }
  return (
    <>
      <Header clinic />
      <main
        tabIndex={-1}
        id="main"
        className="clinic-main clinic-profile page-width"
      >
        <Link href="/clinic" className="back-link">
          <ArrowLeft size={17} />
          Patients
        </Link>
        {error && <ErrorBox message={error} />}
        {!patient ? (
          <Loading label="Loading patient…" />
        ) : (
          <>
            <div className="page-title-row clinic-profile-header">
              <div>
                <h1>{patient.displayName}</h1>
                <p>
                  <CalendarDays size={17} className="inline-icon" />
                  Follow-up {dateLabel(patient.followUpDate)}
                </p>
              </div>
              <div className="clinic-profile-actions">
                <button
                  className="button secondary"
                  type="button"
                  aria-expanded={pairingOpen}
                  aria-controls="pairing-panel"
                  onClick={() => setPairingOpen((open) => !open)}
                >
                  <Link2 size={17} />
                  Pair phone
                </button>
                {report?.status === "ready" && report.url ? (
                  <a
                    className="button"
                    href={report.url}
                  >
                    <Download size={18} />
                    Download report
                  </a>
                ) : (
                  <button
                    className="button"
                    type="button"
                    disabled={
                      reportBusy ||
                      report?.status === "queued" ||
                      report?.status === "generating"
                    }
                    onClick={requestReport}
                  >
                    <ClipboardList size={18} />
                    {report?.status === "queued" ||
                    report?.status === "generating"
                      ? "Preparing…"
                      : "Export report"}
                  </button>
                )}
              </div>
            </div>

            {report?.status === "failed" && (
              <p className="notice error clinic-report-notice" role="alert">
                The report could not be prepared. The moments are preserved;
                try again after processing finishes.
              </p>
            )}
            {report?.status === "outdated" && (
              <p className="notice clinic-report-notice" role="status">
                New information arrived after the last request. Export an
                updated report after processing finishes.
              </p>
            )}

            {pairingOpen && (
              <section
                id="pairing-panel"
                className="glass pairing-card clinic-pairing-panel"
              >
                <div className="clinic-panel-heading">
                  <div>
                    <h2>Pair phone</h2>
                    <p>Connect this synthetic profile to the patient app.</p>
                  </div>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setPairingOpen(false)}
                  >
                    Close
                  </button>
                </div>
                {pairing ? (
                  <div className="clinic-pairing-content">
                    <div className="qr-container">
                      {qr && (
                        <img
                          src={qr}
                          width="190"
                          height="190"
                          alt="QR code for this demo profile’s opaque pairing link"
                        />
                      )}
                    </div>
                    <div className="clinic-pairing-details">
                      <p>Scan the QR code with the phone camera.</p>
                      <label className="pairing-code">
                        Manual pairing code
                        <code data-testid="pairing-code">{pairing.code}</code>
                      </label>
                      <p className="caption">
                        Expires {dateLabel(pairing.expiresAt)}. This link grants
                        demo access; it is not clinical authentication.
                      </p>
                      {pairing.url.includes("localhost") && (
                        <div className="notice">
                          This link works on this computer only. Cross-device
                          pairing needs a reachable HTTPS origin.
                        </div>
                      )}
                      <div className="pairing-controls">
                        <Link className="text-button" href={pairing.url}>
                          Open pairing link <ArrowRight size={16} />
                        </Link>
                        <button
                          className="text-button"
                          type="button"
                          disabled={pairingBusy}
                          onClick={createPairing}
                        >
                          <RefreshCw size={14} />
                          Replace code
                        </button>
                        <button
                          className="text-button danger"
                          type="button"
                          disabled={pairingBusy}
                          onClick={revoke}
                        >
                          Revoke access
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="clinic-pairing-empty">
                    <p>
                      Create a private pairing link. Replacing it later will
                      disconnect previously paired phones.
                    </p>
                    <button
                      className="button"
                      type="button"
                      disabled={pairingBusy}
                      onClick={createPairing}
                    >
                      {pairingBusy ? "Creating…" : "Create pairing QR"}
                      <ArrowRight size={17} />
                    </button>
                  </div>
                )}
              </section>
            )}

            <div className="clinic-tabs" role="tablist" aria-label="Patient"
              onKeyDown={(event) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                const next = event.key === "Home" ? "moments" : event.key === "End" ? "profile" : activeTab === "moments" ? "profile" : "moments";
                setActiveTab(next);
                if (next === "moments") setEditing(false);
                event.currentTarget.querySelector<HTMLButtonElement>(`#tab-${next}`)?.focus();
              }}>

              <button
                type="button"
                role="tab"
                id="tab-moments"
                tabIndex={activeTab === "moments" ? 0 : -1}
                aria-selected={activeTab === "moments"}
                aria-controls="patient-moments"
                className={activeTab === "moments" ? "active" : ""}
                onClick={() => {
                  setActiveTab("moments");
                  setEditing(false);
                }}
              >
                Moments
                <span>{events.length}</span>
              </button>
              <button
                type="button"
                role="tab"
                id="tab-profile"
                tabIndex={activeTab === "profile" ? 0 : -1}
                aria-selected={activeTab === "profile"}
                aria-controls="patient-profile"
                className={activeTab === "profile" ? "active" : ""}
                onClick={() => setActiveTab("profile")}
              >
                Profile
              </button>
            </div>

            {activeTab === "moments" ? (
              <section
                id="patient-moments"
                aria-labelledby="tab-moments"
                className="moments-section clinic-moments"
                role="tabpanel"
              >
                <aside className="clinic-about-note">
                  <Info size={17} aria-hidden="true" />
                  <p>
                    <strong>About these results</strong>
                    Acoustic details come from a phone recording. They are not
                    calibrated sound pressure or clinical interpretation.
                  </p>
                </aside>
                {events.length === 0 ? (
                  <div className="empty-state compact clinic-empty-state">
                    <h2>No moments yet</h2>
                    <p>Pair a phone to record the first listening moment.</p>
                  </div>
                ) : (
                  <div className="detailed-events clinic-moment-list">
                    {events.map((event) => (
                      <details
                        className="glass event-detail-card clinic-moment-row"
                        id={"event-" + event.id}
                        key={event.id}
                      >
                        <summary className="clinic-moment-summary">
                          <span className={"moment-icon " + event.kind}>
                            {event.kind === "understood" ? (
                              <Check size={21} />
                            ) : (
                              <SlidersHorizontal size={21} />
                            )}
                          </span>
                          <span className="clinic-moment-name">
                            <strong>
                              {event.kind === "understood"
                                ? "I understand"
                                : "I don’t understand"}
                            </strong>
                            <small>
                              {event.kind === "difficult"
                                ? event.difficulty || "Difficulty reported"
                                : "Positive listening moment"}
                            </small>
                          </span>
                          <time dateTime={event.capturedAt}>
                            {dateLabel(event.capturedAt)}
                            <small>
                              {new Date(event.capturedAt).toLocaleTimeString(
                                "en",
                                { hour: "2-digit", minute: "2-digit" },
                              )}
                            </small>
                          </time>
                          <Status value={event.status} />
                          <ChevronDown
                            className="clinic-moment-chevron"
                            size={18}
                            aria-hidden="true"
                          />
                        </summary>
                        <div className="clinic-moment-details">
                          {event.kind === "difficult" && (
                            <div className="reported-answers">
                              <span>
                                <small>Difficulty</small>
                                {event.difficulty || "Not provided"}
                              </span>
                              <span>
                                <small>Surroundings</small>
                                {event.environment || "Not provided"}
                              </span>
                            </div>
                          )}
                          <details className="clinic-acoustic-details">
                            <summary>Acoustic details</summary>
                          {event.analysis ? (
                            <AcousticResult analysis={event.analysis} />
                          ) : (
                            <p
                              className={
                                "notice" +
                                (event.status === "failed" ? " error" : "")
                              }
                              role={
                                event.status === "failed" ? "alert" : "status"
                              }
                            >
                              {event.status === "failed"
                                ? event.error ||
                                  "Processing failed. The moment is preserved."
                                : "Processing this recording…"}
                            </p>
                          )}
                          {event.interpretation && !event.interpretation.result && (
                            <p className="caption">
                              Automated interpretation: <Status value={event.interpretation.status} />
                            </p>
                          )}
                          {event.interpretation?.result && (
                            <section className="interpretation-block clinic-interpretation">
                              <div className="clinic-panel-heading">
                                <h3>Interpretation</h3>
                                <Status value={event.interpretation.status} />
                              </div>
                              {event.interpretation.result.summary && (
                                <p>{event.interpretation.result.summary}</p>
                              )}
                              {!!event.interpretation.result.observations
                                ?.length && (
                                <ul>
                                  {event.interpretation.result.observations.map(
                                    (observation, index) => (
                                      <li key={index}>{observation}</li>
                                    ),
                                  )}
                                </ul>
                              )}
                              {event.interpretation.result.limitations?.map(
                                (limit, index) => (
                                  <p className="caption" key={index}>
                                    {limit}
                                  </p>
                                ),
                              )}
                            </section>
                          )}
                          </details>
                          <details className="clinic-capture-details">
                            <summary>Capture and profile snapshot</summary>
                            <p className="caption">
                              Phone microphone intended. Actual routing may be
                              unknown. Snapshot:{" "}
                              {event.profileSnapshot?.displayName}; follow-up{" "}
                              {event.profileSnapshot?.followUpDate}.
                            </p>
                            <pre>{JSON.stringify(event.capture, null, 2)}</pre>
                          </details>
                        </div>
                      </details>
                    ))}
                  </div>
                )}
              </section>
            ) : editing ? (
              <section id="patient-profile" role="tabpanel">
                <div className="clinic-edit-heading">
                  <h2>Edit profile</h2>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setEditing(false)}
                  >
                    Cancel
                  </button>
                </div>
                <PatientForm
                  initial={patient}
                  onSaved={(updated) => {
                    setPatient(updated);
                    setEditing(false);
                  }}
                />
              </section>
            ) : (
              <section
                id="patient-profile"
                aria-labelledby="tab-profile"
                className="glass overview-profile clinic-profile-panel"
                role="tabpanel"
              >
                <div className="clinic-panel-heading">
                  <h2>Profile</h2>
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() => setEditing(true)}
                  >
                    <Pencil size={16} />
                    Edit profile
                  </button>
                </div>
                <div className="clinic-profile-meta">
                  <span>
                    <small>Follow-up</small>
                    {dateLabel(patient.followUpDate)}
                  </span>
                  <span>
                    <small>Timezone</small>
                    {patient.timezone}
                  </span>
                </div>
                <div className="clinic-profile-section">
                  <h3>Audiogram</h3>
                  <Audiogram data={patient.audiogram} />
                </div>
                <div className="clinic-profile-section">
                  <h3>Hearing aids</h3>
                  <div className="aid-pills">
                    {(["left", "right"] as const).map(
                      (ear) =>
                        patient.aids[ear] && (
                          <span key={ear}>
                            <strong>{ear === "left" ? "L" : "R"}</strong>
                            {patient.aids[ear]!.model} ·{" "}
                            {patient.aids[ear]!.tier}
                          </span>
                        ),
                    )}
                  </div>
                </div>
                <div className="clinic-profile-section clinic-profile-note">
                  <h3>Note</h3>
                  <p>{patient.note || "No note added."}</p>
                </div>
              </section>
            )}
          </>
        )}
      </main>
      <Footer />
    </>
  );
}
