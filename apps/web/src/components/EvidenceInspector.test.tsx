// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import EvidenceInspector from "./EvidenceInspector";
import { parseEvidence } from "../lib/evidence";
import type { Snapshot } from "../lib/types";

afterEach(cleanup);

const EVIDENCE = parseEvidence({
  fireIds: ["f1", "f2"],
  stationIds: ["s9"],
  focusTimestamp: "2026-07-04T12:00:00Z",
})!;

const SNAPSHOT: Snapshot = {
  fires: [
    { fire_id: "f1", observed_at: "2026-07-04T10:00:00Z", lat: 41.0, lon: -120.0, frp: 12.34, confidence: "nominal", satellite: "MODIS" },
  ],
  stations: [
    { station_id: "s9", station_name: "Riverside", lat: 41.5, lon: -121.0, pm25: 18.2, quality_flag: "stale", observed_at: "2026-07-04T09:00:00Z" },
  ],
  wind: [],
};

describe("EvidenceInspector", () => {
  it("lists referenced fires, stations, and the focus hour", () => {
    render(<EvidenceInspector evidence={EVIDENCE} snapshot={SNAPSHOT} onClose={() => {}} />);

    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText(/Focus:/)).toBeInTheDocument();
    expect(screen.getByText("🔥 f1")).toBeInTheDocument();
    expect(screen.getByText(/· FRP 12\.3 · MODIS/)).toBeInTheDocument();
    expect(screen.getByText("🔥 f2")).toBeInTheDocument();
    expect(screen.getByText(/not in current snapshot/)).toBeInTheDocument();
    expect(screen.getByText("Riverside")).toBeInTheDocument();
    expect(screen.getByText(/PM2\.5 18\.2 µg\/m³/)).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("truncates long ref lists and counts the overflow", () => {
    const many = parseEvidence({
      fireIds: ["f1", "f2", "f3", "f4", "f5", "f6"],
      stationIds: [],
    })!;
    render(<EvidenceInspector evidence={many} snapshot={SNAPSHOT} onClose={() => {}} />);

    expect(screen.getAllByText(/not in current snapshot/)).toHaveLength(4);
    expect(screen.getByText("+1 more fires")).toBeInTheDocument();
  });

  it("closes via the panel close button", async () => {
    const onClose = vi.fn();
    render(<EvidenceInspector evidence={EVIDENCE} snapshot={SNAPSHOT} onClose={onClose} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Close evidence panel" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
