"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  AudioLines,
  Check,
  ChevronRight,
  History,
  Mic,
  ScanLine,
  Settings,
  ShieldCheck,
  WifiOff,
} from "lucide-react";
import { api, ApiError, dateLabel } from "@/lib/client/api";
import { Microphone, MicrophoneCancelledError } from "@/lib/client/audio";
import {
  forgetMicrophoneConsent,
  hasMicrophoneConsent,
  queryMicrophonePermission,
  rememberMicrophoneConsent,
  shouldAutoAcquireMicrophone,
  type MicrophonePermissionState,
} from "@/lib/client/microphone-access";
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
import { useHomeScreenInstall } from "./home-screen-install";
const PROFILE_KEY = "ihear-paired-profile";
export function PatientHome() {
  const [patient, setPatient] = useState<Patient | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [micState, setMicState] = useState<
      "off" | "ready" | "gesture-required"
    >("off"),
    [enabling, setEnabling] = useState(false),
    [recording, setRecording] = useState(false),
    [message, setMessage] = useState(""),
    [events, setEvents] = useState<ListeningEvent[]>([]),
    [pending, setPending] = useState<PendingEvent[]>([]),
    [questionEvent, setQuestionEvent] = useState<PendingEvent | null>(null),
    [difficulty, setDifficulty] = useState(""),
    [environment, setEnvironment] = useState(""),
    [recent, setRecent] = useState(false),
    [aboutOpen, setAboutOpen] = useState(false),
    [offline, setOffline] = useState(false),
    [sessionRevoked, setSessionRevoked] = useState(false);
  const mic = useRef<Microphone | null>(null),
    recordingLock = useRef(false),
    about = useRef<HTMLDetailsElement | null>(null),
    alive = useRef(true),
    currentPatientId = useRef<string | null>(null);
  const install = useHomeScreenInstall();
  const ready = micState === "ready";
  const captureAvailable = ready || micState === "gesture-required";
  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    setOffline(!navigator.onLine);
    async function init() {
      try {
        const s = await api<{ patient: Patient | null }>("/api/session");
        if (cancelled) return;
        setPatient(s.patient);
        setSessionRevoked(false);
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
            setMicState("off");
            setSessionRevoked(true);
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
      if (document.visibilityState === "visible") retry();
    };
    retry();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") retry();
    }, 7000);
    window.addEventListener("online", retry);
    window.addEventListener("offline", retry);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener("online", retry);
      window.removeEventListener("offline", retry);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [patient]);

  function microphone(): Microphone {
    if (!mic.current)
      mic.current = new Microphone((state) => {
        if (!alive.current) return;
        setMicState(state === "gesture-required" ? state : "off");
        setMessage(
          state === "gesture-required"
            ? "Microphone paused. Tap either listening button to activate it."
            : "Microphone access was interrupted. Try again when you are ready.",
        );
      });
    return mic.current;
  }

  async function startMicrophone(userInitiated: boolean) {
    if (!patient || sessionRevoked || document.visibilityState !== "visible")
      return;
    const patientId = patient.id;
    setEnabling(true);
    if (userInitiated) setError("");
    try {
      const state = await microphone().enable();
      if (
        !alive.current ||
        currentPatientId.current !== patientId ||
        document.visibilityState !== "visible"
      ) {
        mic.current?.stop();
        return;
      }
      if (userInitiated) rememberMicrophoneConsent(patientId);
      setMicState(state);
      setMessage(
        state === "gesture-required"
          ? "Microphone paused. Tap either listening button to activate it."
          : "",
      );
    } catch (e) {
      if (!(e instanceof MicrophoneCancelledError) && alive.current)
        setError((e as Error).message);
      setMicState("off");
    } finally {
      if (alive.current) setEnabling(false);
    }
  }

  useEffect(() => {
    if (!patient || sessionRevoked) return;
    const patientId = patient.id;
    currentPatientId.current = patientId;
    let active = true;
    let permissionStatus: PermissionStatus | null = null;

    const applyPermission = (state: MicrophonePermissionState) => {
      if (!active) return;
      const consented = hasMicrophoneConsent(patientId);
      if (state === "denied" || state === "prompt") {
        mic.current?.stop();
        setMicState("off");
        if (state === "denied" && consented)
          setMessage(
            "Microphone access is off in browser settings. Allow it there, then try again.",
          );
        return;
      }
      if (
        shouldAutoAcquireMicrophone(
          consented,
          state,
          document.visibilityState,
        )
      )
        void startMicrophone(false);
    };

    const refreshPermission = async () => {
      const status = await queryMicrophonePermission();
      if (!active) return;
      if (permissionStatus !== status) {
        permissionStatus?.removeEventListener("change", permissionChanged);
        permissionStatus = status;
        permissionStatus?.addEventListener("change", permissionChanged);
      }
      applyPermission(status?.state ?? "unsupported");
    };
    const permissionChanged = () =>
      applyPermission(permissionStatus?.state ?? "unsupported");
    const visibilityChanged = () => {
      if (document.visibilityState === "hidden") {
        mic.current?.stop();
        setMicState("off");
        setEnabling(false);
        if (hasMicrophoneConsent(patientId))
          setMessage("Microphone paused while iHear was in the background.");
      } else void refreshPermission();
    };
    const pageHidden = () => {
      mic.current?.stop();
      setMicState("off");
    };

    void refreshPermission();
    document.addEventListener("visibilitychange", visibilityChanged);
    window.addEventListener("pagehide", pageHidden);
    return () => {
      active = false;
      currentPatientId.current = null;
      permissionStatus?.removeEventListener("change", permissionChanged);
      document.removeEventListener("visibilitychange", visibilityChanged);
      window.removeEventListener("pagehide", pageHidden);
      mic.current?.stop();
      mic.current = null;
      setMicState("off");
    };
  }, [patient, sessionRevoked]);

  async function enable() {
    await startMicrophone(true);
  }
  async function capture(kind: "understood" | "difficult") {
    if (!patient || recordingLock.current || !captureAvailable) return;
    recordingLock.current = true;
    setRecording(true);
    setError("");
    setMessage("Keep this screen open. Saving a short listening sample…");
    const capturedAt = new Date().toISOString();
    const id = crypto.randomUUID();
    try {
      const audio = await mic.current!.capture();
      setMicState("ready");
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
        setMessage("Saved on this device.");
        await flushPending(patient.id, () => {
          void pendingFor(patient.id).then(setPending);
        });
        if ((await pendingFor(patient.id)).every((e) => e.id !== id))
          setMessage(
            "Moment saved.",
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
      setMessage("Moment saved.");
  }
  const savedMoments = [
    ...events.map((event) => event.capturedAt),
    ...pending
      .filter((event) => event.state === "saved locally")
      .map((event) => event.capturedAt),
  ];
  const lastSavedAt = savedMoments.reduce(
    (latest, capturedAt) =>
      !latest || new Date(capturedAt).getTime() > new Date(latest).getTime()
        ? capturedAt
        : latest,
    "",
  );
  function toggleAbout() {
    const opening = !aboutOpen;
    setAboutOpen(opening);
    if (opening)
      window.requestAnimationFrame(() => {
        about.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        about.current?.querySelector("summary")?.focus({ preventScroll: true });
      });
  }
  const microphoneControl = (
    <div
      className={
        "patient-mic-control " +
        (captureAvailable ? "mic-ready " : "") +
        (micState === "gesture-required" ? "mic-resume" : "")
      }
    >
      {captureAvailable ? (
        <>
          <span className="mic-status">
            {recording ? <AudioLines size={18} /> : <Mic size={18} />}
            {recording
              ? "Recording this moment…"
              : micState === "gesture-required"
                ? "Microphone paused"
                : "Microphone on"}
          </span>
          <button
            className="text-button"
            disabled={recording}
            onClick={() => {
              mic.current?.stop();
              if (patient) forgetMicrophoneConsent(patient.id);
              setMicState("off");
              setMessage("Microphone stopped.");
            }}
          >
            Stop
          </button>
        </>
      ) : sessionRevoked ? (
        <span className="mic-status">Pair again to use the microphone.</span>
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
  );
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
          <h1>Pair this phone</h1>
          <p className="lead">Scan your clinician’s pairing code to begin.</p>
          <div className="glass onboarding-art">
            <ScanLine size={68} strokeWidth={1.2} />
          </div>
          {error && <ErrorBox message={error} />}
          <Link className="button full" href="/app/pair">
            <ScanLine size={22} />
            Pair a profile
          </Link>
          <p className="caption">
            You can scan the QR code or enter its code manually.
          </p>
          <p className="caption">
            A Home Screen copy may use separate browser storage. If this profile
            is missing after installation, pair it again with a fresh clinician
            code.
          </p>
          {install.offer}
          <div className="patient-boundary">
            <ShieldCheck size={18} />
            <p>Illustrative demo. Use synthetic information only.</p>
          </div>
        </main>
      </>
    );
  return (
    <>
      <Header
        patient
        actions={
          <button
            className="patient-about-button"
            type="button"
            aria-label="About & privacy"
            aria-controls="patient-about"
            aria-expanded={aboutOpen}
            onClick={toggleAbout}
          >
            <Settings size={20} />
          </button>
        }
      />
      <main tabIndex={-1} id="main" className="patient-main patient-home">
        <div className="patient-identity">
          <div>
            <h1>{patient.displayName.split(" ")[0]}</h1>
            <p>Next visit · {dateLabel(patient.followUpDate)}</p>
          </div>
        </div>
        {offline && (
          <div className="notice">
            <WifiOff size={19} />
            Offline. Moments stay on this device until you reconnect.
          </div>
        )}
        {error && <ErrorBox message={error} />}{" "}
        {install.offer}
        {questionEvent && captureAvailable && microphoneControl}
        {questionEvent ? (
          <section className="glass questions patient-questionnaire">
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
                Save answers <Check size={20} />
              </button>
            </form>
          </section>
        ) : (
          <>
            {recent ? (
              <>
                {captureAvailable && microphoneControl}
                <section className="recent-section" aria-label="History">
                  <h2>History</h2>
                  {events.length ? (
                    <EventList events={events} patient />
                  ) : (
                    <p className="caption">Saved moments will appear here.</p>
                  )}
                </section>
              </>
            ) : (
              <>
                {microphoneControl}
                <div
                  className={
                    "patient-actions " + (recording ? "is-recording" : "")
                  }
                >
                  <button
                    className="understand-action"
                    disabled={!captureAvailable || recording}
                    onClick={() => capture("understood")}
                  >
                    <span className="action-symbol">
                      <Check size={32} strokeWidth={1.7} />
                    </span>
                    <span>I understand</span>
                  </button>
                  <button
                    className="difficult-action"
                    disabled={!captureAvailable || recording}
                    onClick={() => capture("difficult")}
                  >
                    <span className="action-symbol">
                      <AudioLines size={31} strokeWidth={1.6} />
                    </span>
                    <span>I don’t understand</span>
                  </button>
                </div>
                <p className="patient-last-saved">
                  {lastSavedAt && <Check size={20} aria-hidden="true" />}
                  {lastSavedAt
                    ? `Last saved · ${dateLabel(lastSavedAt)}, ${new Date(lastSavedAt).toLocaleTimeString("en", { hour: "2-digit", minute: "2-digit" })}`
                    : "No moments saved yet"}
                </p>
              </>
            )}
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
            <details
              id="patient-about"
              className="patient-info"
              ref={about}
              open={aboutOpen}
              onToggle={(event) => setAboutOpen(event.currentTarget.open)}
            >
              <summary>About & privacy</summary>
              <Link className="text-button" href="/app/pair">Pair another profile <ArrowRight size={16} /></Link>
              {install.installed ? (
                <p>iHear is open from your Home Screen.</p>
              ) : (
                <button
                  type="button"
                  className="text-button"
                  onClick={install.openHelp}
                >
                  Home Screen access <ArrowRight size={16} />
                </button>
              )}
              <p>
                The microphone starts only after you enable it once for this
                paired profile. If browser permission remains allowed, iHear can
                prepare it again while the app is open. A moment can include up
                to five seconds before and after your press. Leaving or hiding
                the app stops the stream.
              </p>
              <p>
                Offline moments stay on this device and retry when you reconnect.
              </p>
              <p>
                This is an illustrative demo. It does not diagnose a condition
                or set hearing-aid settings.
              </p>
            </details>
            {!recording && (
              <nav className="patient-bottom-nav" aria-label="Patient sections">
                <button
                  type="button"
                  className={!recent ? "active" : ""}
                  aria-current={!recent ? "page" : undefined}
                  onClick={() => setRecent(false)}
                >
                  <Mic size={19} />
                  Record
                </button>
                <button
                  type="button"
                  className={recent ? "active" : ""}
                  aria-current={recent ? "page" : undefined}
                  onClick={() => setRecent(true)}
                >
                  <History size={19} />
                  History
                </button>
              </nav>
            )}
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
        {loading ? (
          <Loading label="Checking your pairing link…" />
        ) : name ? (
          <>
            <span className="pair-confirm-icon">
              <Check size={38} />
            </span>
            <h1>Open this profile?</h1>
            <div className="glass paired-person">
              <span className="avatar sage">{name[0]}</span>
              <div>
                <strong>{name}</strong>
                <span>Synthetic demo profile</span>
              </div>
            </div>
            <p>Pairing replaces the profile currently stored on this phone.</p>
            <label className="acknowledgement">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
              />
              <span>
                I understand this is an illustrative demo and will use
                synthetic information.
              </span>
            </label>
            <button
              className="button full"
              disabled={!ack || busy}
              onClick={confirm}
            >
              {busy ? "Connecting…" : "Confirm profile"}
              <ArrowRight size={20} />
            </button>
          </>
        ) : (
          <>
            <h1>Pairing unavailable</h1>
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
        <h1>Pair this phone</h1>
        <p>Scan the QR code or enter its pairing code.</p>
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
            Scan QR code
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
            <h1>
              {event.kind === "understood"
                ? "I understand."
                : "I don’t understand."}
            </h1>
            <p>{dateLabel(event.capturedAt)}</p>
            <section className="glass patient-event-summary patient-event-detail">
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
              {event.interpretation && ["unavailable", "failed", "skipped"].includes(event.interpretation.status) && (
                <p className="caption">
                  Automated interpretation: {event.interpretation.status}. Your moment is saved.
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
