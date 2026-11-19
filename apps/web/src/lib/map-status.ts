import type { Snapshot } from "./types";

export type MapStatus = "loading-rows" | "loading-hour" | "empty" | "ready" | "error";

export interface MapStatusInput {
  rowsError: string | null;
  selectedHour: string | null;
  snapshot: Snapshot | null;
  snapshotError: string | null;
}

export function deriveMapStatus(input: MapStatusInput): MapStatus {
  if (input.snapshotError !== null || input.rowsError !== null) return "error";
  if (input.selectedHour === null) return "loading-rows";
  if (input.snapshot === null) return "loading-hour";
  return input.snapshot.fires.length === 0 && input.snapshot.stations.length === 0
    ? "empty"
    : "ready";
}
