"""Turn docs/assets/demo.webm (from capture_readme.py) into demo.mp4 and demo.gif.

Typing and the finished answer play in real time; the minutes of research in between are
sped up to a few seconds. Requires ffmpeg on PATH.

    python scripts/make_demo_video.py [--lang en|ru] [--wait-seconds 14] [--width 800]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="en")
    parser.add_argument("--wait-seconds", type=float, default=14, help="length of the sped-up research part")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args()

    name = "demo" if args.lang == "en" else f"demo-{args.lang}"
    marks = json.loads((ASSETS / f"{name}-marks.json").read_text())
    intro_end = marks["submitted"] + 6
    research = max(1.0, marks["finished"] - intro_end)
    speed = max(1.0, research / args.wait_seconds)
    parts = (
        f"[0:v]trim=0:{intro_end:.2f},setpts=PTS-STARTPTS[a];"
        f"[0:v]trim={intro_end:.2f}:{marks['finished']:.2f},setpts=(PTS-STARTPTS)/{speed:.3f}[b];"
        f"[0:v]trim={marks['finished']:.2f}:{marks['end']:.2f},setpts=PTS-STARTPTS[c];"
        "[a][b][c]concat=n=3:v=1:a=0,"
        f"fps={args.fps},scale={args.width}:-2:flags=lanczos"
    )
    source = str(ASSETS / f"{name}.webm")
    print(f"research {research:.0f}s -> {research / speed:.0f}s (x{speed:.1f})")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            source,
            "-filter_complex",
            parts + "[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "26",
            "-movflags",
            "+faststart",
            str(ASSETS / f"{name}.mp4"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            source,
            "-filter_complex",
            parts + ",split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];"
            "[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle[v]",
            "-map",
            "[v]",
            str(ASSETS / f"{name}.gif"),
        ],
        check=True,
    )
    for file in (f"{name}.mp4", f"{name}.gif"):
        print(file, f"{(ASSETS / file).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
