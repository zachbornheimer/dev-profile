#!/usr/bin/env python3
"""Extract frames. Usage: grab_frames.py VIDEO OUTDIR NAME=TIME...  (TIME: s, m:ss, or h:mm:ss)

Writes OUTDIR/NAME.png at full resolution. Re-running a NAME overwrites it,
so re-extract a mid-edit frame by repeating its name with a later time.
"""

import pathlib
import subprocess
import sys


def seconds(t: str) -> float:
    total = 0.0
    for part in t.split(":"):
        total = total * 60 + float(part)
    return total


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    video, out = sys.argv[1], pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for pair in sys.argv[3:]:
        name, _, t = pair.partition("=")
        if not t:
            print(f"skip {pair!r}: expected NAME=TIME", file=sys.stderr)
            continue
        dest = out / f"{name}.png"
        # -ss before -i seeks by keyframe then decodes forward: fast and frame-accurate.
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(seconds(t)),
                "-i",
                video,
                "-frames:v",
                "1",
                str(dest),
            ],
            check=True,
        )
        print(f"{dest}  @ {t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
