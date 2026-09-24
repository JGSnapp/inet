"""Capture the live agent activity panel for an active research run."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'deep-research-20260924'
QUERY='Industrial heat decarbonization landscape 2025-2040'

async def main():
    completed='--completed' in sys.argv
    filename='07-importance-aware-result.png' if completed else '06-live-agent-activity.png'
    errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1600,'height':1050},device_scale_factor=1)
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        await page.goto('http://127.0.0.1:8501',wait_until='networkidle',timeout=120000)
        await page.get_by_text('Сервер подключён',exact=True).wait_for(timeout=30000)
        await page.locator('.history button').filter(has_text=QUERY).first.click()
        await page.locator('.research-dashboard' if completed else '.agent-live').wait_for(timeout=30000)
        await page.evaluate('window.scrollTo(0,0)')
        await page.screenshot(path=str(OUT/filename),full_page=False,animations='disabled')
        await browser.close()
    print(json.dumps({'screenshot':filename,'browser_errors':errors},ensure_ascii=False))
    if errors:raise RuntimeError(errors)

if __name__=='__main__':asyncio.run(main())
