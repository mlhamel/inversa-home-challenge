// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import MapStatusOverlay from "./MapStatusOverlay";
import type { MapStatus } from "../lib/map-status";

afterEach(cleanup);

describe("MapStatusOverlay", () => {
  it("announces the loading state politely with a spinner", () => {
    const { container } = render(<MapStatusOverlay status="loading-hour" />);
    const chip = screen.getByRole("status");
    expect(chip).toHaveTextContent("Loading this hour…");
    expect(chip).toHaveAttribute("aria-live", "polite");
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
  });

  it("labels the boot window", () => {
    render(<MapStatusOverlay status="loading-rows" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading available hours…");
  });

  it("labels an empty hour without a spinner", () => {
    const { container } = render(<MapStatusOverlay status="empty" />);
    expect(screen.getByRole("status")).toHaveTextContent("No activity observed this hour");
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull();
  });

  it("renders nothing when the map is ready", () => {
    render(<MapStatusOverlay status="ready" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders nothing on error, leaving the error banner as the surface", () => {
    render(<MapStatusOverlay status="error" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
