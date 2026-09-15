"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { api, ApiError } from "@/lib/client/api";
import { frequencies, type Pairing, type Patient, type ProfileInput } from "@/lib/types";
import { ErrorBox } from "./shared";

// A presentation label only; server capabilities continue to authorize every request.
export const PATIENT_DEMO_NOTE = "Patient demo: fictional profile, example audiogram and hearing aids. Recordings and acoustic results are real, not prefilled.";

function exampleProfile(): ProfileInput {
  const visit = new Date();
  visit.setUTCDate(visit.getUTCDate() + 14);
  return {
    displayName: "Alex — demo patient",
    audiogram: { frequencies, left: [25, 30, 35, 45, 55, 60], right: [20, 25, 35, 40, 50, 55] },
    aids: {
      side: "bilateral",
      left: { model: "Widex ALLURE BTE R D", tier: "220" },
      right: { model: "Widex ALLURE BTE R D", tier: "220" },
    },
    followUpDate: visit.toISOString().slice(0, 10),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    note: PATIENT_DEMO_NOTE,
  };
}

export function PatientDemoStart({ disabled, workspaceId }: { disabled: boolean; workspaceId: string | null }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState(""),
    [creationUncertain, setCreationUncertain] = useState(false), [restored, setRestored] = useState(false);
  const running = useRef(false), createdPatient = useRef<string | null>(null);
  const storageKey = workspaceId ? `ihear-demo-setup:${workspaceId}` : null;

  useEffect(() => {
    if (!storageKey) return;
    createdPatient.current = null;
    setCreationUncertain(false);
    setError("");
    try {
      const saved = sessionStorage.getItem(storageKey);
      if (saved) {
        const state = JSON.parse(saved);
        if (typeof state.patientId === "string" && /^[a-f0-9-]{36}$/i.test(state.patientId))
          createdPatient.current = state.patientId;
        else setCreationUncertain(true);
      }
    } catch {
      setError("Demo setup could not be restored. Open the clinician demo to check your profiles.");
      setCreationUncertain(true);
    }
    setRestored(true);
  }, [storageKey]);

  async function start() {
    if (running.current || disabled || creationUncertain || !restored || !storageKey) return;
    running.current = true;
    setBusy(true);
    setError("");
    try {
      if (!createdPatient.current) {
        try {
          // Persist before sending: even a reload after a lost response keeps the warning.
          sessionStorage.setItem(storageKey, JSON.stringify({ creating: true }));
          const result = await api<{ patient: Patient }>("/api/patients", {
            method: "POST", body: JSON.stringify(exampleProfile()),
          });
          if (!result.patient?.id) throw new Error("The profile response was incomplete.");
          createdPatient.current = result.patient.id;
          sessionStorage.setItem(storageKey, JSON.stringify({ patientId: result.patient.id }));
        } catch (error) {
          // A lost success response must not silently create another profile on retry.
          if (!(error instanceof ApiError) || error.status === 0 || error.status >= 500)
            setCreationUncertain(true);
          else sessionStorage.removeItem(storageKey);
          throw error;
        }
      }
      const current = await api<{ patient: Patient }>(`/api/patients/${encodeURIComponent(createdPatient.current)}`);
      if (current.patient.id !== createdPatient.current || current.patient.note !== PATIENT_DEMO_NOTE)
        throw new Error("This demo profile changed. Open the clinician demo to review it.");
      const { pairing } = await api<{ pairing: Pairing }>(
        `/api/patients/${encodeURIComponent(createdPatient.current)}/pairing`,
        { method: "POST", body: "{}" },
      );
      const token = pairing.code.replace(/[\s-]/g, "");
      if (!/^[A-Za-z0-9]{16,100}$/.test(token)) throw new Error("Could not open the demo pairing. Try again.");
      // Use the normal confirmation and server-issued patient capability.
      window.location.href = "/pair/" + encodeURIComponent(token);
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
      running.current = false;
    }
  }

  return (
    <section className="patient-demo-entry" aria-labelledby="patient-demo-heading">
      <h2 id="patient-demo-heading">Just trying iHear?</h2>
      <p>Create an example patient, then try the recording buttons and review the results. No QR code needed.</p>
      <button className="button full" onClick={start} disabled={disabled || busy || creationUncertain || !restored}>
        {busy ? "Preparing your demo…" : createdPatient.current ? "Continue to demo" : "Try patient demo"}
        <ArrowRight size={19} />
      </button>
      <p className="caption">Profile details are fictional. Recording starts only after you enable the microphone.</p>
      {error && <ErrorBox message={error} />}
      {creationUncertain && <p role="status" className="caption">The profile may have been saved. Check the clinician demo before creating another one.</p>}
      {(creationUncertain || (createdPatient.current && error)) && (
        <Link className="quiet-link" href={createdPatient.current ? `/clinic/patients/${createdPatient.current}` : "/clinic"}>Open clinician demo</Link>
      )}
    </section>
  );
}
