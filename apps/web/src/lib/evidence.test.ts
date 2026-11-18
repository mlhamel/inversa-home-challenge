import { describe, expect, it } from "vitest";
import { evidenceBounds, evidenceFocusDate, parseEvidence } from "./evidence";

const REFS = {
  fireIds: ["f1", "f2"],
  stationIds: ["s9"],
  focusTimestamp: "2026-07-04T12:00:00Z",
  bboxFocus: { minLon: -120, maxLon: -110, minLat: 30, maxLat: 45 },
};

describe("parseEvidence", () => {
  it("parses proto-JSON evidence frames with camelCase refs", () => {
    const refs = parseEvidence(REFS);
    expect(refs).not.toBeNull();
    expect(refs?.fireIds).toEqual(["f1", "f2"]);
    expect(refs?.stationIds).toEqual(["s9"]);
    expect(refs?.focusTimestamp?.seconds).toBe(1_783_166_400n);
  });

  it("accepts a frame that carries only one ref kind", () => {
    const refs = parseEvidence({ stationIds: ["s1", "s2"] });
    expect(refs?.stationIds).toEqual(["s1", "s2"]);
    expect(refs?.fireIds).toEqual([]);
  });

  it("returns null for a frame with no refs at all", () => {
    expect(parseEvidence({})).toBeNull();
  });

  it("returns null for malformed payloads", () => {
    expect(parseEvidence("not-an-object")).toBeNull();
    expect(parseEvidence(null)).toBeNull();
    expect(parseEvidence({ windSpeed10m: "garbage" })).toBeNull();
  });
});

describe("evidenceFocusDate", () => {
  it("converts the proto timestamp focus to a Date", () => {
    const date = evidenceFocusDate(parseEvidence(REFS));
    expect(date).toEqual(new Date("2026-07-04T12:00:00Z"));
  });

  it("returns null without a focus timestamp", () => {
    expect(evidenceFocusDate(parseEvidence({ fireIds: ["f1"] }))).toBeNull();
    expect(evidenceFocusDate(null)).toBeNull();
  });
});

describe("evidenceBounds", () => {
  it("normalizes the bbox to south-west / north-east corners", () => {
    expect(evidenceBounds(parseEvidence(REFS))).toEqual([
      [-120, 30],
      [-110, 45],
    ]);
  });

  it("returns null without a bbox", () => {
    expect(evidenceBounds(parseEvidence({ fireIds: ["f1"] }))).toBeNull();
    expect(evidenceBounds(null)).toBeNull();
  });
});
