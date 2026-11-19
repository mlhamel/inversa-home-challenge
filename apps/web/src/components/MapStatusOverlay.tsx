import type { MapStatus } from "../lib/map-status";

const LABELS: Record<Exclude<MapStatus, "ready" | "error">, string> = {
  "loading-rows": "Loading available hours…",
  "loading-hour": "Loading this hour…",
  empty: "No activity observed this hour",
};

export default function MapStatusOverlay({ status }: { status: MapStatus }) {
  if (status === "ready" || status === "error") return null;
  const loading = status !== "empty";
  return (
    <p
      role="status"
      aria-live="polite"
      className="pointer-events-none absolute bottom-[232px] left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded panel border px-3 py-1.5 text-xs text-white/75"
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="h-3 w-3 animate-spin rounded-full border border-current border-t-transparent"
        />
      ) : null}
      {LABELS[status]}
    </p>
  );
}
