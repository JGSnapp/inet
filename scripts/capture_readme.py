"""Capture README screenshots and a demo video from a running INET server.

    inet serve                                   # in another terminal, with an LLM configured
    python scripts/capture_readme.py --lang en   # docs/assets/*.png + demo.webm
    python scripts/capture_readme.py --lang ru   # docs/assets/*-ru.png + demo-ru.webm
    python scripts/make_demo_video.py --lang en  # demo.mp4 + demo.gif

English and Russian captures can run at the same time: each waits for its own question.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import time
import urllib.request
from pathlib import Path

from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
BASE = "http://127.0.0.1:8000"
VIEWPORT = {"width": 1440, "height": 900}

UI = {
    "en": {
        "locale": "en-US",
        "question": "Open-source alternatives to Perplexity for self-hosted AI web search in 2026",
        "open_nav": "Open navigation",
        "ask": "Ask anything…",
        "close_activity": "Close activity",
        "pages": {"Traces": "traces", "Library": "library", "System": "system"},
    },
    "ru": {
        "locale": "ru-RU",
        "question": "Open-source альтернативы Perplexity для self-hosted AI-поиска в 2026 году",
        "open_nav": "Открыть навигацию",
        "ask": "Спросите что угодно…",
        "close_activity": "Закрыть ход исследования",
        "pages": {"Маршруты": "traces", "Библиотека": "library", "Система": "system"},
    },
}


def run_for(question: str) -> dict:
    with urllib.request.urlopen(BASE + "/api/runs", timeout=10) as response:
        runs = [r for r in json.load(response) if r.get("query") == question]
    return max(runs, key=lambda r: r.get("created_at", 0)) if runs else {}


async def wait_for_run(page: Page, question: str, timeout: float, shots: dict[float, Path]) -> dict:
    """Poll until the run for `question` finishes, taking screenshots after the given delays."""
    started = time.monotonic()
    pending = dict(shots)
    while time.monotonic() - started < timeout:
        elapsed = time.monotonic() - started
        for delay, path in list(pending.items()):
            if elapsed >= delay:
                await page.screenshot(path=path)
                pending.pop(delay)
        run = run_for(question)
        if run.get("status") in ("completed", "failed", "cancelled"):
            return run
        await page.wait_for_timeout(1000)
    raise TimeoutError("run did not finish")


async def nav(page: Page, ui: dict, name: str) -> None:
    """Click an item in the navigation drawer, opening the drawer first when it is collapsed."""
    button = page.get_by_role("button", name=name, exact=True)
    if not await button.is_visible():
        await page.get_by_role("button", name=ui["open_nav"]).click()
        await page.wait_for_timeout(500)
    await button.click()
    await page.wait_for_timeout(600)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=sorted(UI), default="en")
    parser.add_argument("--question", help="deep research question (default depends on --lang)")
    args = parser.parse_args()
    ui = UI[args.lang]
    question = args.question or ui["question"]
    suffix = "" if args.lang == "en" else f"-{args.lang}"

    def out(name: str) -> Path:
        return OUT / f"{name}{suffix}.png"

    OUT.mkdir(parents=True, exist_ok=True)
    video_dir = OUT / f"_video{suffix}"
    shutil.rmtree(video_dir, ignore_errors=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport=VIEWPORT,
            locale=ui["locale"],
            color_scheme="dark",
            record_video_dir=str(video_dir),
            record_video_size=VIEWPORT,
        )
        started = time.monotonic()
        marks: dict[str, float] = {}
        page = await context.new_page()
        await page.goto(f"{BASE}/?lang={args.lang}", wait_until="networkidle")
        await page.wait_for_timeout(1200)
        await page.screenshot(path=out("home"))

        # Ask a deep research question; the video is sped up later between the marks.
        box = page.get_by_placeholder(ui["ask"])
        await box.click()
        await box.type(question, delay=35)
        await page.locator("select").first.select_option(index=1)
        await page.wait_for_timeout(400)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2500)
        await page.locator(".inline-progress").first.wait_for(timeout=30000)
        await page.locator(".inline-progress").first.click()
        marks["submitted"] = time.monotonic() - started
        run = await wait_for_run(page, question, 1800, {100: out("activity")})
        marks["finished"] = time.monotonic() - started
        await page.wait_for_timeout(3000)
        close = page.get_by_role("button", name=ui["close_activity"])
        if await close.count():
            await close.first.click()
        await page.wait_for_timeout(1500)
        await page.screenshot(path=out("deep-answer"))
        for _ in range(8):
            await page.mouse.wheel(0, 450)
            await page.wait_for_timeout(700)
        marks["end"] = time.monotonic() - started
        stats = (run.get("result") or {}).get("research_stats", {})
        print(args.lang, "deep:", run.get("status"), json.dumps(stats)[:600], flush=True)

        for label, name in ui["pages"].items():
            await nav(page, ui, label)
            await page.wait_for_timeout(1200)
            await page.screenshot(path=out(name))
        await context.close()
        await browser.close()

    videos = sorted(video_dir.glob("*.webm"))
    if videos:
        shutil.move(videos[-1], OUT / f"demo{suffix}.webm")
        (OUT / f"demo{suffix}-marks.json").write_text(json.dumps(marks))
    shutil.rmtree(video_dir, ignore_errors=True)
    print("saved to", OUT, marks)


if __name__ == "__main__":
    asyncio.run(main())
