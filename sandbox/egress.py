"""Forward proxy with IP-pinned public-only egress; fixtures are the only private target."""
import asyncio
import ipaddress
import os
from urllib.parse import urlsplit

async def destination(host,port):
    if host=='fixtures' and port==8081: return host
    if port not in (80,443): raise ValueError('Port not allowed')
    infos=await asyncio.get_running_loop().getaddrinfo(host,port,type=1)
    addresses=[i[4][0] for i in infos]
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses): raise ValueError('Private address')
    return addresses[0]

async def pipe(reader,writer):
    try:
        while data:=await reader.read(65536):
            writer.write(data); await writer.drain()
    finally: writer.close()

async def handle(reader,writer):
    upstream=None
    try:
        raw=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),10)
        if len(raw)>16384: raise ValueError('Headers too large')
        lines=raw.decode('latin1').split('\r\n'); method,target,version=lines[0].split(' ')
        if method=='CONNECT':
            host,port=target.rsplit(':',1);port=int(port)
            ip=await destination(host,port)
            remote,upstream=await asyncio.wait_for(asyncio.open_connection(ip,port),10)
            writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');await writer.drain()
        else:
            p=urlsplit(target);host=p.hostname;port=p.port or 80
            if p.scheme!='http' or not host or p.username: raise ValueError('Invalid URL')
            ip=await destination(host,port)
            remote,upstream=await asyncio.wait_for(asyncio.open_connection(ip,port),10)
            headers=[h for h in lines[1:] if h and not h.lower().startswith(('proxy-','connection:','host:'))]
            path=(p.path or '/')+('?' + p.query if p.query else '')
            upstream.write((f'{method} {path} {version}\r\nHost: {host}:{port}\r\nConnection: close\r\n'+'\r\n'.join(headers)+'\r\n\r\n').encode('latin1'));await upstream.drain()
        await asyncio.wait_for(asyncio.gather(pipe(reader,upstream),pipe(remote,writer)),120)
    except Exception:
        try: writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n');await writer.drain()
        except Exception: pass
    finally:
        writer.close()
        if upstream: upstream.close()

async def main():
    server=await asyncio.start_server(handle,'0.0.0.0',8080,limit=17000)
    async with server: await server.serve_forever()

if __name__=='__main__': asyncio.run(main())
