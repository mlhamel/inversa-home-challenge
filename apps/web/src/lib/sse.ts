export type ChatStreamEventName = "tool_call" | "evidence" | "token" | "error";

export interface ChatStreamEvent {
  event: ChatStreamEventName;
  data: Record<string, unknown>;
}

export async function* parseSseStream(
  response: Response,
): AsyncGenerator<ChatStreamEvent, void, undefined> {
  if (!response.ok || !response.body) {
    throw new Error(`chat stream failed: HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    for (;;) {
      const boundary = buffer.indexOf("\n\n");
      if (boundary === -1) break;
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseSseFrame(frame);
      if (parsed) yield parsed;
    }
  }
  const trailing = buffer.trim();
  if (trailing !== "") {
    const parsed = parseSseFrame(trailing);
    if (parsed) yield parsed;
  }
}

function parseSseFrame(frame: string): ChatStreamEvent | null {
  let event = "";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) {
      event = line.slice(7).trim();
    } else if (line.startsWith("data:")) {
      data += line.slice(5).trimStart();
    }
  }
  if (event === "" || data === "") return null;
  const names: readonly ChatStreamEventName[] = [
    "tool_call",
    "evidence",
    "token",
    "error",
  ];
  if (!names.includes(event as ChatStreamEventName)) return null;
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
  return {
    event: event as ChatStreamEventName,
    data: payload,
  };
}
