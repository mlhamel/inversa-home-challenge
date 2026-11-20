// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import MapIntro from "./MapIntro";

afterEach(cleanup);

describe("MapIntro", () => {
  it("names all three data sources", () => {
    render(<MapIntro />);
    const box = screen.getByLabelText("About the map");
    expect(box).toHaveTextContent("NASA FIRMS");
    expect(box).toHaveTextContent("OpenAQ");
    expect(box).toHaveTextContent("Open-Meteo");
  });

  it("points to the timeline and the chat", () => {
    render(<MapIntro />);
    const box = screen.getByLabelText("About the map");
    expect(box).toHaveTextContent("scrub the timeline below");
    expect(box).toHaveTextContent("ask the map a question");
  });
});
