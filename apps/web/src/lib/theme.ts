const PM25_AQI_STOPS: ReadonlyArray<{ limit: number; color: string }> = [
  { limit: 12, color: "#17a05a" },
  { limit: 35.4, color: "#f5d90a" },
  { limit: 55.4, color: "#ff7e00" },
  { limit: 150.4, color: "#ff2e2e" },
  { limit: 250.4, color: "#a845c4" },
  { limit: Number.POSITIVE_INFINITY, color: "#7e0023" },
];

export function pm25Color(pm25: number | null | undefined): string {
  if (pm25 === null || pm25 === undefined) return "#9aa4ae";
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

const HOUR_FORMAT = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
  hour12: false,
});

export function formatHourUtc(iso: string): string {
  return `${HOUR_FORMAT.format(new Date(iso))} UTC`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
