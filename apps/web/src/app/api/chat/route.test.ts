import { afterEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";
import { POST } from "./route";

function upstreamResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

async function runPost(headers: Record<string, string>, body: string): Promise<Response> {
  const request = new Request("http://localhost:3000/api/chat", {
    method: "POST",
    headers,
    body,
  });
  return POST(request as unknown as NextRequest);
}

describe("POST /api/chat proxy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards method, body, headers, and honors the env base URL", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init: RequestInit) =>
      upstreamResponse(["event: token\n\n"]),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://upstream:8000");

    const res = await runPost(
      {
        "content-type": "application/json",
        authorization: "Bearer token-123",
        accept: "text/event-stream",
        "x-irrelevant": "drop-me",
      },
      '{"message":"hi"}',
    );

    expect(fetchMock).toHaveBeenCalledWith("http://upstream:8000/api/chat", {
      method: "POST",
      headers: expect.any(Headers),
      body: '{"message":"hi"}',
    });
    const init = fetchMock.mock.calls[0]?.[1];
    const sent = (init?.headers ?? undefined) as Headers | undefined;
    expect(sent).toBeInstanceOf(Headers);
    expect(sent?.get("authorization")).toBe("Bearer token-123");
    expect(sent?.get("content-type")).toBe("application/json");
    expect(sent?.get("accept")).toBe("text/event-stream");
    expect(sent?.has("x-irrelevant")).toBe(false);
    expect(res.status).toBe(200);
  });

  it("passes through upstream status, content type, and streamed body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        upstreamResponse(["event: thinking\ndata: {}\n\n", "event: token\n\n"]),
      ),
    );
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://upstream:8000");

    const res = await runPost({ "content-type": "application/json" }, "{}");

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("text/event-stream");
    expect(res.headers.get("x-accel-buffering")).toBe("no");
    expect(await res.text()).toBe(
      "event: thinking\ndata: {}\n\nevent: token\n\n",
    );
  });

  it("passes through upstream error status, body, and content type", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "boom" }), {
          status: 503,
          headers: { "content-type": "application/json" },
        }),
      ),
    );
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://upstream:8000");

    const res = await runPost({ "content-type": "application/json" }, "{}");

    expect(res.status).toBe(503);
    expect(res.headers.get("content-type")).toBe("application/json");
    expect(await res.text()).toBe(JSON.stringify({ detail: "boom" }));
  });

  it("returns 502 when the upstream fetch throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connection refused");
      }),
    );
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://upstream:8000");

    const res = await runPost({ "content-type": "application/json" }, "{}");

    expect(res.status).toBe(502);
  });

  it("defaults the upstream base URL when the env var is unset", async () => {
    const fetchMock = vi.fn(async () => upstreamResponse([""]));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");

    await runPost({}, "{}");

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/api/chat", {
      method: "POST",
      headers: expect.any(Headers),
      body: "{}",
    });
  });
});
