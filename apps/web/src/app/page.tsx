"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ChatDrawer, { type ChatMessageData } from "../components/ChatDrawer";
import EvidenceInspector from "../components/EvidenceInspector";
import MapCanvas, { type MapPadding } from "../components/MapCanvas";
import MapLegend from "../components/MapLegend";
import TimelineDock from "../components/TimelineDock";
import { fetchSnapshot, fetchTimelineSummary } from "../lib/api";
import {
  evidenceBounds,
  evidenceFocusDate,
  parseEvidence,
  type EvidenceRefs,
} from "../lib/evidence";
import { parseSseStream } from "../lib/sse";
import type { Snapshot, TimelineRow } from "../lib/types";

const WEEK_MS = 7 * 24 * 3_600_000;
const SNAPSHOT_DEBOUNCE_MS = 100;
const PLAY_STEP_MS = 800;

export default function Page() {
  const [rows, setRows] = useState<TimelineRow[]>([]);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [selectedHour, setSelectedHour] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceRefs | null>(null);
  const [inspectorEvidence, setInspectorEvidence] = useState<EvidenceRefs | null>(null);
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const nextMessageId = useRef(1);
  const playingRef = useRef(false);

  useEffect(() => {
    playingRef.current = playing;
  }, [playing]);

  useEffect(() => {
    const end = new Date();
    const start = new Date(end.getTime() - WEEK_MS);
    fetchTimelineSummary(start.toISOString(), end.toISOString())
      .then((data) => {
        setRows(data);
        const last = data.at(-1);
        if (last) setSelectedHour((current) => current ?? last.hour_bucket);
      })
      .catch((err: unknown) =>
        setRowsError(err instanceof Error ? err.message : "timeline load failed"),
      );
  }, []);

  useEffect(() => {
    if (selectedHour === null) {
      setSnapshot(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      fetchSnapshot(selectedHour, controller.signal)
        .then((data) => {
          setSnapshot(data);
          setSnapshotError(null);
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          setSnapshotError(err instanceof Error ? err.message : "snapshot failed");
        });
    }, SNAPSHOT_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [selectedHour]);

  const highlightedFireIds = useMemo(
    () => new Set(evidence?.fireIds ?? []),
    [evidence],
  );
  const highlightedStationIds = useMemo(
    () => new Set(evidence?.stationIds ?? []),
    [evidence],
  );
  const focusBounds = useMemo(() => evidenceBounds(evidence), [evidence]);
  const focusPoint = useMemo(() => {
    if (focusBounds !== null || !snapshot) return null;
    const points: { lat: number; lon: number }[] = [];
    for (const fire of snapshot.fires) {
      if (highlightedFireIds.has(fire.fire_id)) points.push(fire);
    }
    for (const station of snapshot.stations) {
      if (highlightedStationIds.has(station.station_id)) points.push(station);
    }
    return points.length === 1 ? points[0] : null;
  }, [focusBounds, snapshot, highlightedFireIds, highlightedStationIds]);

  useEffect(() => {
    if (!evidence || playingRef.current) return;
    const focus = evidenceFocusDate(evidence);
    if (focus) setSelectedHour(focus.toISOString());
  }, [evidence]);

  const mapPadding = useMemo<MapPadding>(
    () => ({ top: 64, right: chatOpen ? 424 : 24, bottom: 224, left: 24 }),
    [chatOpen],
  );

  const handleChatSubmit = useCallback(
    async (text: string) => {
      if (streaming) return;
      setEvidence(null);
      const userMessage: ChatMessageData = {
        id: nextMessageId.current++,
        role: "user",
        text,
        tools: [],
        evidence: null,
        error: null,
      };
      const botId = nextMessageId.current++;
      const assistantMessage: ChatMessageData = {
        id: botId,
        role: "assistant",
        text: "",
        tools: [],
        evidence: null,
        error: null,
      };
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      const update = (fn: (message: ChatMessageData) => ChatMessageData) =>
        setMessages((prev) => prev.map((m) => (m.id === botId ? fn(m) : m)));
      setStreaming(true);
      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        });
        for await (const event of parseSseStream(res)) {
          if (event.event === "token") {
            const token = typeof event.data.text === "string" ? event.data.text : "";
            update((m) => ({ ...m, text: m.text + token }));
          } else if (event.event === "tool_call") {
            const tool =
              typeof event.data.tool === "string" ? event.data.tool : "unknown tool";
            update((m) =>
              m.tools.includes(tool) ? m : { ...m, tools: [...m.tools, tool] },
            );
          } else if (event.event === "evidence") {
            const refs = parseEvidence(event.data);
            if (refs) {
              update((m) => ({ ...m, evidence: refs }));
              setEvidence(refs);
              setInspectorEvidence(refs);
            }
          } else if (event.event === "error") {
            update((m) => ({
              ...m,
              error:
                typeof event.data.message === "string" ? event.data.message : "chat error",
            }));
          }
        }
      } catch (err: unknown) {
        update((m) => ({
          ...m,
          error: err instanceof Error ? err.message : "chat failed",
        }));
      } finally {
        setStreaming(false);
      }
    },
    [streaming],
  );

  return (
    <main className="relative h-dvh w-full overflow-hidden">
      <MapCanvas
        snapshot={snapshot}
        highlightedFireIds={highlightedFireIds}
        highlightedStationIds={highlightedStationIds}
        focusPoint={focusPoint}
        bounds={focusBounds}
        padding={mapPadding}
      />

      <MapLegend />

      <header className="absolute left-3 top-3 z-20 flex flex-col items-start gap-2">
        <div className="rounded-lg panel border px-3 py-2 text-sm">
          <span className="font-semibold">Inversa</span>
          <span className="text-white/60"> · wildfire → wind → air quality</span>
        </div>
        {rowsError === null ? null : (
          <div className="rounded-lg panel border px-3 py-1.5 text-xs text-red-300">
            {rowsError}
          </div>
        )}
      </header>

      {inspectorEvidence === null ? null : (
        <EvidenceInspector
          evidence={inspectorEvidence}
          snapshot={snapshot}
          onClose={() => setInspectorEvidence(null)}
        />
      )}

      {chatOpen ? null : (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          className="absolute right-3 top-3 z-20 rounded-lg panel border px-3 py-2 text-sm hover:bg-white/10"
        >
          💬 Ask the map
        </button>
      )}
      <ChatDrawer
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        messages={messages}
        streaming={streaming}
        onSubmit={handleChatSubmit}
        onEvidenceChip={(refs) => setInspectorEvidence(refs)}
      />

      {snapshotError === null ? null : (
        <p className="absolute bottom-[200px] left-1/2 z-20 -translate-x-1/2 rounded panel border px-3 py-1 text-xs text-red-300">
          {snapshotError}
        </p>
      )}

      <TimelineDock
        rows={rows}
        selectedHour={selectedHour}
        onSelectHour={setSelectedHour}
        playing={playing}
        onPlayingChange={setPlaying}
      />
    </main>
  );
}
