"""Pretty-print the POST /api/chat SSE stream on stdin.

token frames pass through as plain prose; tool_call and evidence frames render
as compact one-liners above the answer; error frames go to stderr with exit 1.
"""

import json
import os
import sys
from typing import Any

EVENT = "event: "
DATA = "data: "


def main() -> int:
    event = ""
    pending = False
    seen: set[str] = set()
    for raw in sys.stdin:
        line = raw.rstrip("\r\n")
        if line.startswith(EVENT):
            event = line[len(EVENT):].strip()
            continue
        if line.startswith(DATA):
            try:
                data = json.loads(line[len(DATA):])
            except json.JSONDecodeError as exc:
                sys.stderr.write(f"error: malformed SSE data: {exc}\n")
                return 1
            if event == "token":
                text = data.get("text", "")
                if pending and not text.startswith("\n"):
                    sys.stdout.write("\n")
                    pending = False
                sys.stdout.write(text)
                sys.stdout.flush()
            elif event == "tool_call":
                sys.stdout.write(f"\n⏺ {data.get('tool', '')}()")
                sys.stdout.flush()
                pending = True
            elif event == "evidence":
                note = _evidence_note(data)
                if note and note not in seen:
                    seen.add(note)
                    sys.stdout.write(f"\n  ⤷ {note}")
                    sys.stdout.flush()
                    pending = True
            elif event == "error":
                sys.stdout.write("\n")
                sys.stderr.write(f"error: {data.get('message', 'unknown')}\n")
                return 1
            event = ""
    sys.stdout.write("\n")
    return 0


def _evidence_note(data: dict[str, Any]) -> str:
    stations = ", ".join(str(s) for s in data.get("station_ids") or [])
    fires = ", ".join(str(f) for f in data.get("fire_ids") or [])
    focus = data.get("focus_timestamp") or ""
    parts = [
        part
        for part in (
            f"station {stations}" if stations else "",
            f"fires {fires}" if fires else "",
            f"focus {focus}" if focus else "",
        )
        if part
    ]
    return " · ".join(parts)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        sys.exit(0)
