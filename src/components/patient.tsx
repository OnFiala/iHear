"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  CalendarDays,
  Check,
  ChevronRight,
  History,
  Mic,
  MicOff,
  ScanLine,
  ShieldCheck,
  WifiOff,
} from "lucide-react";
import { api, ApiError, dateLabel } from "@/lib/client/api";
import { Microphone } from "@/lib/client/audio";
import {
  flushPending,
  pendingFor,
  savePending,
  type PendingEvent,
} from "@/lib/client/pending";
import {
  difficulties,
  environments,
  tips,
  type Patient,
  type ListeningEvent,
} from "@/lib/types";
import { Header, ErrorBox, Loading, Status, EventList } from "./shared";
const PROFILE_KEY = "ihear-paired-profile";
export function PatientHome() {
  const [patient, setPatient] = useState<Patient | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [ready, setReady] = useState(false),
    [enabling, setEnabling] = useState(false),
    [recording, setRecording] = useState(false),
    [message, setMessage] = useState(""),
    [events, setEvents] = useState<ListeningEvent[]>([]),
    [pending, setPending] = useState<PendingEvent[]>([]),
    [questionEvent, setQuestionEvent] = useState<PendingEvent | null>(null),
    [difficulty, setDifficulty] = useState(""),
    [environment, setEnvironment] = useState(""),
    [recent, setRecent] = useState(false),
    [offline, setOffline] = useState(false);
  const mic = useRef<Microphone | null>(null),
    recordingLock = useRef(false),
    alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    setOffline(!navigator.onLine);
    async function init() {
      try {
        const s = await api<{ patient: Patient | null }>("/api/session");
        if (cancelled) return;
        setPatient(s.patient);
        if (s.patient)
          localStorage.setItem(PROFILE_KEY, JSON.stringify(s.patient));
        else localStorage.removeItem(PROFILE_KEY);
      } catch (e) {
        if (cancelled) return;
        if (!navigator.onLine || e instanceof TypeError) {
          setOffline(true);
          try {
            const cached = localStorage.getItem(PROFILE_KEY);
            if (cached) setPatient(JSON.parse(cached));
            else
              setError(
                "Open and pair iHear online once before using it offline.",
              );
          } catch {
            localStorage.removeItem(PROFILE_KEY);
            setError(
              "The saved profile could not be opened. Reconnect and pair again.",
            );
          }
        } else setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void init();
    if ("serviceWorker" in navigator)
      void navigator.serviceWorker.register("/sw.js").catch(() => {});
    return () => {
      cancelled = true;
      alive.current = false;
      mic.current?.stop();
    };
  }, []);
  useEffect(() => {
    if (!patient) return;
    const patientId = patient.id;
    let active = true;
    async function refresh() {
      const drafts = await pendingFor(patientId);
      if (active) setPending(drafts);
      if (navigator.onLine) {
        try {
          const result = await api<{ events: ListeningEvent[] }>("/api/events");
          if (active) setEvents(result.events);
        } catch (e) {
          if (
            active &&
            e instanceof ApiError &&
            (e.status === 401 || e.status === 403)
          ) {
            mic.current?.stop();
            setReady(false);
            setError(
              "This pairing may have expired or been revoked. Pair the profile again. Pending moments remain on this device.",
            );
          }
        }
      }
    }
    const changed = () => {
      void refresh();
    };
    const retry = () => {
      setOffline(!navigator.onLine);
      void flushPending(patientId, changed);
      void refresh();
    };
    const visibility = () => {
      if (document.visibilityState === "hidden") {
        mic.current?.stop();
        setReady(false);
        setMessage("Microphone paused. Enable it again when you return.");
      } else retry();
    };
    const pagehide = () => {
      mic.current?.stop();
      setReady(false);
    };
    retry();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") retry();
    }, 7000);
    window.addEventListener("online", retry);
    window.addEventListener("offline", retry);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", pagehide);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener("online", retry);
      window.removeEventListener("offline", retry);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", pagehide);
    };
  }, [patient]);
  async function enable() {
    setEnabling(true);
    setError("");
    try {
      mic.current?.stop();
      mic.current = new Microphone(() => {
        if (alive.current) {
          setReady(false);
          setMessage("Microphone paused. Enable it again to record.");
        }
      });
      await mic.current.enable();
      if (alive.current) {
        setReady(true);
        setMessage("");
      }
    } catch (e) {
      setError((e as Error).message);
      setReady(false);
    } finally {
      setEnabling(false);
    }
  }
  async function capture(kind: "understood" | "difficult") {
    if (!patient || recordingLock.current || !ready) return;
    recordingLock.current = true;
    setRecording(true);
    setError("");
    setMessage("Keep this screen open. Saving a short listening sample…");
    const capturedAt = new Date().toISOString();
    const id = crypto.randomUUID();
    try {
      const audio = await mic.current!.capture();
      const event: PendingEvent = {
        id,
        patientId: patient.id,
        kind,
        difficulty: null,
        environment: null,
        capturedAt,
        capture: audio.capture,
        audio: audio.blob,
        state: "saved locally",
        needsAnswers: kind === "difficult",
      };
      await savePending(event);
      setPending(await pendingFor(patient.id));
      if (kind === "difficult") {
        setQuestionEvent(event);
        setDifficulty("");
        setEnvironment("");
        setMessage("Saved on this device. Two quick questions.");
      } else {
        setMessage("Moment saved on this device. Thank you.");
        await flushPending(patient.id, () => {
          void pendingFor(patient.id).then(setPending);
        });
        if ((await pendingFor(patient.id)).every((e) => e.id !== id))
          setMessage(
            "Moment received. Your clinician will see it after processing.",
          );
      }
    } catch (e) {
      setError((e as Error).message);
      setMessage("");
    } finally {
      setRecording(false);
      recordingLock.current = false;
    }
  }
  async function finishAnswers(e: React.FormEvent) {
    e.preventDefault();
    if (!questionEvent || !patient) return;
    const event = {
      ...questionEvent,
      difficulty,
      environment,
      needsAnswers: false,
    };
    await savePending(event);
    setQuestionEvent(null);
    setMessage("Answers saved on this device.");
    await flushPending(patient.id, () => {
      void pendingFor(patient.id).then(setPending);
    });
    if ((await pendingFor(patient.id)).every((e) => e.id !== event.id))
      setMessage("Moment received. Thank you for sharing what happened.");
  }
  if (loading)
    return (
      <>
        <Header patient />
        <main tabIndex={-1} id="main" className="patient-main">
          <Loading />
        </main>
      </>
    );
  if (!patient)
    return (
      <>
        <Header patient />
        <main tabIndex={-1} id="main" className="patient-main unpaired">
          <span className="eyebrow">Your listening companion</span>
          <h1>
            A small moment.
            <br />A useful conversation.
          </h1>
          <p className="lead">
            Connect to the demo profile your clinician created, then remember
            the moments that matter.
          </p>
          <div className="glass onboarding-art">
            <ScanLine size={68} strokeWidth={1.2} />
          </div>
          {error && <ErrorBox message={error} />}
          <Link className="button full" href="/app/pair">
            <ScanLine size={22} />
            Pair a demo profile
          </Link>
          <p className="caption">
            Have a QR code? Your phone’s camera can open it too.
          </p>
          <div className="patient-boundary">
            <ShieldCheck size={18} />
            <p>
              Illustrative use only. No login, no speech transcription. Use
              synthetic profiles.
            </p>
          </div>
        </main>
      </>
    );
  return (
    <>
      <Header patient />
      <main tabIndex={-1} id="main" className="patient-main">
        <div className="patient-welcome">
          <div>
            <span className="eyebrow">Your listening space</span>
            <h1>Hello, {patient.displayName.split(" ")[0]}.</h1>
          </div>
          <span className="avatar sage">{patient.displayName[0]}</span>
        </div>
        <div className="appointment-line">
          <CalendarDays size={17} />
          <span>Next appointment · {dateLabel(patient.followUpDate)}</span>
        </div>
        {offline && (
          <div className="notice">
            <WifiOff size={19} />
            Offline. Moments stay on this device until you reconnect.
          </div>
        )}
        {error && <ErrorBox message={error} />}{" "}
        {questionEvent ? (
          <section className="glass questions">
            <span className="eyebrow">A little context</span>
            <h2>What was difficult?</h2>
            <form onSubmit={finishAnswers}>
              <fieldset>
                <legend className="sr-only">What was difficult?</legend>
                {difficulties.map((d) => (
                  <label
                    className={"choice " + (difficulty === d ? "selected" : "")}
                    key={d}
                  >
                    <input
                      required
                      type="radio"
                      name="difficulty"
                      value={d}
                      checked={difficulty === d}
                      onChange={() => setDifficulty(d)}
                    />
                    <span>{d}</span>
                  </label>
                ))}
              </fieldset>
              <h2>What was around you?</h2>
              <fieldset>
                <legend className="sr-only">What was around you?</legend>
                {environments.map((v) => (
                  <label
                    className={
                      "choice " + (environment === v ? "selected" : "")
                    }
                    key={v}
                  >
                    <input
                      required
                      type="radio"
                      name="environment"
                      checked={environment === v}
                      value={v}
                      onChange={() => setEnvironment(v)}
                    />
                    <span>{v}</span>
                  </label>
                ))}
              </fieldset>
              <button
                className="button full"
                disabled={!difficulty || !environment}
              >
                Save these answers <Check size={20} />
              </button>
            </form>
          </section>
        ) : (
          <>
            <div className="listening-prompt">
              <span className="eyebrow">Right here, right now</span>
              <h2>How is listening?</h2>
            </div>
            <div
              className={"patient-actions " + (recording ? "is-recording" : "")}
            >
              <button
                className="understand-action"
                disabled={!ready || recording}
                onClick={() => capture("understood")}
              >
                <span className="action-symbol">
                  <Check size={32} strokeWidth={1.7} />
                </span>
                <span>I understand</span>
                <span className="action-sub">A moment that feels good</span>
              </button>
              <button
                className="difficult-action"
                disabled={!ready || recording}
                onClick={() => capture("difficult")}
              >
                <span className="action-symbol">
                  <AudioLines size={31} strokeWidth={1.6} />
                </span>
                <span>I don’t understand</span>
                <span className="action-sub">Let’s remember this moment</span>
              </button>
            </div>
            <div className={"microphone-panel " + (ready ? "mic-ready" : "")}>
              {ready ? (
                <>
                  <span className="mic-status">
                    <Mic size={18} />
                    {recording ? "Recording this moment…" : "Microphone ready"}
                  </span>
                  <button
                    className="text-button"
                    disabled={recording}
                    onClick={() => {
                      mic.current?.stop();
                      setReady(false);
                      setMessage("Microphone stopped.");
                    }}
                  >
                    Stop
                  </button>
                </>
              ) : (
                <button
                  className="button microphone-button"
                  disabled={enabling}
                  onClick={enable}
                >
                  <Mic size={20} />
                  {enabling ? "Enabling microphone…" : "Enable microphone"}
                </button>
              )}
            </div>
            <p className="microphone-note">
              {ready
                ? "Only while this screen is open. Each moment saves about 10 seconds."
                : "Enable your phone microphone to save a listening sample."}
            </p>
            {message && (
              <p className="patient-message" role="status">
                {recording && (
                  <AudioLines className="recording-wave" size={20} />
                )}{" "}
                {message}
              </p>
            )}
            {pending.length > 0 && (
              <div
                className="pending-list glass"
                aria-label="Moments saved on this device"
              >
                {pending.map((e) => (
                  <div key={e.id}>
                    <div>
                      <strong>
                        {e.kind === "understood"
                          ? "Positive moment"
                          : "Difficult moment"}
                      </strong>
                      <Status value={e.state} />
                    </div>
                    {e.needsAnswers ? (
                      <button
                        className="text-button"
                        onClick={() => {
                          setQuestionEvent(e);
                          setDifficulty(e.difficulty || "");
                          setEnvironment(e.environment || "");
                        }}
                      >
                        Finish two questions <ChevronRight size={17} />
                      </button>
                    ) : (
                      <p className="caption">
                        {e.error || "Will retry when you return online."}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
            <button
              className="recent-toggle"
              onClick={() => setRecent(!recent)}
              aria-expanded={recent}
            >
              <History size={21} />
              <span>Recent moments</span>
              <ChevronRight size={20} />
            </button>
            {recent && (
              <section className="recent-section">
                {events.length ? (
                  <EventList events={events.slice(0, 10)} patient />
                ) : (
                  <p className="caption">
                    Your received moments will appear here.
                  </p>
                )}
              </section>
            )}
            <details className="patient-info">
              <summary>About your microphone and this demo</summary>
              <p>
                Prebuffering starts only after you enable the microphone. Up to
                five seconds before a press and five seconds after are captured.
                A shorter prebuffer adds more time after the press. Locking your
                phone or leaving the app stops monitoring.
              </p>
              <p>
                The phone microphone is intended, but connected hearing aids or
                other devices can change audio routing. The app records
                available source settings; it cannot confirm where sound was
                captured.
              </p>
              <p>
                Audio is private and is deleted after successful feature
                extraction. Failed or abandoned uploads are cleaned up within a
                bounded retention window. Clinical interpretation remains with
                your clinician.
              </p>
              <p>
                Only save recordings you are comfortable sharing in this demo.
                Avoid private conversations and real patient details.
              </p>
            </details>
          </>
        )}
      </main>
    </>
  );
}
export function PairConfirmation({ token }: { token: string }) {
  const [name, setName] = useState(""),
    [error, setError] = useState(""),
    [ack, setAck] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    void api<{ displayName: string }>("/api/pair/" + encodeURIComponent(token))
      .then((r) => setName(r.displayName))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);
  async function confirm() {
    setBusy(true);
    try {
      const result = await api<{ patient: Patient }>(
        "/api/pair/" + encodeURIComponent(token),
        { method: "POST", body: JSON.stringify({ acknowledged: ack }) },
      );
      localStorage.setItem(PROFILE_KEY, JSON.stringify(result.patient));
      window.location.href = "/app";
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Header patient />
      <main tabIndex={-1} id="main" className="patient-main pairing-confirm">
        <span className="eyebrow">A simple connection</span>
        {loading ? (
          <Loading label="Checking your pairing link…" />
        ) : name ? (
          <>
            <span className="pair-confirm-icon">
              <Check size={38} />
            </span>
            <h1>
              Is this your
              <br />
              demo profile?
            </h1>
            <div className="glass paired-person">
              <span className="avatar sage">{name[0]}</span>
              <div>
                <strong>{name}</strong>
                <span>Synthetic demo profile</span>
              </div>
            </div>
            <p>
              Confirm to open your listening space on this device. Pairing
              replaces the current patient profile here.
            </p>
            <label className="acknowledgement">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
              />
              <span>
                I understand this is an illustrative demo, not clinical
                authentication or medical advice. I will use synthetic
                information.
              </span>
            </label>
            <button
              className="button full"
              disabled={!ack || busy}
              onClick={confirm}
            >
              {busy ? "Connecting…" : "Yes, open my listening space"}
              <ArrowRight size={20} />
            </button>
          </>
        ) : (
          <>
            <h1>
              This link cannot
              <br />
              connect a profile.
            </h1>
            <p>
              It may be invalid, expired or revoked. Ask for a new pairing code.
            </p>
            <Link className="button full" href="/app/pair">
              Enter another code
            </Link>
          </>
        )}
        {error && <ErrorBox message={error} />}
      </main>
    </>
  );
}
export function PairScanner() {
  const [code, setCode] = useState(""),
    [error, setError] = useState(""),
    [scanning, setScanning] = useState(false);
  const video = useRef<HTMLVideoElement>(null),
    controls = useRef<{ stop: () => void } | null>(null),
    generation = useRef(0);
  function stop() {
    generation.current++;
    controls.current?.stop();
    controls.current = null;
    setScanning(false);
  }
  useEffect(
    () => () => {
      generation.current++;
      controls.current?.stop();
    },
    [],
  );
  function openCode(raw: string) {
    let token = raw.trim();
    if (token.startsWith("http")) {
      const url = new URL(token);
      if (
        url.origin !== window.location.origin ||
        !url.pathname.startsWith("/pair/")
      )
        throw new Error("Use an iHear pairing code from this demo.");
      token = url.pathname.slice(6);
    }
    token = token.replace(/[\s-]/g, "");
    if (!/^[A-Za-z0-9]{16,100}$/.test(token))
      throw new Error("Check the pairing code and try again.");
    controls.current?.stop();
    window.location.href = "/pair/" + encodeURIComponent(token);
  }
  async function scan() {
    setError("");
    setScanning(true);
    const current = ++generation.current;
    try {
      const { BrowserQRCodeReader } = await import("@zxing/browser");
      const reader = new BrowserQRCodeReader();
      const control = await reader.decodeFromConstraints(
        { video: { facingMode: "environment" }, audio: false },
        video.current!,
        (result) => {
          if (result && generation.current === current) {
            try {
              openCode(result.getText());
            } catch (e) {
              setError((e as Error).message);
            }
          }
        },
      );
      if (generation.current !== current) control.stop();
      else controls.current = control;
    } catch {
      setError(
        "Camera access is unavailable. Allow the camera in browser settings or enter the pairing code below.",
      );
      setScanning(false);
    }
  }
  return (
    <>
      <Header patient />
      <main tabIndex={-1} id="main" className="patient-main scanner-page">
        <Link href="/app" className="back-link">
          <ArrowLeft size={18} />
          Listening space
        </Link>
        <span className="eyebrow">Start with your clinician</span>
        <h1>
          One scan.
          <br />
          Your listening space.
        </h1>
        <p>
          Scan the QR code on your demo patient card, or enter its pairing code.
        </p>
        <div className={"scanner-frame glass " + (scanning ? "active" : "")}>
          <video
            ref={video}
            playsInline
            muted
            aria-label="Pairing QR camera preview"
          />
          {!scanning && <ScanLine size={72} strokeWidth={1.2} />}
        </div>
        {scanning ? (
          <button className="button secondary full" onClick={stop}>
            Stop camera
          </button>
        ) : (
          <button className="button full" onClick={scan}>
            <ScanLine size={21} />
            Open camera to scan
          </button>
        )}
        {error && <ErrorBox message={error} />}
        <div className="or-divider">
          <span>or enter a code</span>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            try {
              openCode(code);
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          <label>
            Pairing code
            <input
              autoCapitalize="characters"
              autoComplete="off"
              spellCheck={false}
              placeholder="Code from your clinician"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
          </label>
          <button className="button secondary full" disabled={!code.trim()}>
            Continue <ArrowRight size={18} />
          </button>
        </form>
        <p className="caption">
          You can also use your phone’s native camera. The QR contains an opaque
          link, not your name or audiogram.
        </p>
      </main>
    </>
  );
}
export function PatientEvent({ id }: { id: string }) {
  const [event, setEvent] = useState<ListeningEvent | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const load = () =>
      api<{ event: ListeningEvent }>("/api/events/" + id)
        .then((r) => {
          if (active) setEvent(r.event);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    void load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [id]);
  return (
    <>
      <Header patient />
      <main tabIndex={-1} id="main" className="patient-main">
        <Link href="/app" className="back-link">
          <ArrowLeft size={18} />
          My listening space
        </Link>
        {error && <ErrorBox message={error} />}{" "}
        {!event ? (
          <Loading label="Opening your moment…" />
        ) : (
          <>
            <span className="eyebrow">A moment you remembered</span>
            <h1>
              {event.kind === "understood"
                ? "I understand."
                : "I don’t understand."}
            </h1>
            <p>{dateLabel(event.capturedAt)}</p>
            <section className="glass patient-event-summary">
              <Status value={event.status} />
              {event.kind === "difficult" && (
                <>
                  <h3>What was difficult</h3>
                  <p>{event.difficulty}</p>
                  <h3>What was around you</h3>
                  <p>{event.environment}</p>
                </>
              )}
              <p>
                {event.status === "ready"
                  ? "Your acoustic results are available to your clinician."
                  : event.status === "failed"
                    ? "This moment is preserved, but analysis could not finish."
                    : "Your moment has been received. Processing continues while you are away."}
              </p>
              {event.interpretation?.status === "unavailable" && (
                <p className="caption">
                  Astra interpretation is unavailable for this moment.
                </p>
              )}
              {event.interpretation?.status === "held_budget" && (
                <p className="caption">
                  This demo has reached its interpretation limit. Your moment
                  and acoustic results are saved.
                </p>
              )}
              {event.interpretation?.status === "held_ambiguity" && (
                <p className="caption">
                  No interpretation was completed for this sample. Your
                  clinician can still review its acoustic results.
                </p>
              )}
            </section>
            {event.interpretation?.result?.tip_ids
              ?.filter((id) => tips[id])
              .slice(0, 1)
              .map((id) => (
                <section className="glass tip-card" key={id}>
                  <span className="eyebrow">A gentle suggestion</span>
                  <p>{tips[id]}</p>
                </section>
              ))}
            <p className="caption">
              Your feedback and this recording can support a conversation. They
              do not diagnose a condition or prescribe hearing-aid settings.
            </p>
          </>
        )}
      </main>
    </>
  );
}
