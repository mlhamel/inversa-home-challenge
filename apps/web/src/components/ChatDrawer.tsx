"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import type { EvidenceRefs } from "../lib/evidence";

export interface ChatMessageData {
  id: number;
  role: "user" | "assistant";
  text: string;
  tools: string[];
  evidence: EvidenceRefs | null;
  error: string | null;
}

interface ChatDrawerProps {
  open: boolean;
  onClose: () => void;
  messages: ChatMessageData[];
  streaming: boolean;
  onSubmit: (text: string) => void;
  onEvidenceChip: (refs: EvidenceRefs) => void;
}

const STARTERS: readonly string[] = [
  "Where is smoke heading right now?",
  "How has air quality changed near the fires over the last 24 hours?",
  "Which stations look stale or suspicious?",
  "Give me a one-paragraph picture of fire, wind, and air quality right now.",
];

export default function ChatDrawer({
  open,
  onClose,
  messages,
  streaming,
  onSubmit,
  onEvidenceChip,
}: ChatDrawerProps) {
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = draft.trim();
    if (value === "" || streaming) return;
    setDraft("");
    onSubmit(value);
  };

  return (
    <aside
      aria-hidden={!open}
      className={`absolute inset-y-0 right-0 z-30 flex w-[400px] max-w-[92vw] flex-col panel border-l transition-transform duration-300 ${
        open ? "translate-x-0" : "pointer-events-none translate-x-full"
      }`}
    >
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-2.5">
        <h2 className="text-sm font-semibold">Ask the map</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close chat"
          className="rounded px-1.5 py-0.5 text-white/60 hover:bg-white/10 hover:text-white"
        >
          ✕
        </button>
      </div>

      <div ref={listRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 ? (
          <div className="mt-6">
            <p className="text-xs text-white/50">Try one of these:</p>
            <div className="mt-2 flex flex-col gap-1.5">
              {STARTERS.map((starter) => (
                <button
                  key={starter}
                  type="button"
                  disabled={streaming}
                  onClick={() => onSubmit(starter)}
                  className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-left text-xs text-white/80 hover:bg-white/10 disabled:opacity-40"
                >
                  {starter}
                </button>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-white/40">
              Answers come from live map tooling; citations pulse as{" "}
              <span className="text-amber-300/80">🔥 fires</span> and{" "}
              <span className="text-cyan-300/80">📡 stations</span> chips.
            </p>
          </div>
        ) : null}

        {messages.map((message) =>
          message.role === "user" ? (
            <p
              key={message.id}
              className="ml-8 max-w-full whitespace-pre-wrap rounded-lg border border-cyan-400/30 bg-cyan-500/15 px-3 py-2 text-sm"
            >
              {message.text}
            </p>
          ) : (
            <div
              key={message.id}
              className="mr-8 max-w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm"
            >
              {message.text === "" && streaming && message.error === null ? (
                <span className="text-white/50">…</span>
              ) : (
                <div className="md-body">
                  <ReactMarkdown>{message.text}</ReactMarkdown>
                </div>
              )}
              {message.tools.length === 0 ? null : (
                <div className="mt-2 flex flex-wrap gap-1">
                  {message.tools.map((tool) => (
                    <span
                      key={tool}
                      className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 text-[11px] text-white/60"
                    >
                      ⚙ {tool}
                    </span>
                  ))}
                </div>
              )}
              {message.evidence === null ? null : (
                <div className="mt-2 flex flex-wrap gap-1">
                  {message.evidence.fireIds.length === 0 ? null : (
                    <button
                      type="button"
                      onClick={() => onEvidenceChip(message.evidence!)}
                      className="rounded-full border border-amber-400/40 bg-amber-500/15 px-2 py-0.5 text-[11px] text-amber-200 hover:bg-amber-500/25"
                    >
                      🔥 {message.evidence.fireIds.length}{" "}
                      {message.evidence.fireIds.length === 1 ? "fire" : "fires"}
                    </button>
                  )}
                  {message.evidence.stationIds.length === 0 ? null : (
                    <button
                      type="button"
                      onClick={() => onEvidenceChip(message.evidence!)}
                      className="rounded-full border border-cyan-400/40 bg-cyan-500/15 px-2 py-0.5 text-[11px] text-cyan-200 hover:bg-cyan-500/25"
                    >
                      📡 {message.evidence.stationIds.length}{" "}
                      {message.evidence.stationIds.length === 1 ? "station" : "stations"}
                    </button>
                  )}
                </div>
              )}
              {message.error === null ? null : (
                <p className="mt-2 text-xs text-red-300">⚠ {message.error}</p>
              )}
            </div>
          ),
        )}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-white/10 p-3">
        <input
          className="min-w-0 flex-1 rounded border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-cyan-400/60"
          placeholder="Ask about fires, wind, air quality…"
          value={draft}
          disabled={streaming}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="submit"
          disabled={streaming || draft.trim() === ""}
          className="rounded border border-white/15 px-3 text-sm hover:bg-white/10 disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </aside>
  );
}
