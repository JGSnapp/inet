"""Read-only external checks; no paid APIs or model calls."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import providers

async def main():
    results=[]
    for name,url in [('httpx','https://example.com/'),('curl_cffi','https://example.com/'),('playwright_wait','https://example.com/'),('official','https://api.github.com/repos/python/cpython')]:
        try:
            result=await providers.execute(name,url,5)
            results.append({'provider':name,'ok':bool(result.get('content')),'chars':len(result.get('content',''))})
        except Exception as exc:results.append({'provider':name,'ok':False,'error':type(exc).__name__+': '+str(exc)[:150]})
    print(json.dumps(results))
if __name__=='__main__':asyncio.run(main())
