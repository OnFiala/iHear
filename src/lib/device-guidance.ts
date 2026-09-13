import catalog from "../../config/device-capabilities.json";

export const supportedActionIds = [
  "allure_equalizer",
  "allure_direction_focus",
  "allure_programs",
] as const;
export type AllureActionId = (typeof supportedActionIds)[number];
export type DeviceAction = {
  id: AllureActionId;
  title: string;
  instruction: string;
  source: string;
  checkedAt: string;
};

type AidConfiguration = {
  side: "left" | "right" | "bilateral";
  left: { model: string; tier: string } | null;
  right: { model: string; tier: string } | null;
  app?: { name: string; version: string; confirmedActions: readonly string[] };
};

function verifiedCatalogAction(action: (typeof catalog.appActions)[number]): boolean {
  return (supportedActionIds as readonly string[]).includes(action.id) &&
    action.verificationStatus === "verified_app_control_requires_confirmation" &&
    action.supportedModels.includes(catalog.device);
}

export const actionOptions: DeviceAction[] = catalog.appActions.filter(verifiedCatalogAction).map((action) => ({
  id: action.id as AllureActionId,
  title: action.title,
  instruction: action.instruction,
  source: action.source,
  checkedAt: action.checkedAt,
}));

export function supportsAllureActions(aids: AidConfiguration): boolean {
  const worn = aids.side === "bilateral" ? [aids.left, aids.right]
    : aids.side === "left" ? [aids.left] : [aids.right];
  return worn.every((device) => device?.model === catalog.device && catalog.illustrativeTiers.includes(device.tier));
}

export function sameAppConfiguration(snapshot: AidConfiguration, current: AidConfiguration): boolean {
  const sameDevice = (left: typeof snapshot.left, right: typeof current.left) =>
    left?.model === right?.model && left?.tier === right?.tier;
  return snapshot.side === current.side && sameDevice(snapshot.left, current.left) &&
    sameDevice(snapshot.right, current.right) && snapshot.app?.name === current.app?.name &&
    snapshot.app?.version === current.app?.version &&
    JSON.stringify([...(snapshot.app?.confirmedActions ?? [])].sort()) ===
      JSON.stringify([...(current.app?.confirmedActions ?? [])].sort());
}

// Manufacturer app documentation plus a clinician's configuration confirmation
// establish availability. A model name or illustrative tier alone does not.
export function actionsForProfile(aids: AidConfiguration): DeviceAction[] {
  if (!supportsAllureActions(aids) || aids.app?.name !== "Widex Allure" || !aids.app.version?.trim()) return [];
  return actionOptions.filter((action) => aids.app?.confirmedActions.includes(action.id) &&
    catalog.appActions.some((record) => record.id === action.id && verifiedCatalogAction(record)));
}
