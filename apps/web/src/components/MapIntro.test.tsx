// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import MapIntro from "./MapIntro";
import type { SnapshotRegion } from "../lib/types";

afterEach(cleanup);

const california: SnapshotRegion = {
  id: "california",
  label: "California",
  bbox: [-124.4, 36.0, -115.4, 42.0],
};
const nwIndia: SnapshotRegion = {
  id: "nw-india",
  label: "Punjab–Haryana–Delhi NCR",
  bbox: [74.0, 28.2, 77.8, 31.5],
};

describe("MapIntro", () => {
  it("names all three data sources", () => {
    render(<MapIntro regions={[]} />);
    const box = screen.getByLabelText("About the map");
    expect(box).toHaveTextContent("NASA FIRMS");
    expect(box).toHaveTextContent("OpenAQ");
    expect(box).toHaveTextContent("Open-Meteo");
  });

  it("points to the timeline and the AI chat by name", () => {
    render(<MapIntro regions={[]} />);
    const box = screen.getByLabelText("About the map");
    expect(box).toHaveTextContent("Scrub the timeline below");
    expect(box).toHaveTextContent("💬 Ask the map");
    expect(box).toHaveTextContent("ask the AI");
  });

  it("lists every configured focus area dynamically", () => {
    render(<MapIntro regions={[california, nwIndia]} />);
    const box = screen.getByLabelText("About the map");
    expect(box).toHaveTextContent(
      "Watching 2 focus areas (bbox outlines): California, Punjab–Haryana–Delhi NCR.",
    );
  });

  it("uses singular grammar for a single focus area", () => {
    render(<MapIntro regions={[california]} />);
    expect(screen.getByLabelText("About the map")).toHaveTextContent(
      "Watching 1 focus area (bbox outline): California.",
    );
  });

  it("omits the focus-area line when the snapshot has none", () => {
    render(<MapIntro regions={null} />);
    const box = screen.getByLabelText("About the map");
    expect(box).not.toHaveTextContent("focus area");
    expect(box).not.toHaveTextContent("bbox");
  });

  it("treats an undefined regions list the same as none", () => {
    render(<MapIntro regions={undefined} />);
    expect(screen.getByLabelText("About the map")).not.toHaveTextContent(
      "bbox",
    );
  });
});
