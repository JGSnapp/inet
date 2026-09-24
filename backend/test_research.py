import asyncio
import json
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import providers
from api import app
from research import Research
from store import Store

def test_fallback_cache_and_inflight(tmp_path, monkeypatch):
    calls=[]
    async def execute(p,q,n):
        calls.append(p)
        if p=='broken': raise ValueError('blocked')
        return {'sources':[{'url':'https://example.com','title':'Example','snippet':'evidence'}]}
    monkeypatch.setattr(providers,'available',lambda mode:['broken','working'])
    monkeypatch.setattr(providers,'execute',execute)
    async def scenario():
        store=Store(str(tmp_path/'state.db')); service=Research(store)
        run=service.submit('research')
        assert service.submit('research')['id']==run['id']
        await service.tasks[run['id']]
        done=store.get('runs',run['id'])
        assert done['status']=='completed'
        assert calls==['broken','working']
        assert any(e['status']=='error' for e in done['events'])
        second=service.submit('research'); await service.tasks[second['id']]
        assert store.get('runs',second['id'])['cached'] is True
        assert len(calls)==2
        store.db.close()
    asyncio.run(scenario())

def test_unique_tools_mode_never_invokes_provider_twice(tmp_path,monkeypatch):
    calls=[]
    async def execute(provider,*_):
        calls.append(provider)
        if provider=='broken': raise ValueError('blocked')
        return {'sources':[{'url':'https://example.com','title':'Example','snippet':'evidence'}]}
    monkeypatch.setattr(providers,'available',lambda mode:['broken','broken','working'])
    monkeypatch.setattr(providers,'execute',execute)
    async def scenario():
        store=Store(str(tmp_path/'state.db')); service=Research(store)
        run=service.submit('unique tool test',fresh=True,unique_tools=True)
        await service.tasks[run['id']]
        done=store.get('runs',run['id'])
        assert done['status']=='completed'
        assert done['unique_tools'] is True
        assert calls==['broken','working']
        assert any(e['status']=='skipped' and 'уже использован' in e['detail'] for e in done['events'])
        store.db.close()
    asyncio.run(scenario())

def test_negative_cache_recovery_and_quota(tmp_path,monkeypatch):
    monkeypatch.setattr(providers,'available',lambda mode:['tavily'])
    monkeypatch.setenv('TAVILY_MONTHLY_LIMIT','0')
    monkeypatch.setenv('ENABLE_LLM','false')
    async def scenario():
        store=Store(str(tmp_path/'state.db')); service=Research(store)
        run=service.submit('missing'); await service.tasks[run['id']]
        assert store.get('runs',run['id'])['status']=='failed'
        assert len(store.list('cases'))==1
        assert any(e['status']=='skipped' for e in store.get('runs',run['id'])['events'])
        run=service.submit('missing'); await service.tasks[run['id']]
        assert store.get('runs',run['id'])['cached']
        assert not store.reserve('tavily',0)
        assert store.reserve('tavily',1)
        assert not store.reserve('tavily',1)
        store.cache('expired',{'x':1},-1)
        assert store.cached('expired') is None
        store.db.close()
    asyncio.run(scenario())

def test_cancel(tmp_path,monkeypatch):
    async def execute(*args): await asyncio.sleep(10)
    monkeypatch.setattr(providers,'execute',execute)
    monkeypatch.setattr(providers,'available',lambda mode:['slow'])
    async def scenario():
        store=Store(str(tmp_path/'state.db')); service=Research(store)
        run=service.submit('slow'); task=service.tasks[run['id']]
        await asyncio.sleep(.05); task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        assert store.get('runs',run['id'])['status']=='cancelled'
        assert not service.inflight
        store.db.close()
    asyncio.run(scenario())

@pytest.mark.parametrize('url',['http://127.0.0.1','http://[::1]','http://169.254.169.254','file:///etc/passwd','http://user:pass@example.com'])
def test_private_urls(url):
    with pytest.raises(ValueError): asyncio.run(providers.public_url(url))

def test_content_quality():
    with pytest.raises(ValueError): providers.validate_content('too short')
    with pytest.raises(ValueError): providers.validate_content('Verify you are human '+'.'*150)
    assert providers.normalize_url('https://EXAMPLE.COM#fragment')=='https://example.com/'

def test_api_and_persistence(tmp_path,monkeypatch):
    monkeypatch.setenv('RUNTIME_DB',str(tmp_path/'state.db'))
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        assert client.post('/api/runs',json={'query':'  '}).status_code==422
        assert client.post('/api/runs',json={'query':'x','limit':100}).status_code==422
        assert client.get('/api/runs/unknown').status_code==404
        assert len(client.get('/api/resources').json()['resources'])>100
        app.state.store.put('runs','interrupted',{'id':'interrupted','status':'running'})
    with TestClient(app) as client:
        assert client.get('/api/runs/interrupted').json()['status']=='interrupted'

def test_catalog_provenance():
    resources=json.loads(Path(__file__).with_name('resources.json').read_text(encoding='utf-8'))['resources']
    assert len({r['url'] for r in resources})==len(resources)
    assert all(r['description'] and r['provenance'] for r in resources)

def test_checkpoint_resume(tmp_path,monkeypatch):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    started=asyncio.Event()
    calls=[]
    async def execute(*args):
        calls.append(1)
        started.set()
        if len(calls)==1: await asyncio.sleep(10)
        return {'sources':[{'url':'https://example.com','title':'Example','snippet':'found'}]}
    monkeypatch.setattr(providers,'available',lambda mode:['test'])
    monkeypatch.setattr(providers,'execute',execute)
    async def scenario():
        store=Store(str(tmp_path/'runtime.db'))
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path/'checkpoints.db')) as saver:
            service=Research(store,saver)
            run=service.submit('checkpoint'); task=service.tasks[run['id']]
            await started.wait(); task.cancel(); await asyncio.gather(task,return_exceptions=True)
        async with AsyncSqliteSaver.from_conn_string(str(tmp_path/'checkpoints.db')) as saver:
            service=Research(store,saver)
            await service.resume(run['id']); await service.tasks[run['id']]
            assert store.get('runs',run['id'])['status']=='completed'
            assert len(calls)==2
        store.db.close()
    asyncio.run(scenario())

def test_compressed_http_response(monkeypatch):
    import gzip
    import httpx
    original_client=httpx.AsyncClient
    payload=b'<html><body>'+b'Useful page content. '*20+b'</body></html>'
    def transport(request):
        return httpx.Response(200,headers={'Content-Encoding':'gzip'},content=gzip.compress(payload))
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kwargs:original_client(transport=httpx.MockTransport(transport),**kwargs))
    result=asyncio.run(providers.request('https://example.com',trusted=True))
    assert result.content==payload
