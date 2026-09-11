import "server-only";
import { z } from "zod";
import type { ProfileInput } from "@/lib/types";
import { HttpError } from "./http";

const finiteNumber = z.number().finite();
const device = z.object({
  model: z.string().trim().min(1).max(160),
  tier: z.string().trim().min(1).max(80),
});

export const profileSchema = z
  .object({
    displayName: z.string().trim().min(1).max(120),
    audiogram: z.object({
      frequencies: z.array(finiteNumber).min(1).max(32),
      left: z.array(finiteNumber).min(1).max(32),
      right: z.array(finiteNumber).min(1).max(32),
    }),
    aids: z.object({
      side: z.enum(["left", "right", "bilateral"]),
      left: device.nullable(),
      right: device.nullable(),
    }),
    followUpDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    note: z.string().trim().max(4000),
    timezone: z.string().trim().min(1).max(80),
  })
  .superRefine((value, context) => {
    const count = value.audiogram.frequencies.length;
    if (
      value.audiogram.left.length !== count ||
      value.audiogram.right.length !== count
    ) {
      context.addIssue({
        code: "custom",
        path: ["audiogram"],
        message: "Audiogram arrays must have matching lengths.",
      });
    }
    for (let index = 1; index < count; index += 1) {
      if (
        value.audiogram.frequencies[index] <=
        value.audiogram.frequencies[index - 1]
      ) {
        context.addIssue({
          code: "custom",
          path: ["audiogram", "frequencies"],
          message: "Frequencies must be strictly increasing.",
        });
        break;
      }
    }
    if (value.aids.side === "left" && (!value.aids.left || value.aids.right))
      context.addIssue({
        code: "custom",
        path: ["aids"],
        message: "Left-side configuration is inconsistent.",
      });
    if (value.aids.side === "right" && (!value.aids.right || value.aids.left))
      context.addIssue({
        code: "custom",
        path: ["aids"],
        message: "Right-side configuration is inconsistent.",
      });
    if (
      value.aids.side === "bilateral" &&
      (!value.aids.left || !value.aids.right)
    )
      context.addIssue({
        code: "custom",
        path: ["aids"],
        message: "Bilateral configuration requires both devices.",
      });
    const followUp = new Date(`${value.followUpDate}T00:00:00Z`);
    if (
      Number.isNaN(followUp.valueOf()) ||
      followUp.toISOString().slice(0, 10) !== value.followUpDate
    ) {
      context.addIssue({
        code: "custom",
        path: ["followUpDate"],
        message: "Follow-up date is invalid.",
      });
    }
    try {
      new Intl.DateTimeFormat("en", { timeZone: value.timezone }).format();
    } catch {
      context.addIssue({
        code: "custom",
        path: ["timezone"],
        message: "Timezone is invalid.",
      });
    }
  });

const captureSchema = z.object({
  sampleRate: z.number().int().min(8_000).max(192_000),
  preSeconds: z.number().finite().min(0).max(10.1),
  postSeconds: z.number().finite().min(0).max(10.1),
  trackSettings: z.record(z.string(), z.unknown()),
  sourceLabel: z.string().trim().min(1).max(160),
  routing: z.enum(["unknown", "phone-confirmed"]),
  interrupted: z.boolean(),
});

export const eventMetadataSchema = z
  .object({
    id: z.string().uuid(),
    patientId: z.string().uuid(),
    kind: z.enum(["understood", "difficult"]),
    difficulty: z.string().trim().min(1).max(160).nullable(),
    environment: z.string().trim().min(1).max(160).nullable(),
    capturedAt: z.iso.datetime({ offset: true }),
    capture: captureSchema,
  })
  .superRefine((value, context) => {
    if (
      value.kind === "difficult" &&
      (!value.difficulty || !value.environment)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Difficulty and environment are required for a difficult event.",
      });
    }
    if (
      value.kind === "understood" &&
      (value.difficulty !== null || value.environment !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Understood events cannot include difficulty answers.",
      });
    }
  });

function parse<T>(schema: z.ZodType<T>, value: unknown, message: string): T {
  const result = schema.safeParse(value);
  if (!result.success)
    throw new HttpError(400, result.error.issues[0]?.message ?? message);
  return result.data;
}

export function parseProfile(value: unknown): ProfileInput {
  return parse(
    profileSchema,
    value,
    "The patient profile is invalid.",
  ) as ProfileInput;
}

export type EventMetadata = z.infer<typeof eventMetadataSchema>;

export function parseEventMetadata(value: unknown): EventMetadata {
  return parse(eventMetadataSchema, value, "The event metadata is invalid.");
}

const uuidSchema = z.string().uuid();

export function parseUuid(value: string, label: string): string {
  const result = uuidSchema.safeParse(value);
  if (!result.success) throw new HttpError(400, `${label} is invalid.`);
  return result.data;
}

export function parsePatientFilters(searchParams: URLSearchParams): {
  q?: string;
  status?: string;
  difficulty?: string;
  followUp?: string;
} {
  const q = searchParams.get("q")?.trim() || undefined;
  const status = searchParams.get("status")?.trim() || undefined;
  const difficulty = searchParams.get("difficulty")?.trim() || undefined;
  const followUp = searchParams.get("followUp")?.trim() || undefined;
  if (q && q.length > 200)
    throw new HttpError(400, "Search query is too long.");
  if (
    status &&
    !["uploading", "queued", "analysing", "ready", "failed"].includes(status)
  )
    throw new HttpError(400, "Status filter is invalid.");
  if (difficulty && difficulty.length > 160)
    throw new HttpError(400, "Difficulty filter is too long.");
  if (followUp && !["overdue", "today", "upcoming"].includes(followUp)) {
    const date = new Date(`${followUp}T00:00:00Z`);
    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(followUp) ||
      Number.isNaN(date.valueOf()) ||
      date.toISOString().slice(0, 10) !== followUp
    ) {
      throw new HttpError(400, "Follow-up filter is invalid.");
    }
  }
  return { q, status, difficulty, followUp };
}
