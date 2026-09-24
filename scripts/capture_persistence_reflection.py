"""Capture the real persistence settings and completed reflection UI."""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'autonomy-20260924'


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1600, 'height': 1000}, device_scale_factor=1)
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        await page.goto('http://127.0.0.1:8501', wait_until='networkidle', timeout=120000)
        await page.get_by_text('Сервер подключён', exact=True).wait_for(timeout=30000)

        await page.get_by_label('Новое исследование').click()
        await page.locator('.research-settings summary').click()
        await page.locator('.settings-grid').wait_for()
        await page.screenshot(path=str(OUT / '08-persistence-and-reflection-settings.png'), full_page=False, animations='disabled')

        await page.locator('.history button').filter(has_text='https://example.com').first.click()
        panel = page.locator('.reflection-panel')
        await panel.wait_for(timeout=30000)
        await panel.scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT / '09-post-answer-reflection.png'), full_page=False, animations='disabled')
        await browser.close()

    manifest = {'screenshots': ['08-persistence-and-reflection-settings.png', '09-post-answer-reflection.png'], 'browser_errors': errors}
    print(json.dumps(manifest, ensure_ascii=False))
    if errors:
        raise RuntimeError(errors)


if __name__ == '__main__':
    asyncio.run(main())
