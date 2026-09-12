"use client";

import { Download, Share2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

const DISMISSED_KEY = "ihear-install-offer-dismissed-v1";

type InstallChoice = { outcome: "accepted" | "dismissed"; platform?: string };
type InstallPromptEvent = Event & {
  prompt: () => Promise<InstallChoice | void>;
  userChoice?: Promise<InstallChoice>;
};

type NavigatorWithStandalone = Navigator & { standalone?: boolean };

export type HomeScreenInstallController = {
  installed: boolean;
  openHelp: () => void;
  offer: React.ReactNode;
};

export function installGuidance(userAgent: string): string[] {
  const ios = /iPad|iPhone|iPod/.test(userAgent);
  const safari = /Safari/.test(userAgent) && !/CriOS|FxiOS|EdgiOS/.test(userAgent);
  if (ios && safari)
    return [
      "Tap Share in Safari.",
      "Choose Add to Home Screen, then tap Add.",
    ];
  if (ios)
    return [
      "Open this page in Safari.",
      "Tap Share, choose Add to Home Screen, then tap Add.",
    ];
  return [
    "Open your browser menu.",
    "Choose Install app or Add to Home screen.",
  ];
}

function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    Boolean((navigator as NavigatorWithStandalone).standalone)
  );
}

export function useHomeScreenInstall(): HomeScreenInstallController {
  const prompt = useRef<InstallPromptEvent | null>(null);
  const offerRef = useRef<HTMLElement | null>(null);
  const [installed, setInstalled] = useState(false);
  const [dismissed, setDismissed] = useState(true);
  const [showGuidance, setShowGuidance] = useState(false);
  const [nativePrompt, setNativePrompt] = useState(false);
  const [requestAccepted, setRequestAccepted] = useState(false);
  const [installError, setInstallError] = useState("");

  useEffect(() => {
    setInstalled(isStandalone());
    setDismissed(localStorage.getItem(DISMISSED_KEY) === "yes");
    const displayMode = window.matchMedia("(display-mode: standalone)");
    const displayChanged = () => setInstalled(isStandalone());
    const beforeInstall = (rawEvent: Event) => {
      const event = rawEvent as InstallPromptEvent;
      event.preventDefault();
      prompt.current = event;
      setNativePrompt(true);
      setRequestAccepted(false);
      setInstallError("");
    };
    const appInstalled = () => {
      prompt.current = null;
      setNativePrompt(false);
      setInstalled(true);
    };
    displayMode.addEventListener("change", displayChanged);
    window.addEventListener("beforeinstallprompt", beforeInstall);
    window.addEventListener("appinstalled", appInstalled);
    return () => {
      displayMode.removeEventListener("change", displayChanged);
      window.removeEventListener("beforeinstallprompt", beforeInstall);
      window.removeEventListener("appinstalled", appInstalled);
    };
  }, []);

  const openHelp = useCallback(() => {
    setDismissed(false);
    setShowGuidance(true);
    setRequestAccepted(false);
    setInstallError("");
    window.requestAnimationFrame(() =>
      offerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
    );
  }, []);

  async function install() {
    const event = prompt.current;
    if (!event) {
      setShowGuidance(true);
      return;
    }
    prompt.current = null;
    setNativePrompt(false);
    setInstallError("");
    try {
      const promptResult = await event.prompt();
      const result = promptResult ?? (await event.userChoice);
      if (!result) {
        setShowGuidance(true);
        return;
      }
      setRequestAccepted(result.outcome === "accepted");
      if (result.outcome === "dismissed") setShowGuidance(true);
    } catch {
      setInstallError(
        "The install prompt could not be opened. Use your browser menu instead.",
      );
      setShowGuidance(true);
    }
  }

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "yes");
    setDismissed(true);
    setShowGuidance(false);
  }

  const offer = !installed && !dismissed ? (
    <section
      id="home-screen-install"
      className="patient-install"
      aria-label="Home Screen access"
      ref={offerRef}
    >
      <div className="patient-install-copy">
        <h2>Keep iHear on this phone</h2>
        <p>Open it from your Home Screen for quicker access.</p>
      </div>
      {requestAccepted ? (
        <p role="status">
          The browser accepted the install request. Wait for the iHear icon to
          appear.
        </p>
      ) : (
        <div className="patient-install-actions">
          <button type="button" className="button" onClick={install}>
            {nativePrompt ? <Download size={17} /> : <Share2 size={17} />}
            {nativePrompt ? "Add to Home Screen" : "How to add"}
          </button>
          <button
            type="button"
            className="text-button"
            aria-label="Dismiss Home Screen suggestion"
            onClick={dismiss}
          >
            <X size={17} />
            Not now
          </button>
        </div>
      )}
      {installError && <p role="alert">{installError}</p>}
      {showGuidance && (
        <ol className="patient-install-steps">
          {installGuidance(navigator.userAgent).map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}
      <p className="caption">
        A Home Screen copy may use separate browser storage. If your profile is
        missing there, pair it again with a fresh clinician code.
      </p>
    </section>
  ) : null;

  return { installed, openHelp, offer };
}
