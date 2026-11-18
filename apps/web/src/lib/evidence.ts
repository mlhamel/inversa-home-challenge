import { fromJson, type JsonValue } from "@bufbuild/protobuf";
import { timestampDate } from "@bufbuild/protobuf/wkt";
import {
  EvidenceRefsSchema,
  type EvidenceRefs,
} from "../generated/inversa/v1/grounding_pb";

export type { EvidenceRefs };

export function parseEvidence(frame: unknown): EvidenceRefs | null {
  if (typeof frame !== "object" || frame === null) return null;
  try {
    const refs = fromJson(EvidenceRefsSchema, frame as JsonValue);
    const hasRefs = refs.fireIds.length > 0 || refs.stationIds.length > 0;
    if (!hasRefs && !refs.focusTimestamp && !refs.bboxFocus) return null;
    return refs;
  } catch {
    return null;
  }
}

export function evidenceFocusDate(refs: EvidenceRefs | null): Date | null {
  if (refs?.focusTimestamp) return timestampDate(refs.focusTimestamp);
  return null;
}

export function evidenceBounds(
  refs: EvidenceRefs | null,
): [[number, number], [number, number]] | null {
  const box = refs?.bboxFocus;
  if (box === undefined) return null;
  return [
    [Math.min(box.minLon, box.maxLon), Math.min(box.minLat, box.maxLat)],
    [Math.max(box.minLon, box.maxLon), Math.max(box.minLat, box.maxLat)],
  ];
}
