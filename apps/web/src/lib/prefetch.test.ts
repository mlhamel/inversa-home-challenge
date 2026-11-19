import { describe, expect, it } from "vitest";
import { planPrefetchHours } from "./prefetch";

describe("planPrefetchHours", () => {
  it("returns the newest hours first up to the requested count", () => {
    const hours = [
      "2026-11-17T00:00:00Z",
      "2026-11-17T01:00:00Z",
      "2026-11-17T02:00:00Z",
    ];
    expect(planPrefetchHours(hours, 2)).toEqual([
      "2026-11-17T02:00:00Z",
      "2026-11-17T01:00:00Z",
    ]);
  });

  it("returns every hour reversed when count exceeds the timeline", () => {
    const hours = ["2026-11-17T00:00:00Z", "2026-11-17T01:00:00Z"];
    expect(planPrefetchHours(hours, 48)).toEqual([
      "2026-11-17T01:00:00Z",
      "2026-11-17T00:00:00Z",
    ]);
  });

  it("returns nothing for zero or negative counts", () => {
    const hours = ["2026-11-17T00:00:00Z"];
    expect(planPrefetchHours(hours, 0)).toEqual([]);
    expect(planPrefetchHours(hours, -1)).toEqual([]);
  });

  it("returns nothing for an empty timeline", () => {
    expect(planPrefetchHours([], 48)).toEqual([]);
  });
});
