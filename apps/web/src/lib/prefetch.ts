export const PREFETCH_HOURS = 48;
export const PREFETCH_CONCURRENCY = 2;
export const PREFETCH_PUMP_MS = 250;
export const PREFETCH_PAUSE_MS = 500;

export function planPrefetchHours(hours: string[], count: number): string[] {
  if (count <= 0 || hours.length === 0) return [];
  return hours.slice(Math.max(0, hours.length - count)).reverse();
}
