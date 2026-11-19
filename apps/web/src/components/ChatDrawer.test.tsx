// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import ChatDrawer, { type ChatMessageData } from "./ChatDrawer";
import { parseEvidence } from "../lib/evidence";

afterEach(cleanup);

const EVIDENCE = parseEvidence({
  fireIds: ["f1", "f2"],
  stationIds: ["s9"],
})!;

function assistantMessage(overrides: Partial<ChatMessageData> = {}): ChatMessageData {
  return {
    id: 2,
    role: "assistant",
    text: "Downwind PM2.5 is high.",
    tools: [],
    evidence: null,
    error: null,
    ...overrides,
  };
}

function renderDrawer(
  messages: ChatMessageData[],
  streaming = false,
): { onSubmit: ReturnType<typeof vi.fn>; onEvidenceChip: ReturnType<typeof vi.fn>; onClose: ReturnType<typeof vi.fn>; user: ReturnType<typeof userEvent.setup> } {
  const onSubmit = vi.fn();
  const onEvidenceChip = vi.fn();
  const onClose = vi.fn();
  const user = userEvent.setup();
  render(
    <ChatDrawer
      open
      onClose={onClose}
      messages={messages}
      streaming={streaming}
      onSubmit={onSubmit}
      onEvidenceChip={onEvidenceChip}
    />,
  );
  return { onSubmit, onEvidenceChip, onClose, user };
}

describe("ChatDrawer", () => {
  it("renders starter prompts when empty and submits the clicked one", async () => {
    const { onSubmit, user } = renderDrawer([]);

    expect(screen.getByText("Ask the map")).toBeInTheDocument();
    const starter = screen.getByRole("button", { name: /Where is smoke heading/ });
    await user.click(starter);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit.mock.calls[0]?.[0]).toBe("Where is smoke heading right now?");
  });

  it("sends the typed draft and clears the input", async () => {
    const { onSubmit, user } = renderDrawer([]);

    const input = screen.getByPlaceholderText("Ask about fires, wind, air quality…");
    await user.type(input, "Why is air quality bad?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith("Why is air quality bad?");
    expect(input).toHaveValue("");
  });

  it("renders evidence chips and reports clicks back as refs", async () => {
    const { onEvidenceChip, user } = renderDrawer([
      assistantMessage({ evidence: EVIDENCE }),
    ]);

    await user.click(screen.getByRole("button", { name: "🔥 2 fires" }));
    expect(onEvidenceChip).toHaveBeenCalledOnce();
    expect(onEvidenceChip.mock.calls[0]?.[0]).toBe(EVIDENCE);

    await user.click(screen.getByRole("button", { name: "📡 1 station" }));
    expect(onEvidenceChip).toHaveBeenCalledTimes(2);
  });

  it("renders assistant thinking as muted light-grey text above the answer", () => {
    renderDrawer([assistantMessage({ thinking: "Check fires, then wind." })]);

    const thinking = screen.getByText("Check fires, then wind.");
    expect(thinking).toBeInTheDocument();
    expect(thinking.className).toContain("text-white/40");
    expect(thinking.className).toContain("italic");
    expect(screen.getByText(/Downwind PM2\.5 is high/)).toBeInTheDocument();
  });

  it("shows assistant tool chips and error text", () => {
    renderDrawer([assistantMessage({ tools: ["wind_summary"], error: "boom" })]);

    expect(screen.getByText("⚙ wind_summary")).toBeInTheDocument();
    expect(screen.getByText("⚠ boom")).toBeInTheDocument();
  });

  it("renders user and assistant bubbles", () => {
    renderDrawer([
      { id: 1, role: "user", text: "hello", tools: [], evidence: null, error: null },
      assistantMessage(),
    ]);

    expect(screen.getByText("hello")).toBeInTheDocument();
    expect(screen.getByText(/Downwind PM2\.5 is high/)).toBeInTheDocument();
  });

  it("keeps input and starters disabled while streaming", () => {
    renderDrawer([], true);

    expect(screen.getByPlaceholderText("Ask about fires, wind, air quality…")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Where is smoke heading/ })).toBeDisabled();
  });

  it("closes via the drawer close button", async () => {
    const { onClose, user } = renderDrawer([]);

    await user.click(screen.getByRole("button", { name: "Close chat" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
