import { describe, expect, it } from "vitest";
import { parseSseStream, type ChatStreamEvent } from "./sse";

function streamedResponse(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

async function collect(body: string): Promise<ChatStreamEvent[]> {
  const events: ChatStreamEvent[] = [];
  for await (const event of parseSseStream(streamedResponse(body))) {
    events.push(event);
  }
  return events;
}

describe("parseSseStream", () => {
  it("parses framed events in order", async () => {
    const events = await collect(
      'event: token\ndata: {"text":"hi"}\n\nevent: evidence\ndata: {"fireIds":["f1"]}\n\n',
    );
    expect(events).toEqual([
      { event: "token", data: { text: "hi" } },
      { event: "evidence", data: { fireIds: ["f1"] } },
    ]);
  });

  it("flushes a trailing frame missing the final blank line", async () => {
    const events = await collect('event: token\ndata: {"text":"end"}');
    expect(events).toEqual([{ event: "token", data: { text: "end" } }]);
  });

  it("drops unknown events and malformed payloads without aborting", async () => {
    const events = await collect(
      'event: ping\ndata: {}\n\nevent: token\ndata: not-json\n\nevent: error\ndata: {"message":"boom"}\n\n',
    );
    expect(events).toEqual([{ event: "error", data: { message: "boom" } }]);
  });

  it("ignores frames missing the event name or data payload", async () => {
    const events = await collect(
      'data: {"text":"no-event"}\n\nevent: token\n\nevent: token\ndata: {"text":"ok"}\n\n',
    );
    expect(events).toEqual([{ event: "token", data: { text: "ok" } }]);
  });

  it("rejects non-2xx responses", async () => {
    const response = new Response(null, { status: 503 });
    await expect(parseSseStream(response).next()).rejects.toThrow(
      "chat stream failed: HTTP 503",
    );
  });
});
