"""Exercise the built UI against the real API in an isolated local runtime."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]

async def smoke():
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        async def proxy(route):
            response=await route.fetch(url=route.request.url.replace('127.0.0.1:3007','127.0.0.1:8007'))
            await route.fulfill(response=response)
        await page.route('**/api/**',proxy)
        await page.goto('http://127.0.0.1:3007')
        await page.get_by_text('Сервер подключён',exact=True).wait_for()
        out=ROOT/'artifacts';out.mkdir(exist_ok=True)
        await page.screenshot(path=str(out/'home-desktop.png'),full_page=True)
        await page.get_by_role('button',name='Инструменты',exact=True).click()
        await page.get_by_label('Найти инструмент').fill('Firecrawl')
        assert await page.locator('.resource-card').count()>0
        await page.get_by_role('button',name='Карта запросов',exact=True).click()
        await page.get_by_text('У каждого ответа есть путь').wait_for()
        await page.get_by_role('button',name='Поиск',exact=True).click()
        await page.get_by_label('Поисковый запрос или URL').fill('https://example.com')
        await page.get_by_role('button',name='Начать исследование',exact=True).click()
        await page.locator('.answer-section h1').wait_for()
        await page.wait_for_function("document.querySelector('.answer-section .eyebrow')?.textContent.includes('Готово') || document.querySelector('.answer-section .eyebrow')?.textContent.includes('Ошибка')",timeout=150000)
        result=await page.locator('.answer-section').inner_text()
        assert 'Готово' in result and 'Example Domain' in result,result
        await page.screenshot(path=str(out/'answer-desktop.png'),full_page=True)
        await page.get_by_role('button',name='Карта запросов',exact=True).click()
        assert await page.locator('.flow-node').count()>0
        await page.locator('.flow-node').first.click()
        await page.get_by_text('Детали этапа',exact=True).wait_for()
        await page.screenshot(path=str(out/'map-desktop.png'),full_page=True)
        await page.get_by_role('button',name='Система',exact=True).click()
        await page.get_by_text('Система под наблюдением').wait_for()
        await page.get_by_role('button',name='Автоматизация',exact=True).click()
        await page.get_by_text('Лаборатория инструментов').wait_for()
        await page.get_by_role('tab',name='Настройки сайтов',exact=True).click()
        await page.get_by_role('button',name='Сохранить правила',exact=True).click()
        await page.get_by_role('status').wait_for()
        await page.get_by_role('tab',name='Парсинг',exact=True).click()
        await page.get_by_role('button',name='Сохранить план',exact=True).click()
        await page.get_by_role('button',name='Запустить',exact=True).wait_for()
        await page.get_by_role('tab',name='Подключения',exact=True).click()
        await page.get_by_label('API-ключ').fill('ui-test-not-a-real-key')
        await page.get_by_role('button',name='Сохранить ключ',exact=True).click()
        await page.wait_for_function("document.querySelector('input[type=password]')?.value === ''")
        await page.screenshot(path=str(out/'automation-desktop.png'),full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.get_by_role('button',name='Новое исследование',exact=False).click()
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.screenshot(path=str(out/'home-mobile.png'),full_page=True)
        assert not errors,errors
        print(json.dumps({'browser_errors':errors,'fetch_result':result[:700],'screenshots':str(out)},ensure_ascii=True))
        await page.unroute_all(behavior='wait')
        await browser.close()

if __name__=='__main__':
    with tempfile.TemporaryDirectory() as temp:
        env={**os.environ,'RUNTIME_DB':str(Path(temp)/'state.sqlite3'),'ENABLE_LLM':'false','ENABLE_AUTOMATION':'false'}
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        processes=[]
        try:
            processes.append(subprocess.Popen([sys.executable,'-m','uvicorn','main:app','--app-dir',str(ROOT/'backend'),'--port','8007'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags))
            processes.append(subprocess.Popen([sys.executable,'-m','http.server','3007','--bind','127.0.0.1','--directory',str(ROOT/'frontend'/'build')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags))
            for _ in range(50):
                try:
                    urllib.request.urlopen('http://127.0.0.1:8007/health',timeout=1)
                    break
                except OSError: time.sleep(.2)
            asyncio.run(smoke())
        finally:
            for process in processes:
                if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
                else: process.terminate()
            for process in processes: process.wait(timeout=10)
