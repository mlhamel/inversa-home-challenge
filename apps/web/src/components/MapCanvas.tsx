"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { Map as MapLibre } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { IconLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import {
  clamp,
  FIRE_FILL_ALPHA,
  FIRE_FILL_COLOR,
  FIRE_LOW_CONFIDENCE_ALPHA,
  FIRE_OUTLINE_COLOR,
  OUTLIER_RING_COLOR,
  pm25DeckColor,
  STALE_RING_COLOR,
  STATION_OUTLINE_COLOR,
  WIND_COLOR,
} from "../lib/theme";
import type {
  Snapshot,
  SnapshotFireRow,
  SnapshotStationRow,
  SnapshotWindRow,
} from "../lib/types";

const DEFAULT_MAP_STYLE =
  process.env.NEXT_PUBLIC_MAP_STYLE ??
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const ICON_SIZE = 72;
const ARROW_KEY = "wind-arrow";
const RING_KEY = "flag-ring";

export interface MapPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

interface MapCanvasProps {
  snapshot: Snapshot | null;
  highlightedFireIds: ReadonlySet<string>;
  highlightedStationIds: ReadonlySet<string>;
  focusPoint: { lat: number; lon: number } | null;
  bounds: [[number, number], [number, number]] | null;
  padding: MapPadding;
}

interface TooltipDatum extends Partial<SnapshotFireRow>, Partial<SnapshotStationRow> {}

function buildIconAtlas(): HTMLCanvasElement | null {
  const canvas = document.createElement("canvas");
  canvas.width = ICON_SIZE * 2;
  canvas.height = ICON_SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.moveTo(ICON_SIZE / 2, 10);
  ctx.lineTo(ICON_SIZE - 14, 40);
  ctx.lineTo(ICON_SIZE / 2 + 6, 35);
  ctx.lineTo(ICON_SIZE / 2 + 6, 62);
  ctx.lineTo(ICON_SIZE / 2 - 6, 62);
  ctx.lineTo(ICON_SIZE / 2 - 6, 35);
  ctx.lineTo(14, 40);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = "rgba(10, 14, 20, 0.85)";
  ctx.lineWidth = 3;
  ctx.stroke();
  ctx.save();
  ctx.translate(ICON_SIZE, 0);
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 5;
  ctx.setLineDash([9, 8]);
  ctx.beginPath();
  ctx.arc(ICON_SIZE / 2, ICON_SIZE / 2, ICON_SIZE / 2 - 7, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
  return canvas;
}

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export default function MapCanvas({
  snapshot,
  highlightedFireIds,
  highlightedStationIds,
  focusPoint,
  bounds,
  padding,
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const movedRef = useRef(false);
  const autoFitDoneRef = useRef(false);
  const [atlas, setAtlas] = useState<HTMLCanvasElement | null>(null);
  const [pulsePhase, setPulsePhase] = useState(0);

  useEffect(() => {
    setAtlas(buildIconAtlas());
  }, []);

  const hasHighlights =
    highlightedFireIds.size > 0 || highlightedStationIds.size > 0;

  useEffect(() => {
    if (!hasHighlights) return;
    const id = window.setInterval(() => setPulsePhase((p) => (p + 1) % 8), 120);
    return () => window.clearInterval(id);
  }, [hasHighlights]);

  useEffect(() => {
    if (!containerRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DEFAULT_MAP_STYLE,
      center: [-100, 39],
      zoom: 3.4,
      attributionControl: { compact: true },
    });
    const overlay = new MapboxOverlay({ layers: [] });
    map.addControl(overlay as unknown as maplibregl.IControl);
    map.on("error", (event: maplibregl.ErrorEvent) => {
      console.error("maplibre error", event.error ?? event);
    });
    map.on("dragstart", () => {
      movedRef.current = true;
    });
    mapRef.current = map;
    overlayRef.current = overlay;
    return () => {
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (focusPoint) {
      mapRef.current?.flyTo({
        center: [focusPoint.lon, focusPoint.lat],
        zoom: 10.5,
        duration: 900,
      });
    }
  }, [focusPoint]);

  useEffect(() => {
    if (bounds) {
      mapRef.current?.fitBounds(bounds, { padding, duration: 900 });
    }
  }, [bounds, padding]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !snapshot || autoFitDoneRef.current || movedRef.current) return;
    if (map.loaded() && (snapshot.stations.length > 0 || snapshot.fires.length > 0)) {
      const lons: number[] = [];
      const lats: number[] = [];
      for (const s of snapshot.stations) {
        lons.push(s.lon);
        lats.push(s.lat);
      }
      for (const f of snapshot.fires) {
        lons.push(f.lon);
        lats.push(f.lat);
      }
      if (lons.length > 0) {
        autoFitDoneRef.current = true;
        map.fitBounds(
          [
            [Math.min(...lons), Math.min(...lats)],
            [Math.max(...lons), Math.max(...lats)],
          ],
          { padding, duration: 900 },
        );
      }
    }
  }, [snapshot, padding]);

  const pulseScale = 1 + 0.38 * Math.sin((pulsePhase / 7) * Math.PI * 2);

  const baseLayers = useMemo(() => {
    const stations = snapshot?.stations ?? [];
    const fires = snapshot?.fires ?? [];
    const wind = snapshot?.wind ?? [];
    const flagged = stations.filter(
      (s) => s.quality_flag === "stale" || s.quality_flag === "outlier",
    );
    const flagRing =
      atlas === null
        ? null
        : new IconLayer<SnapshotStationRow>({
            id: "flagged-stations",
            data: flagged,
            pickable: true,
            iconAtlas: atlas as unknown as string,
            iconMapping: {
              [RING_KEY]: {
                x: ICON_SIZE,
                y: 0,
                width: ICON_SIZE,
                height: ICON_SIZE,
                anchorX: ICON_SIZE / 2,
                anchorY: ICON_SIZE / 2,
                mask: true,
              },
            },
            getIcon: () => RING_KEY,
            getPosition: (d) => [d.lon, d.lat],
            sizeUnits: "pixels",
            getSize: 26,
            getColor: (d) =>
              d.quality_flag === "outlier" ? OUTLIER_RING_COLOR : STALE_RING_COLOR,
            updateTriggers: {
              getSize: atlas,
              getIcon: atlas,
            },
          });
    return [
      new IconLayer<SnapshotWindRow>({
        id: "wind-vectors",
        data: wind,
        visible: atlas !== null,
        iconAtlas: (atlas ?? undefined) as unknown as string,
        iconMapping: {
          [ARROW_KEY]: {
            x: 0,
            y: 0,
            width: ICON_SIZE,
            height: ICON_SIZE,
            anchorX: ICON_SIZE / 2,
            anchorY: ICON_SIZE / 2,
            mask: true,
          },
        },
        getIcon: () => ARROW_KEY,
        getPosition: (d) => [d.lon, d.lat],
        sizeUnits: "pixels",
        getSize: (d) =>
          clamp(
            12 + (d.wind_speed_10m === null ? 0 : Math.sqrt(d.wind_speed_10m) * 6),
            12,
            30,
          ),
        getAngle: (d) =>
          (360 - (((d.wind_direction_10m ?? 0) + 180) % 360)) % 360,
        getColor: [...WIND_COLOR, 210],
        opacity: 0.85,
        updateTriggers: {
          getIcon: atlas,
          getSize: atlas,
        },
      }),
      new ScatterplotLayer<SnapshotFireRow>({
        id: "fires",
        data: fires,
        pickable: true,
        radiusUnits: "meters",
        radiusMinPixels: 3,
        radiusMaxPixels: 60,
        getPosition: (d) => [d.lon, d.lat],
        getRadius: (d) => 600 + Math.sqrt(Math.max(d.frp ?? 8, 8)) * 260,
        getFillColor: (d) => [
          ...FIRE_FILL_COLOR,
          d.confidence === "low" ? FIRE_LOW_CONFIDENCE_ALPHA : FIRE_FILL_ALPHA,
        ],
        getLineColor: FIRE_OUTLINE_COLOR,
        lineWidthMinPixels: 1,
      }),
      new ScatterplotLayer<SnapshotStationRow>({
        id: "stations",
        data: stations,
        pickable: true,
        radiusUnits: "pixels",
        radiusMinPixels: 4,
        radiusMaxPixels: 7,
        getPosition: (d) => [d.lon, d.lat],
        getFillColor: (d) => pm25DeckColor(d.pm25),
        getLineColor: STATION_OUTLINE_COLOR,
        lineWidthMinPixels: 1,
      }),
      ...(flagRing ? [flagRing] : []),
    ];
  }, [snapshot, atlas]);

  const pulseLayers = useMemo(() => {
    if (!snapshot || !hasHighlights) return [];
    const evidenceFires = snapshot.fires.filter((f) =>
      highlightedFireIds.has(f.fire_id),
    );
    const evidenceStations = snapshot.stations.filter((s) =>
      highlightedStationIds.has(s.station_id),
    );
    return [
      new ScatterplotLayer<SnapshotFireRow>({
        id: "fire-pulse",
        data: evidenceFires,
        stroked: true,
        filled: false,
        radiusUnits: "meters",
        radiusMinPixels: 8,
        lineWidthUnits: "pixels",
        lineWidthMinPixels: 2,
        getPosition: (d) => [d.lon, d.lat],
        getRadius: 1500,
        radiusScale: pulseScale,
        getLineColor: [255, 170, 66, 220],
        updateTriggers: { radiusScale: pulsePhase },
      }),
      new ScatterplotLayer<SnapshotStationRow>({
        id: "station-pulse",
        data: evidenceStations,
        stroked: true,
        filled: false,
        radiusUnits: "meters",
        radiusMinPixels: 10,
        lineWidthUnits: "pixels",
        lineWidthMinPixels: 2,
        getPosition: (d) => [d.lon, d.lat],
        getRadius: 900,
        radiusScale: pulseScale,
        getLineColor: [126, 216, 247, 220],
        updateTriggers: { radiusScale: pulsePhase },
      }),
    ];
  }, [
    snapshot,
    hasHighlights,
    highlightedFireIds,
    highlightedStationIds,
    pulseScale,
    pulsePhase,
  ]);

  const getTooltip = useCallback((info: PickingInfo) => {
    const d = info.object as TooltipDatum | null;
    if (!d || !info.layer) return null;
    const name = escapeHtml(d.station_name ?? d.fire_id ?? "");
    if (info.layer.id === "stations" || info.layer.id === "flagged-stations") {
      const flag = d.quality_flag ?? "valid";
      const lines = [`<strong>${name}</strong> · ${d.pm25 ?? "—"} µg/m³ PM2.5`];
      if (flag === "stale") {
        lines.push(
          `<span>⚠ Stale data — last observed ${escapeHtml(d.observed_at ?? "")}</span>`,
        );
      } else if (flag === "outlier") {
        lines.push("<span>⚠ Flagged as statistical outlier</span>");
      }
      return { html: lines.join("<br/>") };
    }
    if (info.layer.id === "fires") {
      return {
        html: `<strong>${name}</strong><br/>frp ${d.frp ?? "—"}${d.satellite ? ` · ${escapeHtml(d.satellite)}` : ""}`,
      };
    }
    return null;
  }, []);

  useEffect(() => {
    overlayRef.current?.setProps({
      layers: [...pulseLayers, ...baseLayers],
      getTooltip,
    });
  }, [baseLayers, pulseLayers, getTooltip]);

  return (
    <div className="absolute inset-0">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
