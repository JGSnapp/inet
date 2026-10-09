"""Cut a 1080p trailer from docs/assets/demo.webm (from capture_readme.py) into trailer.mp4.

Intro card, the recording split into captioned scenes with crossfades (the research part is sped
up to a few seconds), and an outro card with the install commands. Cards and captions are rendered
with Playwright, the cut is done by ffmpeg, which must be on PATH.

    python scripts/make_trailer.py [--lang en|ru] [--research-seconds 10]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
from html import escape
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
LOGO = (ROOT / "frontend" / "public" / "icon.svg").read_text(encoding="utf-8")

W, H, FPS = 1920, 1080, 30
# The recording (1440x900) sits in a rounded window; captions go in the strip below it.
WIN_W, WIN_H, WIN_X, WIN_Y, RADIUS = 1488, 930, 216, 24, 16
CAPTION_Y = WIN_Y + WIN_H
FADE = 0.6

TEXT = {
    "en": {
        "tagline": "Free-first, self-healing web research engine",
        "sub": "for people and AI agents",
        "scenes": [
            ("Ask a question", "or paste a URL. INET plans the research for you"),
            ("An agent reads the web, free sources first", "search engines, feeds, plain HTTP, a headless browser. Paid APIs only as a last resort"),
            ("A report with sources", "every claim links to the page it came from"),
            ("Every request on a route map", "which tools ran for each query and URL, with timings and errors"),
        ],
        # The English recording shows Russian text past the route map, so stop there.
        "tail": (2.1, 0.6),
        "speed": "{minutes} min → {seconds} s",
        "outro": "Self-hosted · MIT · MCP, SDK, Tavily- and Firecrawl-compatible API",
    },
    "ru": {
        "tagline": "Движок веб-исследований: сначала бесплатное, сам себя чинит",
        "sub": "для людей и AI-агентов",
        "scenes": [
            ("Задайте вопрос", "или вставьте ссылку. INET сам спланирует исследование"),
            ("Агент читает интернет, начиная с бесплатного", "поисковики, фиды, обычный HTTP, браузер. Платные API только в крайнем случае"),
            ("Отчёт с источниками", "каждое утверждение ведёт на страницу, откуда оно взято"),
            ("Всё прозрачно", "карта маршрутов, библиотека источников и самовосстанавливающиеся пайплайны"),
        ],
        "tail": None,
        "speed": "{minutes} мин → {seconds} с",
        "outro": "Self-hosted · MIT · MCP, SDK, API, совместимый с Tavily и Firecrawl",
    },
}

INSTALL = [
    "curl -fsSL https://raw.githubusercontent.com/JGSnapp/inet/main/install.sh | sh",
    "irm https://raw.githubusercontent.com/JGSnapp/inet/main/install.ps1 | iex",
]

STYLE = """
* { margin: 0; box-sizing: border-box; }
body { width: 1920px; font-family: "Segoe UI", Inter, system-ui, sans-serif; color: #f2f3f5; }
.bg { width: 1920px; height: 1080px;
  background: radial-gradient(1200px 700px at 50% 38%, #142019 0%, #0c0e10 55%, #08090a 100%); }
.card { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 28px; }
.logo svg { display: block; }
.tagline { font-size: 46px; font-weight: 600; letter-spacing: -0.5px; text-align: center; max-width: 1500px; }
.sub { font-size: 30px; color: #9aa1a9; }
.cmd { font-family: Consolas, monospace; font-size: 25px; color: #d6dbe0; background: #121518;
  border: 1px solid #262b30; border-radius: 12px; padding: 16px 26px; }
.cmd b { color: #5fd48a; font-weight: normal; }
.repo { font-size: 34px; font-weight: 600; color: #5fd48a; margin-top: 8px; }
.note { font-size: 24px; color: #8a929a; }
.caption { height: 126px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
.caption .t { font-size: 36px; font-weight: 600; display: flex; align-items: center; gap: 18px; }
.caption .s { font-size: 23px; color: #9aa1a9; }
.pill { font-size: 21px; font-weight: 600; color: #0b0d0e; background: #5fd48a; border-radius: 999px; padding: 3px 14px; }
"""


def logo(width: int) -> str:
    return f'<div class="logo" style="width:{width}px">{LOGO.replace("<svg ", f"<svg width={width} ", 1)}</div>'


def intro_html(text: dict) -> str:
    return (
        f'<div class="bg card">{logo(420)}<div class="tagline">{escape(text["tagline"])}</div>'
        f'<div class="sub">{escape(text["sub"])}</div></div>'
    )


def outro_html(text: dict) -> str:
    cmds = "".join(f'<div class="cmd"><b>$</b> {escape(c)}</div>' for c in INSTALL)
    return (
        f'<div class="bg card" style="gap:22px">{logo(260)}<div class="tagline">{escape(text["tagline"])}</div>'
        f'<div style="height:10px"></div>{cmds}<div class="repo">github.com/JGSnapp/inet</div>'
        f'<div class="note">{escape(text["outro"])}</div></div>'
    )


def caption_html(title: str, sub: str, pill: str = "") -> str:
    badge = f'<span class="pill">{escape(pill)}</span>' if pill else ""
    return f'<div class="caption"><div class="t">{escape(title)}{badge}</div><div class="s">{escape(sub)}</div></div>'


async def render(htmls: dict[str, tuple[str, int, bool]], out: Path) -> None:
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception:  # bundled Chromium not downloaded: use the system Chrome
            browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport={"width": W, "height": H})
        for name, (body, height, transparent) in htmls.items():
            await page.set_viewport_size({"width": W, "height": height})
            await page.set_content(f"<html><head><style>{STYLE}</style></head><body>{body}</body></html>")
            await page.screenshot(path=str(out / f"{name}.png"), omit_background=transparent)
        await browser.close()


def make_frame(bg: Path, out: Path) -> None:
    """Background with a soft shadow, a transparent rounded window for the video and a thin border."""
    base = Image.open(bg).convert("RGBA")
    box = (WIN_X, WIN_Y, WIN_X + WIN_W - 1, WIN_Y + WIN_H - 1)
    shadow = Image.new("L", base.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 10, box[2], box[3] + 10), RADIUS, fill=170)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    base = Image.composite(Image.new("RGBA", base.size, (0, 0, 0, 255)), base, shadow)
    hole = Image.new("L", base.size, 255)
    ImageDraw.Draw(hole).rounded_rectangle(box, RADIUS, fill=0)
    base.putalpha(hole)
    ImageDraw.Draw(base).rounded_rectangle(box, RADIUS, outline=(255, 255, 255, 34), width=2)
    base.save(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=sorted(TEXT), default="en")
    parser.add_argument("--research-seconds", type=float, default=10, help="length of the sped-up research scene")
    parser.add_argument("--crf", type=int, default=20)
    args = parser.parse_args()
    text = TEXT[args.lang]
    name = "demo" if args.lang == "en" else f"demo-{args.lang}"
    source = ASSETS / f"{name}.webm"
    marks = json.loads((ASSETS / f"{name}-marks.json").read_text())
    duration = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(source)],
            capture_output=True, text=True, check=True,
        ).stdout
    )

    # (start, end, speed) in the recording for each captioned scene.
    research_start = marks["submitted"] + 3
    research = marks["finished"] - research_start
    scenes = [
        (0.8, research_start, 1.2),
        (research_start, marks["finished"], research / args.research_seconds),
        (marks["finished"], marks["end"], 1.0),
        (marks["end"], duration - 0.3, 1.3),
    ]
    if text["tail"]:
        seconds, rate = text["tail"]
        scenes[-1] = (marks["end"], marks["end"] + seconds, rate)
    minutes = f"{research / 60:.0f}" if research >= 300 else f"{research / 60:.1f}".replace(".0", "")
    if args.lang == "ru":
        minutes = minutes.replace(".", ",")
    speed = text["speed"].format(minutes=minutes, seconds=round(args.research_seconds))

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        htmls = {"intro": (intro_html(text), H, False), "outro": (outro_html(text), H, False), "bg": ('<div class="bg"></div>', H, False)}
        for i, (title, sub) in enumerate(text["scenes"]):
            htmls[f"cap{i}"] = (caption_html(title, sub, speed if i == 1 else ""), H - CAPTION_Y, True)
        asyncio.run(render(htmls, work))
        make_frame(work / "bg.png", work / "frame.png")

        inputs = ["-i", str(source)]
        lengths: list[float] = []
        chains: list[str] = []

        def add(path: Path, seconds: float) -> int:
            inputs.extend(["-loop", "1", "-framerate", str(FPS), "-t", f"{seconds:.3f}", "-i", str(path)])
            return inputs.count("-i") - 1

        n = add(work / "intro.png", 3.5)
        chains.append(f"[{n}:v]format=yuv420p,setsar=1[s0]")
        lengths.append(3.5)
        for i, (start, end, rate) in enumerate(scenes):
            seconds = (end - start) / rate
            frame = add(work / "frame.png", seconds)
            cap = add(work / f"cap{i}.png", seconds)
            chains.append(
                f"[0:v]trim={start:.3f}:{end:.3f},setpts=(PTS-STARTPTS)/{rate:.4f},fps={FPS},"
                f"scale={WIN_W}:{WIN_H}:flags=lanczos,pad={W}:{H}:{WIN_X}:{WIN_Y}[v{i}];"
                f"[{cap}:v]format=rgba,fade=in:st=0.35:d=0.5:alpha=1[c{i}];"
                f"[v{i}][{frame}:v]overlay=0:0:shortest=1[f{i}];"
                f"[f{i}][c{i}]overlay=0:{CAPTION_Y}:shortest=1,format=yuv420p,setsar=1[s{i + 1}]"
            )
            lengths.append(seconds)
        n = add(work / "outro.png", 6.0)
        chains.append(f"[{n}:v]format=yuv420p,setsar=1[s{len(lengths)}]")
        lengths.append(6.0)

        # Crossfade the scenes one after another.
        last, offset = "s0", 0.0
        for k in range(1, len(lengths)):
            offset += lengths[k - 1] - FADE
            out = f"x{k}"
            chains.append(f"[{last}][s{k}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[{out}]")
            last = out
        total = sum(lengths) - FADE * (len(lengths) - 1)
        chains.append(f"[{last}]fade=in:st=0:d=0.6,fade=out:st={total - 0.8:.3f}:d=0.8[v]")

        target = ASSETS / ("trailer.mp4" if args.lang == "en" else f"trailer-{args.lang}.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(chains), "-map", "[v]",
             "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
             "-r", str(FPS), "-movflags", "+faststart", str(target)],
            check=True,
        )
    print(f"{target.name}: {total:.1f}s, {target.stat().st_size / 1e6:.1f} MB (research {research:.0f}s -> {args.research_seconds:.0f}s)")


if __name__ == "__main__":
    main()
