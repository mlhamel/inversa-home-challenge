// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import TimelineDock from "./TimelineDock";
import { fireResize } from "../test/setup";
import { formatHourUtc } from "../lib/theme";
import type { TimelineRow } from "../lib/types";

afterEach(cleanup);

const ROWS: TimelineRow[] = [
  { hour_bucket: "2026-07-04T10:00:00Z", active_fires_count: 0, avg_pm25: 8.0, max_pm25: 12.0, active_stations: 5, stale_stations: 1 },
  { hour_bucket: "2026-07-04T11:00:00Z", active_fires_count: 1, avg_pm25: 10.0, max_pm25: 20.0, active_stations: 6, stale_stations: 0 },
  { hour_bucket: "2026-07-04T12:00:00Z", active_fires_count: 2, avg_pm25: 14.0, max_pm25: 30.0, active_stations: 7, stale_stations: 1 },
  { hour_bucket: "2026-07-04T13:00:00Z", active_fires_count: 4, avg_pm25: 21.5, max_pm25: 55.0, active_stations: 8, stale_stations: 2 },
  { hour_bucket: "2026-07-04T14:00:00Z", active_fires_count: 2, avg_pm25: 18.0, max_pm25: 44.0, active_stations: 8, stale_stations: 2 },
];

interface DockRig {
  onSelectHour: ReturnType<typeof vi.fn>;
  onPlayingChange: ReturnType<typeof vi.fn>;
  rerender: (overrides?: { rows?: TimelineRow[]; selectedHour?: string | null; playing?: boolean }) => void;
}

function renderDock(overrides: { rows?: TimelineRow[]; selectedHour?: string | null; playing?: boolean } = {}): DockRig {
  const props = {
    rows: ROWS,
    selectedHour: ROWS[0].hour_bucket,
    onSelectHour: vi.fn(),
    playing: false,
    onPlayingChange: vi.fn(),
    ...overrides,
  };
  const utils = render(<TimelineDock {...props} />);
  return {
    onSelectHour: props.onSelectHour,
    onPlayingChange: props.onPlayingChange,
    rerender(more: { rows?: TimelineRow[]; selectedHour?: string | null; playing?: boolean } = {}) {
      utils.rerender(<TimelineDock {...props} {...more} />);
    },
  };
}

function sizeTimeline(width: number): void {
  const placeholder = screen.getByText("Sizing timeline…");
  const wrap = placeholder.parentElement;
  if (wrap === null) throw new Error("timeline wrap div not found");
  act(() => {
    fireResize(wrap, width);
  });
}

function pressScrubber(target: Element, clientX: number): void {
  const event = new Event("pointerdown", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clientX", { value: clientX });
  Object.defineProperty(event, "pointerId", { value: 1 });
  act(() => {
    target.dispatchEvent(event);
  });
}

describe("TimelineDock", () => {
  beforeAll(() => {
    Object.defineProperty(Element.prototype, "getBoundingClientRect", {
      value: () => ({ left: 0, width: 480, right: 480, top: 0, bottom: 0, height: 0, x: 0, y: 0 }),
      configurable: true,
    });
  });

  it("shows the empty-state message with no rows", () => {
    renderDock({ rows: [], selectedHour: null });

    expect(screen.getByText("No timeline data yet — run ingestion, then reload.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "▶ Play" })).toBeDisabled();
  });

  it("sizes the timeline via ResizeObserver and marks the selected hour", () => {
    renderDock();

    expect(screen.getByText("Sizing timeline…")).toBeInTheDocument();
    sizeTimeline(480);

    const slider = screen.getByRole("slider", { name: "Timeline scrubber" });
    expect(slider).toHaveAttribute("aria-valuemin", "1");
    expect(slider).toHaveAttribute("aria-valuemax", "5");
    expect(slider).toHaveAttribute("aria-valuenow", "1");
    expect(slider).toHaveAttribute("aria-valuetext", formatHourUtc(ROWS[0].hour_bucket));
  });

  it("renders the selected-hour summary line", () => {
    renderDock({ selectedHour: ROWS[3].hour_bucket });

    expect(screen.getByText(/fires 4 · PM2\.5 21\.5 \/ 55\.0 µg\/m³/)).toBeInTheDocument();
    expect(screen.getByText(/stations 8 \(2 stale\)/)).toBeInTheDocument();
  });

  it("selects an hour when the scrubber is pressed", () => {
    const { onSelectHour } = renderDock();

    sizeTimeline(480);
    const slider = screen.getByRole("slider", { name: "Timeline scrubber" });
    pressScrubber(slider, 468);

    expect(onSelectHour).toHaveBeenCalledTimes(1);
    expect(onSelectHour).toHaveBeenCalledWith(ROWS[4].hour_bucket);
  });

  it("does not select before the timeline has width", () => {
    const { onSelectHour } = renderDock();

    const placeholder = screen.getByText("Sizing timeline…");
    pressScrubber(placeholder.parentElement ?? document.body, 240);

    expect(onSelectHour).not.toHaveBeenCalled();
  });

  it("toggles playback via the play button", async () => {
    const { onPlayingChange, rerender } = renderDock();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "▶ Play" }));
    expect(onPlayingChange).toHaveBeenCalledTimes(1);
    expect(onPlayingChange).toHaveBeenCalledWith(true);
    expect(screen.getByRole("button", { name: "▶ Play" })).toBeInTheDocument();

    rerender({ playing: true });
    await user.click(screen.getByRole("button", { name: "⏸ Pause" }));
    expect(onPlayingChange).toHaveBeenCalledTimes(2);
    expect(onPlayingChange).toHaveBeenLastCalledWith(false);
  });
});
