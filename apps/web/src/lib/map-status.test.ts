import { describe, expect, it } from "vitest";
import { deriveMapStatus, type MapStatusInput } from "./map-status";
import type { Snapshot } from "./types";

const BASE: MapStatusInput = {
  rowsError: null,
  selectedHour: null,
  snapshot: null,
  snapshotError: null,
};

const EMPTY_SNAPSHOT: Snapshot = { fires: [], stations: [], wind: [] };

const ACTIVE_SNAPSHOT: Snapshot = {
  fires: [],
  stations: [
    {
      station_id: "s9",
      station_name: "Riverside",
      lat: 41.5,
      lon: -121.0,
      pm25: 18.2,
      quality_flag: "stale",
      observed_at: "2026-07-04T09:00:00Z",
    },
  ],
  wind: [
    {
      grid_id: "g1",
      observed_at: "2026-07-04T12:00:00Z",
      lat: 0,
      lon: 0,
      wind_speed_10m: 4.2,
      wind_direction_10m: 220,
      boundary_layer_height: 1000,
    },
  ],
};

describe("deriveMapStatus", () => {
  it("reports loading-rows while the timeline is pending", () => {
    expect(deriveMapStatus(BASE)).toBe("loading-rows");
  });

  it("reports loading-hour when the hour is selected but the snapshot is pending", () => {
    expect(deriveMapStatus({ ...BASE, selectedHour: "2026-07-04T12:00:00Z" })).toBe(
      "loading-hour",
    );
  });

  it("reports empty for a snapshot without fires or stations", () => {
    expect(
      deriveMapStatus({
        ...BASE,
        selectedHour: "2026-07-04T12:00:00Z",
        snapshot: EMPTY_SNAPSHOT,
      }),
    ).toBe("empty");
  });

  it("does not count wind rows as map items", () => {
    expect(
      deriveMapStatus({
        ...BASE,
        selectedHour: "2026-07-04T12:00:00Z",
        snapshot: { fires: [], stations: [], wind: ACTIVE_SNAPSHOT.wind },
      }),
    ).toBe("empty");
  });

  it("reports ready once fires or stations exist", () => {
    expect(
      deriveMapStatus({
        ...BASE,
        selectedHour: "2026-07-04T12:00:00Z",
        snapshot: ACTIVE_SNAPSHOT,
      }),
    ).toBe("ready");
  });

  it("reports error on snapshot failure regardless of other state", () => {
    expect(
      deriveMapStatus({
        ...BASE,
        selectedHour: "2026-07-04T12:00:00Z",
        snapshot: ACTIVE_SNAPSHOT,
        snapshotError: "snapshot failed",
      }),
    ).toBe("error");
  });

  it("reports error on timeline failure", () => {
    expect(deriveMapStatus({ ...BASE, rowsError: "timeline load failed" })).toBe("error");
  });
});
