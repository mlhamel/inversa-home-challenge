import { describe, expect, it } from "vitest";
import { REGION_FILL_ALPHA, REGION_OUTLINE_ALPHA, regionDeckColor } from "./theme";
import { regionFeatures } from "./regions";
import type { SnapshotRegion } from "./types";

const CALIFORNIA: SnapshotRegion = {
  id: "california",
  label: "California",
  bbox: [-124.4, 36.0, -115.4, 42.0],
};
const SECOND: SnapshotRegion = {
  id: "second_area",
  label: "Second area",
  bbox: [10.0, 20.0, 15.0, 25.0],
};

describe("regionFeatures", () => {
  it("builds a closed bbox polygon per region", () => {
    const [feature] = regionFeatures([CALIFORNIA]);
    expect(feature.geometry.type).toBe("Polygon");
    const ring = feature.geometry.coordinates[0];
    expect(ring).toHaveLength(5);
    expect(ring[0]).toEqual(ring.at(-1));
    for (const [lon, lat] of ring) {
      expect(lon).toBeGreaterThanOrEqual(CALIFORNIA.bbox[0] - 1e-9);
      expect(lon).toBeLessThanOrEqual(CALIFORNIA.bbox[2] + 1e-9);
      expect(lat).toBeGreaterThanOrEqual(CALIFORNIA.bbox[1] - 1e-9);
      expect(lat).toBeLessThanOrEqual(CALIFORNIA.bbox[3] + 1e-9);
    }
  });

  it("attaches id, label, and a sequential hueIndex", () => {
    const features = regionFeatures([CALIFORNIA, SECOND]);
    expect(features.map((f) => f.properties)).toEqual([
      { id: "california", label: "California", hueIndex: 0 },
      { id: "second_area", label: "Second area", hueIndex: 1 },
    ]);
  });

  it("tolerates snapshots persisted before regions existed", () => {
    expect(regionFeatures(undefined)).toEqual([]);
    expect(regionFeatures(null)).toEqual([]);
  });
});

describe("regionDeckColor", () => {
  it("cycles the hue palette and applies the alpha", () => {
    expect(regionDeckColor(0, REGION_OUTLINE_ALPHA)).toEqual([64, 224, 200, REGION_OUTLINE_ALPHA]);
    expect(regionDeckColor(2, REGION_FILL_ALPHA)).toEqual([128, 222, 122, REGION_FILL_ALPHA]);
    expect(regionDeckColor(4, REGION_OUTLINE_ALPHA)[0]).toEqual(
      regionDeckColor(0, REGION_OUTLINE_ALPHA)[0],
    );
  });
});
