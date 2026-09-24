"""Rebuild the resource catalogue without losing original claims or provenance."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

root = Path(__file__).resolve().parents[1]
source = (root / 'VISION.md').read_text(encoding='utf-8-sig')
items = {}
for match in re.finditer(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', source):
    label, raw = match.groups()
    parts = urlsplit(raw)
    url = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip('/'), urlencode([(k,v) for k,v in parse_qsl(parts.query) if not k.startswith('utm_')]), ''))
    start = source.rfind('\n\n', 0, match.start()) + 2
    end = source.find('\n\n', match.end())
    context = source[start:end if end >= 0 else len(source)].strip()
    name = re.sub(r'[*\\]', '', label)
    if name.startswith('http') or name.lower() in ('github', 'github/инструкция', 'здесь.'):
        name = parts.path.strip('/').split('/')[-1] or parts.netloc
    category = 'proxy' if 'proxy' in url.lower() or 'proxies' in url.lower() else 'reference'
    if any(x in url.lower() for x in ('search', 'exa.ai', 'tavily', 'parallel.ai', 'serp', 'yacy')): category = 'search'
    if any(x in url.lower() for x in ('crawl', 'scrap', 'jina', 'playwright', 'browser', 'curl')): category = 'fetch'
    if parts.netloc in ('t.me', 'max.ru'): category = 'community'
    entry = items.setdefault(url, dict(id=f'resource-{len(items)+1:03}', name=name, url=url, links={'homepage': url}, description=context, category=category, integration_status='candidate', verification_status='unverified', quota={'limit': None, 'period': None, 'verified_at': None}, provenance=[]))
    entry['provenance'].append({'file': 'VISION.md', 'line': source.count('\n', 0, match.start())+1, 'original_url': raw})
target = root / 'backend' / 'resources.json'
target.write_text(json.dumps({'schema_version': 1, 'resources': list(items.values())}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(f'{len(items)} unique resources -> {target}')
