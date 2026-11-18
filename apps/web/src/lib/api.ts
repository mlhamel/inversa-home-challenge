import type { Snapshot, TimelineRow } from "./types";

export async function fetchTimelineSummary(
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<TimelineRow[]> {
  const params = new URLSearchParams({ start, end });
  const res = await fetch(`/api/timeline/summary?${params.toString()}`, { signal });
  if (!res.ok) throw new Error(`timeline summary failed: HTTP ${res.status}`);
  return (await res.json()) as TimelineRow[];
}

export async function fetchSnapshot(
  timestamp: string,
  signal?: AbortSignal,
): Promise<Snapshot> {
  const params = new URLSearchParams({ timestamp });
  const res = await fetch(`/api/snapshot?${params.toString()}`, { signal });
  if (!res.ok) throw new Error(`snapshot failed: HTTP ${res.status}`);
  return (await res.json()) as Snapshot;
}
