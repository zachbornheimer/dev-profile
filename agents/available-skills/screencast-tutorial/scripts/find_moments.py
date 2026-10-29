#!/usr/bin/env python3
"""Find when phrases are spoken. Usage: find_moments.py transcript.json PHRASE..."""

import json
import sys


def mmss(ms: int) -> str:
    s = ms // 1000
    return (
        f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
        if s >= 3600
        else f"{s // 60}:{s % 60:02d}"
    )


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    with open(sys.argv[1]) as handle:
        transcript = json.load(handle)
    segments = [
        (s["offsets"]["from"], s["text"].strip()) for s in transcript["transcription"]
    ]
    missing = 0
    for phrase in sys.argv[2:]:
        hits = [(t, text) for t, text in segments if phrase.lower() in text.lower()][:3]
        if not hits:
            missing += 1
            print(f"{phrase!r}: not found")
        for t, text in hits:
            print(f"{phrase!r} → {mmss(t)}  ({t // 1000}s)  {text[:90]}")
    return 1 if missing == len(sys.argv) - 2 else 0


if __name__ == "__main__":
    sys.exit(main())
