export function qualityFlagLabel(flag: string): string {
  const labels: Record<string, string> = {
    very_quiet: "Weak digital signal in this recording",
    weak_digital_signal: "Weak digital signal in this recording",
    silence: "Signal at or below the digital-silence threshold in this recording",
    clipping: "Waveform reaches the digital recording limit",
    too_short: "Recording is too short for a stable summary",
  };
  return labels[flag] ?? `Recording flag: ${flag.replaceAll("_", " ")}`;
}

export function modelStatus(status: string | undefined): string {
  return (status || "not stored").replaceAll("_", " ");
}

export function digitalLevelHeight(dbfs: number | null): number {
  if (dbfs === null || !Number.isFinite(dbfs)) return 0;
  return Math.max(1, Math.min(100, ((dbfs + 80) / 80) * 100));
}

export function captureSetting(
  capture: Record<string, unknown>,
  key: "echoCancellation" | "noiseSuppression" | "autoGainControl",
): boolean | null {
  const settings = capture.trackSettings;
  if (!settings || typeof settings !== "object") return null;
  const value = (settings as Record<string, unknown>)[key];
  return typeof value === "boolean" ? value : null;
}

export function captureText(
  capture: Record<string, unknown>,
  key: "sourceLabel",
): string | null {
  const value = capture[key];
  return typeof value === "string" && value.trim() ? value : null;
}

export function settingLabel(value: boolean | null): string {
  return value === null ? "Not reported" : value ? "On" : "Off";
}
