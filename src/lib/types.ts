export type ProfileInput = {
  displayName: string;
  audiogram: { frequencies: number[]; left: number[]; right: number[] };
  aids: {
    side: "left" | "right" | "bilateral";
    left: { model: string; tier: string } | null;
    right: { model: string; tier: string } | null;
    app?: {
      name: "Widex Allure";
      version: string;
      confirmedActions: Array<
        | "allure_equalizer"
        | "allure_direction_focus"
        | "allure_programs"
      >;
    };
  };
  followUpDate: string;
  note: string;
  timezone: string;
};
export type Patient = ProfileInput & {
  id: string;
  workspaceId: string;
  createdAt: string;
  eventCount?: number;
  latestStatus?: string;
};
export type Analysis = {
  duration_seconds: number;
  sample_rate: number;
  rms_dbfs: number | null;
  peak_dbfs: number | null;
  clipping_fraction: number;
  silent: boolean;
  quality_flags: string[];
  bands: { low_hz: number; high_hz: number; relative_energy: number }[];
  spectral_centroid_hz: number;
  level_timeline?: {
    start_seconds: number;
    end_seconds: number;
    rms_dbfs: number | null;
    peak_dbfs: number | null;
    clipping_fraction: number;
  }[];
  speech_activity: {
    status: string;
    fraction?: number;
    aggregation?: string;
    mean_probability?: number;
    threshold?: number;
    model?: string;
    version?: string;
    windows?: {
      start_seconds: number;
      end_seconds: number;
      active_fraction: number;
      mean_probability: number;
    }[];
  };
  acoustic_categories: {
    status: string;
    categories?: { label: string; score: number }[];
    model?: string;
    version?: string;
    aggregation?: string;
    frame_window_seconds?: number;
    frame_hop_seconds?: number;
    windows?: {
      start_seconds: number;
      end_seconds: number;
      categories: { label: string; score: number }[];
    }[];
  };
};
export type ListeningEvent = {
  id: string;
  patientId: string;
  kind: "understood" | "difficult";
  difficulty: string | null;
  environment: string | null;
  capturedAt: string;
  createdAt: string;
  status: string;
  capture: Record<string, unknown>;
  profileSnapshot: ProfileInput;
  currentAids?: ProfileInput["aids"];
  analysis: Analysis | null;
  interpretation: {
    status: string;
    promptVersion?: string;
    model?: string;
    result: {
      summary?: string;
      observations?: string[];
      tip_ids?: string[];
      limitations?: string[];
      recommendations?: { text: string; evidence_refs: string[] }[];
      frequency_notes?: {
        band_index: number;
        explanation: string;
        review_question: string;
      }[];
      patient_summary?: string;
      device_action_ids?: string[];
      device_actions?: {
        id: string;
        title: string;
        instruction: string;
        source: string;
        checkedAt: string;
      }[];
    } | null;
  } | null;
  error?: string | null;
};
export type Pairing = { url: string; code: string; expiresAt: string };
export const difficulties = [
  "Following one person",
  "Several people talking",
  "Sound was uncomfortable",
  "Something else",
] as const;
export const environments = [
  "Quiet",
  "Background conversation",
  "Music or TV",
  "Traffic or machinery",
  "Not sure",
] as const;
export const frequencies = [250, 500, 1000, 2000, 4000, 8000];
export const tips: Record<string, string> = {
  face_speaker: "If it helps, face the person you are listening to.",
  quieter_place: "If you can, move to a quieter place.",
  take_break: "It is okay to take a short listening break.",
  ask_repeat: "You can ask someone to repeat or rephrase.",
  share_clinician: "Share this moment at your next appointment.",
};
