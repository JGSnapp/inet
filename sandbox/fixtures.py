"""Twenty deterministic web fixtures; never reflects arbitrary scripts or paths."""
import json
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlsplit

KINDS=['article','navigation','unicode','table','list','json','rss','atom','sitemap','redirect','empty','blocked','notfound','javascript','metadata','nested','entities','large','links','whitespace']

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try: index=int(urlsplit(self.path).path.strip('/'))
        except ValueError: self.send_error(404);return
        if not 1<=index<=20: self.send_error(404);return
        kind=KINDS[index-1];token=f'INET_EVIDENCE_{index:02}'
        text=token+' Verified reference material about open web research, reliable information retrieval and reproducible extraction. '*3
        status=200;content_type='text/html; charset=utf-8'
        content=f'<html><head><title>Reference {index}</title></head><body><article>{text}</article></body></html>'
        if kind=='navigation': content=f'<nav>Home links</nav><main>{text}</main><footer>footer</footer>'
        if kind=='unicode': content=f'<main>{text} Исследование, 中文, العربية, café.</main>'
        if kind=='table': content=f'<table><tr><th>Reference</th></tr><tr><td>{text}</td></tr></table>'
        if kind=='list': content=f'<ul><li>{text}</li></ul>'
        if kind=='json': content=json.dumps({'title':'Reference','content':text});content_type='application/json'
        if kind=='rss': content=f'<rss version="2.0"><channel><title>Reference</title><item><title>{token}</title><description>{text}</description><link>https://example.com</link></item></channel></rss>';content_type='application/rss+xml'
        if kind=='atom': content=f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>{token}</title><content>{text}</content><link href="https://example.com"/></entry></feed>';content_type='application/atom+xml'
        if kind=='sitemap': content=f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/{token}</loc></url></urlset>';content_type='application/xml'
        if kind=='redirect':
            self.send_response(302);self.send_header('Location','/1');self.end_headers();return
        if kind=='empty': content=''
        if kind=='blocked': content='<html><body>Verify you are human. Access denied.</body></html>'
        if kind=='notfound': status=404;content='Not found'
        if kind=='javascript': content=f'<html><body><div id="content"></div><script>setTimeout(()=>document.querySelector("#content").textContent={json.dumps(text)},150)</script></body></html>'
        if kind=='metadata': content=f'<html><head><script type="application/ld+json">{json.dumps({"description":text})}</script></head><body>{text}</body></html>'
        if kind=='nested': content=f'<div><section><p><span>{text}</span></p></section></div>'
        if kind=='entities': content=f'<p>{text} &amp; &lt; data &gt;</p>'
        if kind=='large': content=f'<main>{text*100}</main>'
        if kind=='links': content=f'<a href="https://example.com">{text}</a>'
        if kind=='whitespace': content=f'<main>\n\n\t {text} \n\n</main>'
        raw=content.encode();self.send_response(status);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def log_message(self,*args): pass

if __name__=='__main__': HTTPServer(('0.0.0.0',8081),Handler).serve_forever()
