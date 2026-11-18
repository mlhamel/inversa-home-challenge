"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TimelineRow } from "../lib/types";
import { clamp, formatHourUtc } from "../lib/theme";

interface TimelineDockProps {
  rows: TimelineRow[];
  selectedHour: string | null;
  onSelectHour: (hour: string) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
}

const PLOT_TOP = 14;
const PLOT_HEIGHT = 84;
const PAD_X = 12;
const BASE_Y = PLOT_TOP + PLOT_HEIGHT;
const SVG_HEIGHT = BASE_Y + 16;
const PLAY_STEP_MS = 800;
const LATENCY_MS = 3 * 3_600_000;

const TICK_FORMAT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

export default function TimelineDock({
  rows,
  selectedHour,
  onSelectHour,
  playing,
  onPlayingChange,
}: TimelineDockProps) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const draggingRef = useRef(false);
  const selectedRef = useRef(selectedHour);
  const [width, setWidth] = useState(0);

  const n = rows.length;
  const selectedIdx = rows.findIndex((r) => r.hour_bucket === selectedHour);
  const selected = selectedIdx >= 0 ? rows[selectedIdx] : null;

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      setWidth(Math.round(w));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    selectedRef.current = selectedHour;
  }, [selectedHour]);

  useEffect(() => {
    if (!playing || n === 0) return;
    const id = window.setInterval(() => {
      const current = selectedRef.current;
      let idx = rows.findIndex((r) => r.hour_bucket === current);
      if (idx < 0) idx = n - 1;
      const nextIdx = Math.min(n - 1, idx + 1);
      onSelectHour(rows[nextIdx].hour_bucket);
      if (nextIdx >= n - 1) onPlayingChange(false);
    }, PLAY_STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, rows, n, onSelectHour, onPlayingChange]);

  const geometry = useMemo(() => {
    if (n === 0 || width <= 2 * PAD_X + 20) return null;
    const innerW = width - 2 * PAD_X;
    const xFor = (i: number) => PAD_X + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW);
    const pm25Domain = Math.max(5, ...rows.map((r) => r.max_pm25 ?? 0));
    const countDomain = Math.max(1, ...rows.map((r) => r.active_fires_count));
    const yForPm25 = (v: number) => PLOT_TOP + (1 - v / pm25Domain) * PLOT_HEIGHT;
    const yForCount = (v: number) => PLOT_TOP + (1 - v / countDomain) * PLOT_HEIGHT;
    const line = (
      get: (r: TimelineRow) => number | null,
      yFor: (v: number) => number,
    ): string => {
      const segments: string[] = [];
      let current: string[] = [];
      rows.forEach((row, i) => {
        const value = get(row);
        if (value === null || value === undefined) {
          if (current.length > 1) segments.push(current.join(" "));
          current = [];
        } else {
          current.push(
            `${current.length === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(value).toFixed(1)}`,
          );
        }
      });
      if (current.length > 1) segments.push(current.join(" "));
      return segments.join(" ");
    };
    const latencyIdx = (() => {
      const cutoff = new Date(rows[n - 1].hour_bucket).getTime() - LATENCY_MS;
      const found = rows.findIndex((r) => new Date(r.hour_bucket).getTime() >= cutoff);
      return found < 0 ? 0 : found;
    })();
    return {
      innerW,
      xFor,
      yForPm25,
      yForCount,
      pm25Domain,
      countDomain,
      latencyIdx,
      avgLine: line((r) => r.avg_pm25, yForPm25),
      maxLine: line((r) => r.max_pm25, yForPm25),
      fireLine: line((r) => r.active_fires_count, yForCount),
      fireArea: (() => {
        if (rows.every((r) => r.active_fires_count === 0)) return "";
        const points = rows
          .map((r, i) => `L${xFor(i).toFixed(1)},${yForCount(r.active_fires_count).toFixed(1)}`)
          .join(" ");
        return `M${xFor(0).toFixed(1)},${BASE_Y} ${points} L${xFor(n - 1).toFixed(1)},${BASE_Y} Z`;
      })(),
      ticks: rows
        .map((r, i) => ({ i, bucket: r.hour_bucket }))
        .filter(({ i }) => i % 24 === 0),
      latestHour: rows[n - 1].hour_bucket,
    };
  }, [rows, n, width]);

  const selectAt = useCallback(
    (clientX: number) => {
      const svg = svgRef.current;
      if (!svg || n === 0 || geometry === null) return;
      const rect = svg.getBoundingClientRect();
      const t = (clientX - rect.left - PAD_X) / Math.max(1, rect.width - 2 * PAD_X);
      const idx = clamp(Math.round(t * (n - 1)), 0, n - 1);
      onSelectHour(rows[idx].hour_bucket);
    },
    [n, rows, onSelectHour, geometry],
  );

  const shadeLeft = geometry ? geometry.xFor(geometry.latencyIdx) : 0;
  const shadeWidth = geometry ? Math.max(0, geometry.xFor(n - 1) - shadeLeft) : 0;
  const scrubberX = geometry && selectedIdx >= 0 ? geometry.xFor(selectedIdx) : null;

  return (
    <section className="absolute inset-x-0 bottom-0 z-20 flex h-[190px] flex-col panel border-t px-4 pb-2.5 pt-2.5">
      <div className="flex items-baseline gap-3 text-xs sm:text-sm">
        <button
          type="button"
          onClick={() => onPlayingChange(!playing)}
          disabled={n === 0}
          className="shrink-0 rounded border border-white/15 px-2.5 py-1 hover:bg-white/10 disabled:opacity-40"
        >
          {playing ? "⏸ Pause" : "▶ Play"}
        </button>
        <div className="min-w-0 truncate text-white/85">
          {selected === null ? (
            <span className="text-white/50">Drag along the timeline to pick an hour…</span>
          ) : (
            <span>
              <span className="font-medium">{formatHourUtc(selected.hour_bucket)}</span>
              <span className="text-white/60">
                {" "}
                · fires {selected.active_fires_count} · PM2.5{" "}
                {selected.avg_pm25 === null ? "—" : selected.avg_pm25.toFixed(1)}
                {" / "}
                {selected.max_pm25 === null ? "—" : selected.max_pm25.toFixed(1)} µg/m³ · stations{" "}
                {selected.active_stations} ({selected.stale_stations} stale)
              </span>
            </span>
          )}
        </div>
        <div className="ml-auto hidden shrink-0 items-center gap-2.5 text-[11px] text-white/60 md:flex">
          <span><span className="text-[#ff5630]">▬</span> fires</span>
          <span><span className="text-[#58c7f5]">▬</span> PM2.5 avg</span>
          <span><span className="text-[#b07cff]">▬</span> PM2.5 max</span>
          <span>▨ ~3h FIRMS latency</span>
        </div>
      </div>

      <div ref={wrapRef} className="mt-2 min-h-0 flex-1">
        {n === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-white/50">
            No timeline data yet — run ingestion, then reload.
          </p>
        ) : geometry === null ? (
          <p className="flex h-full items-center justify-center text-sm text-white/50">
            Sizing timeline…
          </p>
        ) : (
          <svg
            ref={svgRef}
            width={width}
            height={SVG_HEIGHT}
            className="block cursor-crosshair select-none touch-none"
            role="slider"
            aria-label="Timeline scrubber"
            aria-valuemin={1}
            aria-valuemax={n}
            aria-valuenow={selectedIdx + 1}
            aria-valuetext={selected ? formatHourUtc(selected.hour_bucket) : undefined}
            onPointerDown={(e) => {
              draggingRef.current = true;
              e.currentTarget.setPointerCapture(e.pointerId);
              selectAt(e.clientX);
            }}
            onPointerMove={(e) => {
              if (draggingRef.current) selectAt(e.clientX);
            }}
            onPointerUp={(e) => {
              draggingRef.current = false;
              e.currentTarget.releasePointerCapture(e.pointerId);
            }}
            onPointerCancel={() => {
              draggingRef.current = false;
            }}
          >
            <defs>
              <pattern
                id="latency-hatch"
                width={8}
                height={8}
                patternUnits="userSpaceOnUse"
                patternTransform="rotate(45)"
              >
                <line x1={0} y1={0} x2={0} y2={8} stroke="#a8b2bc" strokeOpacity={0.35} strokeWidth={1.5} />
              </pattern>
            </defs>
            <line
              x1={PAD_X}
              x2={width - PAD_X}
              y1={BASE_Y}
              y2={BASE_Y}
              stroke="rgba(255,255,255,0.18)"
            />
            {geometry.fireArea === "" ? null : (
              <path d={geometry.fireArea} fill="rgba(255,86,48,0.16)" />
            )}
            {geometry.fireLine === "" ? null : (
              <path d={geometry.fireLine} stroke="#ff5630" fill="none" strokeWidth={1.5} />
            )}
            {geometry.maxLine === "" ? null : (
              <path
                d={geometry.maxLine}
                stroke="#b07cff"
                fill="none"
                strokeWidth={1.4}
                strokeDasharray="4 3"
              />
            )}
            {geometry.avgLine === "" ? null : (
              <path d={geometry.avgLine} stroke="#58c7f5" fill="none" strokeWidth={1.6} />
            )}
            {shadeWidth < 4 ? null : (
              <>
                <rect x={shadeLeft} y={PLOT_TOP} width={shadeWidth} height={PLOT_HEIGHT} fill="url(#latency-hatch)" />
                {shadeWidth > 78 ? (
                  <text x={shadeLeft + 6} y={PLOT_TOP + 12} fontSize={9} fill="rgba(255,255,255,0.55)">
                    FIRMS ≈3h latency
                  </text>
                ) : null}
              </>
            )}
            {geometry.ticks.map(({ i, bucket }) => (
              <text
                key={bucket}
                x={geometry.xFor(i)}
                y={SVG_HEIGHT - 4}
                fontSize={9}
                fill="rgba(255,255,255,0.45)"
                textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}
              >
                {TICK_FORMAT.format(new Date(bucket))}
              </text>
            ))}
            {scrubberX === null ? null : (
              <>
                <line x1={scrubberX} x2={scrubberX} y1={PLOT_TOP} y2={BASE_Y} stroke="#e6e9ef" strokeOpacity={0.85} />
                <circle
                  cx={scrubberX}
                  cy={PLOT_TOP + PLOT_HEIGHT / 2}
                  r={5}
                  fill="#e6e9ef"
                  stroke="#0a0e14"
                  strokeWidth={2}
                />
              </>
            )}
          </svg>
        )}
      </div>
    </section>
  );
}
