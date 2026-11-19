import type { Feature, Polygon } from "geojson";
import type { SnapshotRegion } from "./types";

export interface RegionProperties {
  id: string;
  label: string;
  hueIndex: number;
}

export type RegionFeature = Feature<Polygon, RegionProperties>;

export function regionFeatures(
  regions: readonly SnapshotRegion[] | null | undefined,
): RegionFeature[] {
  return (regions ?? []).map((region, index) => {
    const [minLon, minLat, maxLon, maxLat] = region.bbox;
    return {
      type: "Feature" as const,
      properties: { id: region.id, label: region.label, hueIndex: index },
      geometry: {
        type: "Polygon" as const,
        coordinates: [
          [
            [minLon, minLat],
            [maxLon, minLat],
            [maxLon, maxLat],
            [minLon, maxLat],
            [minLon, minLat],
          ],
        ],
      },
    };
  });
}
