import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/server", () => ({
  NextResponse: {
    next: vi.fn((init?: unknown) => ({ kind: "next", init })),
  },
}));

import { NextResponse } from "next/server";
import { middleware } from "./middleware";
import { tokenCache } from "./lib/identity-token";

const request = () =>
  ({ headers: new Headers() }) as unknown as Parameters<typeof middleware>[0];

const metadataBody = () =>
  new Response("header.payload-exp-123.sig", {
    status: 200,
  });

describe("middleware", () => {
  beforeEach(() => {
    tokenCache.clear();
    vi.unstubAllGlobals();
    vi.mocked(NextResponse.next).mockClear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("passes through unchanged when no https audience is configured", async () => {
    vi.stubEnv("API_AUDIENCE", "http://localhost:8000");
    vi.stubGlobal("fetch", vi.fn());

    await middleware(request());

    expect(NextResponse.next).toHaveBeenCalledWith();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("attaches a Bearer identity token to /api requests", async () => {
    vi.stubEnv("API_AUDIENCE", "https://api.example.com");
    vi.stubGlobal("fetch", vi.fn(async () => metadataBody()));

    await middleware(request());

    const init = (NextResponse.next as ReturnType<typeof vi.fn>).mock
      .calls[0]![0] as { request: { headers: Headers } };
    expect(init.request.headers.get("authorization")).toBe("Bearer header.payload-exp-123.sig");
  });

  it("passes through unchanged when the metadata server is unreachable", async () => {
    vi.stubEnv("API_AUDIENCE", "https://api.example.com");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("unreachable");
      }),
    );

    await middleware(request());

    expect(NextResponse.next).toHaveBeenCalledWith();
  });
});
