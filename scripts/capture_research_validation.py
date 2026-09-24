"""Capture the live UI after the network acceptance suite."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'network-research-20260924'

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1600,'height':1050},device_scale_factor=1)
        errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
        await page.goto('http://127.0.0.1:8501',wait_until='networkidle',timeout=120000)
        await page.get_by_text('Сервер подключён',exact=True).wait_for(timeout=30000)
        cases=[
            ('01-postgresql-research.png','PostgreSQL 17 logical replication improvements'),
            ('02-eu-ai-act-research.png','EU AI Act general-purpose AI obligations'),
            ('03-cpython-research.png','CPython free-threaded Python 3.13 3.14'),
        ]
        for filename,query in cases:
            button=page.locator('.history button').filter(has_text=query).first
            await button.click();await page.locator('.research-dashboard').wait_for(timeout=30000)
            await page.screenshot(path=str(OUT/filename),full_page=False,animations='disabled')
        await page.get_by_role('button',name='Карта запросов',exact=True).click()
        await page.locator('.map-layout').wait_for(timeout=30000)
        await page.screenshot(path=str(OUT/'04-research-route.png'),full_page=False,animations='disabled')
        await page.get_by_role('button',name='Автоматизация',exact=True).click()
        await page.get_by_text('Лаборатория инструментов',exact=True).wait_for(timeout=30000)
        await page.evaluate('window.scrollTo(0, 0)')
        await page.get_by_role('tab',name='Repair-loop',exact=True).click()
        await page.locator('.pipeline-card').first.wait_for(timeout=30000)
        await page.evaluate('window.scrollTo(0, 0)')
        await page.screenshot(path=str(OUT/'05-parsing-pipelines.png'),full_page=False,animations='disabled')
        await page.get_by_role('tab',name='Очередь',exact=True).click()
        await page.locator('.jobs-grid .job-card').first.wait_for(timeout=30000)
        await page.screenshot(path=str(OUT/'06-operations.png'),full_page=False,animations='disabled')
        await page.get_by_role('button',name='Поиск',exact=True).click()
        unique_query='https://example.com/inet-unique-tool-test-404'
        await page.locator('.history button').filter(has_text=unique_query).first.click()
        await page.locator('.attempt-details').wait_for(timeout=30000)
        await page.locator('.attempt-details summary').click()
        await page.evaluate('window.scrollTo(0, 0)')
        await page.screenshot(path=str(OUT/'07-unique-tools-failures.png'),full_page=False,animations='disabled')
        await browser.close()
        manifest={'screenshots':[item[0] for item in cases]+['04-research-route.png','05-parsing-pipelines.png','06-operations.png','07-unique-tools-failures.png'],'browser_errors':errors}
        (OUT/'screenshots.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(manifest,ensure_ascii=False))
        if errors:raise RuntimeError(errors)

if __name__=='__main__':asyncio.run(main())
