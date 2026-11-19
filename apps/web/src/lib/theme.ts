export const PM25_NO_DATA_COLOR = "#9aa4ae";

interface AqiStop {
  limit: number;
  color: string;
  label: string;
  range: string;
}

export const PM25_AQI_STOPS: ReadonlyArray<AqiStop> = [
  { limit: 12, color: "#17a05a", label: "Good", range: "≤ 12" },
  { limit: 35.4, color: "#f5d90a", label: "Moderate", range: "12–35" },
  { limit: 55.4, color: "#ff7e00", label: "Unhealthy for sensitive groups", range: "35–55" },
  { limit: 150.4, color: "#ff2e2e", label: "Unhealthy", range: "55–150" },
  { limit: 250.4, color: "#a845c4", label: "Very unhealthy", range: "150–250" },
  { limit: Number.POSITIVE_INFINITY, color: "#7e0023", label: "Hazardous", range: "> 250" },
];

export const STALE_RING_COLOR: [number, number, number] = [168, 178, 188];
export const OUTLIER_RING_COLOR: [number, number, number] = [196, 150, 255];
export const FIRE_FILL_COLOR: [number, number, number] = [255, 86, 48];
export const FIRE_FILL_ALPHA = 230;
export const FIRE_LOW_CONFIDENCE_ALPHA = 140;
export const FIRE_OUTLINE_COLOR: [number, number, number] = [255, 176, 92];
export const STATION_OUTLINE_COLOR: [number, number, number] = [10, 14, 20];
export const WIND_COLOR: [number, number, number] = [143, 214, 249];

export const REGION_HUES: ReadonlyArray<[number, number, number]> = [
  [64, 224, 200],
  [186, 118, 255],
  [128, 222, 122],
  [255, 122, 158],
];
export const REGION_OUTLINE_ALPHA = 115;
export const REGION_FILL_ALPHA = 18;

export function regionDeckColor(
  hueIndex: number,
  alpha: number,
): [number, number, number, number] {
  return [...REGION_HUES[hueIndex % REGION_HUES.length], alpha];
}

export function pm25Color(pm25: number | null | undefined): string {
  if (pm25 === null || pm25 === undefined) return PM25_NO_DATA_COLOR;
  const stop = PM25_AQI_STOPS.find((entry) => pm25 <= entry.limit);
  return stop ? stop.color : PM25_AQI_STOPS.at(-1)!.color;
}

export function pm25DeckColor(pm25: number | null | undefined): [number, number, number] {
  const hex = pm25Color(pm25).slice(1);
  return [
    Number.parseInt(hex.slice(0, 2), 16),
    Number.parseInt(hex.slice(2, 4), 16),
    Number.parseInt(hex.slice(4, 6), 16),
  ];
}

export function badgeClass(flag: string): string {
  switch (flag) {
    case "stale":
      return "bg-amber-500/15 text-amber-300 border-amber-400/40";
    case "outlier":
      return "bg-violet-500/15 text-violet-300 border-violet-400/40";
    default:
      return "bg-emerald-500/15 text-emerald-300 border-emerald-400/40";
  }
}

export function formatHourUtc(iso: string): string {
  return `${HOUR_FORMAT.format(new Date(iso))} UTC`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

const HOUR_FORMAT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  hour12: false,
});
