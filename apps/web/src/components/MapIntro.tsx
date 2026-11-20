import type { SnapshotRegion } from "../lib/types";

export default function MapIntro({
  regions,
}: {
  regions: readonly SnapshotRegion[] | null | undefined;
}) {
  const labels = (regions ?? []).map((region) => region.label);
  const count = labels.length;
  return (
    <aside
      aria-label="About the map"
      className="w-64 rounded-lg panel border px-3 py-2 text-xs text-white/70"
    >
      <p>
        Live wildfire detections (NASA FIRMS), downwind PM2.5 stations
        (OpenAQ), and surface wind (Open-Meteo) for the selected hour.
      </p>
      {count > 0 ? (
        <p className="mt-1.5">
          {`Watching ${count} focus ${count === 1 ? "area" : "areas"} (bbox outline${count === 1 ? "" : "s"}): ${labels.join(", ")}.`}
        </p>
      ) : null}
      <p className="mt-1.5">
        Scrub the timeline below, or click 💬 Ask the map (top-right) — ask the
        AI about what you see; it answers with data-backed evidence.
      </p>
    </aside>
  );
}
