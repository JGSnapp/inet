"""Capture compact screenshots of the completed deep-research runs."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'deep-research-20260924'
CASES=[
    ('01-smr-global-landscape.png','Global small modular reactor market and deployment landscape'),
    ('02-industrial-heat-decarbonization.png','Industrial heat decarbonization landscape 2025-2040'),
    ('03-ai-datacenter-infrastructure.png','AI data center electricity water and grid infrastructure outlook'),
]

async def main():
    errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1600,'height':1050},device_scale_factor=1)
        page.on('pageerror',lambda exc:errors.append(str(exc)))
        await page.goto('http://127.0.0.1:8501',wait_until='networkidle',timeout=120000)
        await page.get_by_text('Сервер подключён',exact=True).wait_for(timeout=30000)
        for filename,query in CASES:
            await page.locator('.history button').filter(has_text=query).first.click()
            await page.locator('.research-dashboard').wait_for(timeout=30000)
            await page.evaluate('window.scrollTo(0,0)')
            await page.screenshot(path=str(OUT/filename),full_page=False,animations='disabled')
        details=page.locator('.attempt-details')
        await details.locator('summary').click()
        await page.screenshot(path=str(OUT/'04-ai-datacenter-failures.png'),full_page=False,animations='disabled')
        await page.get_by_role('button',name='Карта запросов',exact=True).click()
        await page.locator('.map-layout').wait_for(timeout=30000)
        await page.evaluate('window.scrollTo(0,0)')
        await page.screenshot(path=str(OUT/'05-deep-research-route.png'),full_page=False,animations='disabled')
        await browser.close()
    manifest={'screenshots':[x[0] for x in CASES]+['04-ai-datacenter-failures.png','05-deep-research-route.png','06-live-agent-activity.png','07-importance-aware-result.png'],'browser_errors':errors}
    (OUT/'screenshots.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))
    if errors:raise RuntimeError(errors)

if __name__=='__main__':asyncio.run(main())
