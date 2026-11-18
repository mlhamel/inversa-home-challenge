"use client";

import { badgeClass, formatHourUtc, pm25Color } from "../lib/theme";
import { evidenceFocusDate, type EvidenceRefs } from "../lib/evidence";
import type { Snapshot } from "../lib/types";

interface EvidenceInspectorProps {
  evidence: EvidenceRefs;
  snapshot: Snapshot | null;
  onClose: () => void;
}

export default function EvidenceInspector({
  evidence,
  snapshot,
  onClose,
}: EvidenceInspectorProps) {
  const focusDate = evidenceFocusDate({ ...evidence });
  const fires = evidence.fireIds
    .map((id) => ({ id, row: snapshot?.fires.find((f) => f.fire_id === id) ?? null }))
    .slice(0, 5);
  const stations = evidence.stationIds
    .map((id) => ({ id, row: snapshot?.stations.find((s) => s.station_id === id) ?? null }))
    .slice(0, 5);
  const hiddenFires = Math.max(0, evidence.fireIds.length - fires.length);
  const hiddenStations = Math.max(0, evidence.stationIds.length - stations.length);

  return (
    <aside className="absolute left-3 top-3 z-20 w-80 max-w-[calc(100vw-1.5rem)] rounded-lg panel border p-3 text-xs">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Evidence</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close evidence panel"
          className="rounded px-1.5 py-0.5 text-white/60 hover:bg-white/10 hover:text-white"
        >
          ✕
        </button>
      </div>
      {focusDate === null ? null : (
        <p className="mt-1 text-white/60">Focus: {formatHourUtc(focusDate.toISOString())}</p>
      )}

      {fires.length === 0 ? null : (
        <ul className="mt-2 space-y-1.5">
          {fires.map(({ id, row }) => (
            <li key={id} className="rounded border border-white/10 bg-white/5 px-2 py-1">
              <span className="font-medium">🔥 {row?.fire_id ?? id}</span>
              {row === null ? (
                <span className="text-white/45"> · not in current snapshot</span>
              ) : (
                <span className="text-white/70">
                  {" "}
                  · FRP {row.frp === null ? "—" : row.frp.toFixed(1)}
                  {" · "}
                  {row.satellite}
                </span>
              )}
            </li>
          ))}
          {hiddenFires > 0 ? <li className="text-white/45">+{hiddenFires} more fires</li> : null}
        </ul>
      )}

      {stations.length === 0 ? null : (
        <ul className="mt-2 space-y-1.5">
          {stations.map(({ id, row }) => (
            <li key={id} className="rounded border border-white/10 bg-white/5 px-2 py-1">
              {row === null ? (
                <span className="text-white/45">📡 {id} · not in current snapshot</span>
              ) : (
                <>
                  <span className="inline-block h-2 w-2 rounded-full align-middle" style={{ backgroundColor: pm25Color(row.pm25) }} />
                  <span className="ml-1.5 font-medium">{row.station_name}</span>
                  <span className="text-white/70">
                    {" "}
                    · PM2.5 {row.pm25 === null ? "—" : row.pm25.toFixed(1)} µg/m³ · observed{" "}
                    {formatHourUtc(row.observed_at)}
                  </span>
                  <span className={`ml-1.5 inline-block rounded-full border px-1.5 py-px ${badgeClass(row.quality_flag)}`}>
                    {row.quality_flag}
                  </span>
                </>
              )}
            </li>
          ))}
          {hiddenStations > 0 ? (
            <li className="text-white/45">+{hiddenStations} more stations</li>
          ) : null}
        </ul>
      )}

      <p className="mt-2 text-white/45">Highlighted items pulse on the map.</p>
    </aside>
  );
}
