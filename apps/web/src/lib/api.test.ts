import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchSnapshot, fetchTimelineSummary } from "./api";

const JSON_HEADERS = { headers: { "content-type": "application/json" } };

function jsonFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, ...JSON_HEADERS }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchTimelineSummary", () => {
  it("sends start/end as the query string and parses rows", async () => {
    const rows = [
      {
        hour_bucket: "2026-07-04T10:00:00Z",
        active_fires_count: 3,
        avg_pm25: 12.5,
        max_pm25: 40.1,
        active_stations: 8,
        stale_stations: 2,
      },
    ];
    const fetchMock = jsonFetch(200, rows);
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchTimelineSummary("2026-07-04T00:00:00Z", "2026-07-05T00:00:00Z")).resolves.toEqual(rows);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/timeline/summary?start=2026-07-04T00%3A00%3A00Z&end=2026-07-05T00%3A00%3A00Z",
      { signal: undefined },
    );
  });

  it("passes the abort signal through", async () => {
    const controller = new AbortController();
    const fetchMock = jsonFetch(200, []);
    vi.stubGlobal("fetch", fetchMock);

    await fetchTimelineSummary("a", "b", controller.signal);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      signal: controller.signal,
    });
  });

  it("throws on HTTP failure", async () => {
    vi.stubGlobal("fetch", jsonFetch(500, {}));
    await expect(fetchTimelineSummary("a", "b")).rejects.toThrow(
      "timeline summary failed: HTTP 500",
    );
  });
});

describe("fetchSnapshot", () => {
  it("sends the timestamp and parses the snapshot", async () => {
    const snapshot = { fires: [], stations: [], wind: [] };
    const fetchMock = jsonFetch(200, snapshot);
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchSnapshot("2026-07-04T10:00:00Z")).resolves.toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/snapshot?timestamp=2026-07-04T10%3A00%3A00Z",
      { signal: undefined },
    );
  });

  it("throws on HTTP failure", async () => {
    vi.stubGlobal("fetch", jsonFetch(404, {}));
    await expect(fetchSnapshot("ts")).rejects.toThrow("snapshot failed: HTTP 404");
  });
});
