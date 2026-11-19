import { describe, expect, it } from "vitest";
import {
  SNAPSHOT_TTL_MS,
  createInMemorySnapshotStore,
  createSnapshotStore,
  filterExpired,
} from "./snapshot-store";
import type { Snapshot } from "./types";

const SNAPSHOT_A: Snapshot = { fires: [], stations: [], wind: [] };
const SNAPSHOT_B: Snapshot = { fires: [], stations: [], wind: [] };

describe("filterExpired", () => {
  it("keeps only entries inside the ttl window", () => {
    const entries = [
      { hour: "fresh", snapshot: SNAPSHOT_A, savedAt: 100 },
      { hour: "stale", snapshot: SNAPSHOT_B, savedAt: 0 },
    ];
    expect(
      filterExpired(entries, 100, 50).map((entry) => entry.hour),
    ).toEqual(["fresh"]);
    expect(filterExpired(entries, 1_100, 100)).toEqual([]);
  });
});

describe("createInMemorySnapshotStore", () => {
  it("round-trips saved snapshots", async () => {
    const store = createInMemorySnapshotStore();
    await store.save("2026-11-19T10:00:00Z", SNAPSHOT_A, 42);
    await expect(store.load(43)).resolves.toEqual(
      new Map([["2026-11-19T10:00:00Z", SNAPSHOT_A]]),
    );
  });

  it("drops expired entries on load", async () => {
    const store = createInMemorySnapshotStore();
    await store.save("old", SNAPSHOT_A, 0);
    await store.save("latest", SNAPSHOT_B, 1_000);

    const live = await store.load(SNAPSHOT_TTL_MS + 1);
    expect(live.get("latest")).toEqual(SNAPSHOT_B);
    expect(live.has("old")).toBe(false);
    expect(live.size).toBe(1);

    expect((await store.load(2 * SNAPSHOT_TTL_MS + 1)).size).toBe(0);
  });
});

describe("createSnapshotStore", () => {
  it("falls back to an in-memory store when indexedDB is missing", async () => {
    const store = createSnapshotStore(undefined);
    await store.save("2026-11-19T10:00:00Z", SNAPSHOT_A, 42);
    await expect(store.load(43)).resolves.toEqual(
      new Map([["2026-11-19T10:00:00Z", SNAPSHOT_A]]),
    );
  });

  it("persists and evicts through an indexedDB-like factory", async () => {
    const { factory, records } = createFakeIdb();
    records.set("stale", { hour: "stale", snapshot: SNAPSHOT_B, savedAt: 0 });
    const store = createSnapshotStore(factory as unknown as IDBFactory);
    await store.save("fresh", SNAPSHOT_A, 1_000);
    const live = await store.load(SNAPSHOT_TTL_MS + 1);
    expect(live.get("fresh")).toEqual(SNAPSHOT_A);
    expect(live.has("stale")).toBe(false);
    await new Promise<void>((resolve) => {
      setTimeout(resolve, 0);
    });
    expect(records.has("stale")).toBe(false);
    expect(records.get("fresh")?.savedAt).toBe(1_000);
  });
});

interface FakeRequest {
  result: unknown;
  onsuccess: (() => void) | null;
  onerror: (() => void) | null;
  onupgradeneeded: (() => void) | null;
  onblocked: (() => void) | null;
}

interface FakeRecord {
  hour: string;
  snapshot: unknown;
  savedAt: number;
}

function createTransaction(records: Map<string, FakeRecord>) {
  const transaction = {
    oncomplete: null as (() => void) | null,
    onabort: null as (() => void) | null,
    onerror: null as (() => void) | null,
    objectStore: (_name: string) => ({
      put: (record: FakeRecord) => {
        records.set(record.hour, record);
      },
      delete: (hour: string) => {
        records.delete(hour);
      },
      getAll: () => {
        const request: FakeRequest = {
          result: undefined,
          onsuccess: null,
          onerror: null,
          onupgradeneeded: null,
          onblocked: null,
        };
        queueMicrotask(() => {
          request.result = Array.from(records.values());
          request.onsuccess?.();
        });
        return request;
      },
    }),
  };
  queueMicrotask(() => {
    transaction.oncomplete?.();
  });
  return transaction;
}

function createFakeIdb() {
  const records = new Map<string, FakeRecord>();
  const factory = {
    open: (_name: string, _version: number) => {
      const request: FakeRequest = {
        result: undefined,
        onsuccess: null,
        onerror: null,
        onupgradeneeded: null,
        onblocked: null,
      };
      const database = {
        objectStoreNames: { contains: () => true },
        createObjectStore: () => ({}),
        transaction: (_storeName: string, _mode: string) =>
          createTransaction(records),
      };
      queueMicrotask(() => {
        request.result = database;
        request.onupgradeneeded?.();
        request.onsuccess?.();
      });
      return request;
    },
  };
  return { factory, records };
}
