import asyncio
import ipaddress
import re
import time
from urllib.parse import urlsplit
import httpx
from providers import request,public_url

DEFAULT_SOURCES=['https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt']

def parse_proxies(text):
    found=[]
    for match in re.finditer(r'(?:(https?|socks4|socks5)://)?((?:\d{1,3}\.){3}\d{1,3}):(\d{2,5})',text):
        scheme,host,port=match.groups()
        try:
            if not ipaddress.ip_address(host).is_global or not 1<=int(port)<=65535: continue
        except ValueError: continue
        # httpx supports HTTP CONNECT and SOCKS5; unsupported protocols stay out of the active pool.
        if scheme=='socks4': continue
        found.append(f'{scheme or "http"}://{host}:{port}')
    return list(dict.fromkeys(found))

class ProxyPool:
    def __init__(self,store): self.store=store

    async def refresh(self,sources=None):
        sources=sources or self.store.load('settings','proxy_sources',DEFAULT_SOURCES)
        candidates=[];errors=[]
        for url in sources[:8]:
            try: candidates.extend(parse_proxies((await request(url)).text))
            except Exception as exc: errors.append({'source':url,'error':type(exc).__name__})
        gate=asyncio.Semaphore(8)
        async def check(url):
            async with gate:
                start=time.monotonic();ok=False
                try:
                    async with httpx.AsyncClient(proxy=url,timeout=6,trust_env=False) as client:
                        response=await client.get('https://example.com',headers={'Accept-Encoding':'identity'})
                        ok=response.status_code==200 and 'Example Domain' in response.text
                except Exception: pass
                record={'id':url,'url':url,'healthy':ok,'latency_ms':round((time.monotonic()-start)*1000),'checked_at':time.time(),'expires_at':time.time()+900}
                self.store.save('proxies',url,record)
                return ok
        tested=list(dict.fromkeys(candidates))[:80]
        checked=await asyncio.gather(*(check(url) for url in tested))
        return {'tested':len(tested),'healthy':sum(checked),'errors':errors}

    def choose(self):
        good=[p for p in self.store.all('proxies') if p['healthy'] and p['expires_at']>time.time()]
        return min(good,key=lambda p:p['latency_ms'])['url'] if good else None

    def failed(self,url):
        record=self.store.load('proxies',url)
        if record: record['healthy']=False;self.store.save('proxies',url,record)
