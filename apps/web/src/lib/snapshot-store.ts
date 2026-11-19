import type { Snapshot } from "./types";

export const SNAPSHOT_TTL_MS = 7 * 24 * 3_600_000;

const DB_NAME = "inversa-snapshots";
const DB_VERSION = 1;
const STORE_NAME = "snapshots";

export interface SnapshotStore {
  load(now: number): Promise<Map<string, Snapshot>>;
  save(hour: string, snapshot: Snapshot, now: number): Promise<void>;
}

interface StoredSnapshot {
  hour: string;
  snapshot: Snapshot;
  savedAt: number;
}

export function filterExpired(
  entries: StoredSnapshot[],
  now: number,
  ttlMs: number,
): StoredSnapshot[] {
  return entries.filter((entry) => now - entry.savedAt < ttlMs);
}

export function createInMemorySnapshotStore(): SnapshotStore {
  const entries = new Map<string, StoredSnapshot>();
  return {
    async load(now) {
      const liveEntries = filterExpired(
        Array.from(entries.values()),
        now,
        SNAPSHOT_TTL_MS,
      );
      const liveHours = new Set(liveEntries.map((entry) => entry.hour));
      const staleHours: string[] = [];
      for (const hour of entries.keys()) {
        if (!liveHours.has(hour)) staleHours.push(hour);
      }
      for (const hour of staleHours) entries.delete(hour);
      return new Map(liveEntries.map((entry) => [entry.hour, entry.snapshot]));
    },
    async save(hour, snapshot, now) {
      entries.set(hour, { hour, snapshot, savedAt: now });
    },
  };
}

export function createSnapshotStore(factory?: IDBFactory): SnapshotStore {
  let impl: SnapshotStore | null = null;
  const resolveImpl = (): SnapshotStore => {
    if (impl !== null) return impl;
    const resolvedFactory = factory ?? globalThis.indexedDB;
    impl = resolvedFactory
      ? createIdbSnapshotStore(resolvedFactory)
      : createInMemorySnapshotStore();
    return impl;
  };
  return {
    load(now) {
      return resolveImpl().load(now);
    },
    save(hour, snapshot, now) {
      return resolveImpl().save(hour, snapshot, now);
    },
  };
}

function createIdbSnapshotStore(factory: IDBFactory): SnapshotStore {
  let openPromise: Promise<IDBDatabase | null> | null = null;
  const openDb = () => {
    if (openPromise) return openPromise;
    openPromise = new Promise((resolve) => {
      const request = factory.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME)) {
          request.result.createObjectStore(STORE_NAME, { keyPath: "hour" });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    });
    return openPromise;
  };

  const withStore = async (
    mode: IDBTransactionMode,
    run: (store: IDBObjectStore) => void,
  ): Promise<boolean> => {
    const db = await openDb();
    if (db === null) return false;
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, mode);
      const store = tx.objectStore(STORE_NAME);
      run(store);
      tx.oncomplete = () => resolve(true);
      tx.onabort = () => resolve(false);
      tx.onerror = () => resolve(false);
    });
  };

  return {
    async load(now) {
      const db = await openDb();
      if (db === null) return new Map();
      const result = await new Promise<Map<string, Snapshot>>((resolve) => {
        const tx = db.transaction(STORE_NAME, "readonly");
        const request = tx.objectStore(STORE_NAME).getAll();
        request.onsuccess = () => {
          const parsed: StoredSnapshot[] = [];
          for (const raw of request.result as unknown[]) {
            const entry = toStored(raw);
            if (entry) parsed.push(entry);
          }
          const liveEntries = filterExpired(parsed, now, SNAPSHOT_TTL_MS);
          if (liveEntries.length < parsed.length) {
            const liveHours = new Set(liveEntries.map((entry) => entry.hour));
            void withStore("readwrite", (store) => {
              for (const entry of parsed) {
                if (!liveHours.has(entry.hour)) store.delete(entry.hour);
              }
            });
          }
          resolve(
            new Map(liveEntries.map((entry) => [entry.hour, entry.snapshot])),
          );
        };
        request.onerror = () => resolve(new Map());
      });
      return result;
    },
    async save(hour, snapshot, now) {
      const record: StoredSnapshot = { hour, snapshot, savedAt: now };
      await withStore("readwrite", (store) => {
        store.put(record);
      });
    },
  };
}

function toStored(value: unknown): StoredSnapshot | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Partial<StoredSnapshot>;
  if (
    typeof record.hour !== "string" ||
    typeof record.savedAt !== "number" ||
    typeof record.snapshot !== "object" ||
    record.snapshot === null
  ) {
    return null;
  }
  return record as StoredSnapshot;
}
