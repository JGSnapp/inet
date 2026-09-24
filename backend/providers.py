"""Small, explicit adapters. Catalogue entries never execute arbitrary code."""
import asyncio
import ipaddress
import os
import socket
from contextvars import ContextVar
from urllib.parse import urlsplit, urlunsplit, urljoin

import httpx
from bs4 import BeautifulSoup

options=ContextVar('provider_options',default={})

def normalize_url(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Нужен публичный HTTP(S) URL без учётных данных.')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))

async def public_url(url):
    url = normalize_url(url)
    host = urlsplit(url).hostname
    addresses = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Локальные и служебные адреса недоступны.')
    return url

async def request(url, *, trusted=False, method='GET', proxy=None, **kwargs):
    async with httpx.AsyncClient(timeout=options.get().get('timeout',20), proxy=proxy, follow_redirects=False, trust_env=False) as client:
        for _ in range(5):
            if not trusted: await public_url(url)
            async with client.stream(method, url, **kwargs) as response:
                if response.is_redirect:
                    if method!='GET' or any(k.lower()!='accept' for k in kwargs.get('headers',{})):
                        raise ValueError('Authenticated requests cannot redirect')
                    url = urljoin(url, response.headers['location'])
                    trusted = False
                    continue
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000: raise ValueError('Ответ превышает лимит 2 МБ.')
                # aiter_bytes already decompresses; retaining Content-Encoding would decode twice.
                headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-encoding','content-length')}
                return httpx.Response(response.status_code, headers=headers, content=bytes(content), request=response.request)
    raise ValueError('Слишком много перенаправлений.')

def validate_content(text):
    minimum=options.get().get('min_chars',100)
    if len(text.strip()) < minimum: raise ValueError(f'Недостаточно содержимого (<{minimum} символов).')
    if any(marker.lower() in text.lower()[:5000] for marker in options.get().get('blocked_markers',('verify you are human', 'cf-chl-', 'captcha challenge', 'access denied', 'just a moment...'))):
        raise ValueError('Обнаружена страница проверки доступа.')
    return text[:60000]

def available(mode):
    if mode == 'fetch':
        return ['httpx','httpx_mobile'] + (['curl_cffi'] if os.getenv('ENABLE_CURL')=='true' else []) + ['trafilatura','readability','jina'] + (['playwright'] if os.getenv('ENABLE_BROWSER')=='true' else []) + (['firecrawl'] if os.getenv('FIRECRAWL_API_KEY') else [])
    return (['searxng'] if os.getenv('SEARXNG_URL') else []) + ['duckduckgo'] + (['tavily'] if os.getenv('TAVILY_API_KEY') else [])

async def execute(provider, query, limit):
    if provider in ('official','wayback','httpx_proxy','browser_agent','playwright_wait'):
        from extended_providers import execute_extended
        return await execute_extended(provider,query,limit)
    if provider == 'searxng':
        r = await request(os.environ['SEARXNG_URL'].rstrip('/')+'/search', trusted=True, params={'q': query, 'format': 'json'})
        return {'sources': [dict(url=x['url'], title=x.get('title',x['url']), snippet=x.get('content','')) for x in r.json().get('results',[])[:limit]]}
    if provider == 'tavily':
        r = await request('https://api.tavily.com/search', method='POST', json={'api_key': options.get().get('api_key') or os.environ['TAVILY_API_KEY'], 'query':query, 'max_results':limit, 'search_depth':'basic'})
        return {'sources':[dict(url=x['url'], title=x['title'], snippet=x.get('content','')) for x in r.json().get('results',[])]}
    if provider == 'duckduckgo':
        r = await request('https://html.duckduckgo.com/html/', params={'q':query})
        soup = BeautifulSoup(r.text, 'html.parser')
        from urllib.parse import parse_qs
        sources = []
        for result in soup.select('.result')[:limit]:
            a = result.select_one('.result__a')
            if not a: continue
            url = urljoin(str(r.url), a.get('href',''))
            url = parse_qs(urlsplit(url).query).get('uddg',[url])[0]
            snippet = result.select_one('.result__snippet')
            sources.append(dict(url=url, title=a.get_text(' ',strip=True), snippet=snippet.get_text(' ',strip=True) if snippet else ''))
        return {'sources': sources}
    if provider in ('httpx_mobile','trafilatura','readability'):
        await public_url(query)
        headers={'User-Agent':'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 Chrome/145 Mobile Safari/537.36'} if provider=='httpx_mobile' else {'Accept':'text/html,application/xhtml+xml'}
        r=await request(query,headers=headers)
        if provider=='trafilatura':
            from trafilatura import extract
            content=extract(r.text,include_comments=False,include_links=True,output_format='txt') or ''
            title=query
        elif provider=='readability':
            from readability import Document
            document=Document(r.text);title=document.short_title() or query
            content=BeautifulSoup(document.summary(html_partial=True),'html.parser').get_text(' ',strip=True)
        else:
            soup=BeautifulSoup(r.text,'html.parser');title=soup.title.get_text(strip=True) if soup.title else query
            for node in soup(['script','style','nav','footer']):node.decompose()
            content=soup.get_text(' ',strip=True)
        content=validate_content(content)
        return {'content':content,'status':r.status_code,'final_url':str(r.url),'sources':[dict(url=query,title=title,snippet=content[:700])]}
    await public_url(query)
    if provider == 'playwright':
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(service_workers='block',accept_downloads=False)
                async def route_request(route):
                    try:
                        await public_url(route.request.url)
                        await route.continue_()
                    except Exception: await route.abort()
                await context.route('**/*',route_request)
                page = await context.new_page()
                response = await page.goto(query,wait_until='domcontentloaded',timeout=20000)
                await page.locator(options.get().get('wait_selector','body')).wait_for(timeout=5000)
                if options.get().get('automation'):
                    from captcha import solve_widget
                    await solve_widget(page,options.get()['automation'])
                content = validate_content(await page.locator('body').inner_text(timeout=5000))
                if response and response.status >= 400: raise ValueError(f'HTTP {response.status}')
                return {'content':content,'status':response.status if response else 200,'final_url':page.url,'sources':[dict(url=page.url,title=await page.title(),snippet=content[:700])]}
            finally: await browser.close()
    if provider == 'curl_cffi':
        from curl_cffi.requests import AsyncSession
        async with AsyncSession() as session:
            response = await session.get(query,impersonate='chrome',timeout=20,allow_redirects=False)
            if response.status_code >= 300: raise ValueError(f'HTTP {response.status_code}; переход к следующему адаптеру')
            soup = BeautifulSoup(response.text[:2_000_000], 'html.parser')
            for node in soup(['script','style']): node.decompose()
            content = validate_content(soup.get_text(' ',strip=True))
            return {'content':content,'status':response.status_code,'final_url':query,'sources':[dict(url=query,title=soup.title.get_text() if soup.title else query,snippet=content[:700])]}
    if provider == 'firecrawl':
        r = await request('https://api.firecrawl.dev/v1/scrape', method='POST', headers={'Authorization': 'Bearer '+(options.get().get('api_key') or os.environ['FIRECRAWL_API_KEY'])}, json={'url':query,'formats':['markdown']})
        content = r.json().get('data',{}).get('markdown','')
        title = query
    else:
        r = await request('https://r.jina.ai/'+query if provider == 'jina' else query)
        soup = BeautifulSoup(r.text, 'html.parser')
        title = soup.title.get_text(strip=True) if soup.title else query
        for node in soup(['script','style','nav','footer']): node.decompose()
        content = soup.get_text(' ',strip=True) if provider == 'httpx' else r.text
    content = validate_content(content)
    extracted={};links=[]
    if provider=='httpx':
        extracted={name:[node.get_text(' ',strip=True) for node in soup.select(selector)[:100]] for name,selector in options.get().get('extractors',{}).items()}
        links=[urljoin(str(r.url),a['href']) for a in soup.select('a[href]')[:100]]
    return {'content':content, 'status':r.status_code, 'extracted':extracted,'links':links,'final_url':str(r.url) if provider == 'httpx' else query, 'sources':[dict(url=query,title=title,snippet=content[:700])]}
