import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.text();
  try {
    const upstream = await fetch(_upstreamUrl(), {
      method: "POST",
      headers: _upstreamHeaders(request),
      body,
    });
    const headers = new Headers(upstream.headers);
    headers.set(
      "content-type",
      upstream.headers.get("content-type") ?? "text/event-stream",
    );
    headers.set(
      "cache-control",
      upstream.headers.get("cache-control") ?? "no-cache",
    );
    headers.set("x-accel-buffering", "no");
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return new Response("chat upstream unreachable", { status: 502 });
  }
}

const _DEFAULT_API_URL = "http://localhost:8000";

const _FORWARDED_HEADERS = ["accept", "authorization", "content-type"] as const;

function _upstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  for (const name of _FORWARDED_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) {
      headers.set(name, value);
    }
  }
  return headers;
}

function _upstreamUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || _DEFAULT_API_URL;
  return `${base}/api/chat`;
}
