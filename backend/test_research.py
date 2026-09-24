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
from reports import markdown_report, pdf_report

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

def test_persistence_levels_and_post_answer_reflection(tmp_path,monkeypatch):
    tools=['official','httpx','curl_cffi','jina','httpx_mobile','trafilatura','readability','playwright','browser_agent','extra']
    async def execute(*_):return {'sources':[{'url':'https://example.com','title':'Example','snippet':'evidence'}]}
    monkeypatch.setattr(providers,'available',lambda mode:tools)
    monkeypatch.setattr(providers,'execute',execute)
    async def scenario():
        store=Store(str(tmp_path/'state.db'));service=Research(store)
        assert service.ranked_plan(tools,'example.com',1)==tools[:4]
        assert len(service.ranked_plan(tools,'example.com',2))==6
        assert len(service.ranked_plan(tools,'example.com',3))==8
        assert len(service.ranked_plan(tools,'example.com',4))==len(tools)
        run=service.submit('reflection test',fresh=True,reflection_enabled=True,reflection_level=1)
        await service.tasks[run['id']]
        if run['id'] in service.reflection_tasks:await service.reflection_tasks[run['id']]
        done=store.get('runs',run['id'])
        assert done['reflection']['status']=='completed'
        assert done['reflection']['summary']['events_analyzed']>0
        store.db.close()
    asyncio.run(scenario())

def test_agent_owns_deep_search_plan_and_never_exceeds_120_messages(tmp_path,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','false')
    calls=[]
    monkeypatch.setattr(providers,'available',lambda mode:['searcher'] if mode=='search' else ['fetcher'])
    async def execute(provider,query,limit):
        calls.append((provider,query))
        if provider=='searcher':
            suffix=str(abs(hash(query))%100000)
            return {'sources':[{'url':f'https://example.com/{suffix}','title':query,'snippet':'relevant result'}]}
        return {'content':'Useful independently verified source content. '*20,'sources':[{'url':query,'title':'Source','snippet':'evidence'}]}
    monkeypatch.setattr(providers,'execute',execute)
    async def scenario():
        store=Store(str(tmp_path/'state.db'));service=Research(store)
        run=service.submit('compare open and commercial 3D generation systems',deep=True,fresh=True,reflection_enabled=False,persistence_level=4)
        await service.tasks[run['id']]
        done=store.get('runs',run['id'])
        assert done['status']=='completed'
        assert done['result']['provider']=='agentic'
        assert done['call_budget']['used']<=120
        assert done['result']['research_stats']['agent_messages_used']==done['call_budget']['used']
        assert done['result']['research_stats']['tool_calls_used']==done['tool_budget']['used']
        stages=[event['stage'] for event in done['events']]
        assert stages.index('agent_plan')<next(i for i,stage in enumerate(stages) if stage.startswith('agent_search:'))
        assert any(stage.startswith('agent_fetch:') for stage in stages)
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

def test_followups_are_serialized_and_rerun_is_fresh(tmp_path,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','false')
    entered=[]
    async def execute(provider,query,limit):
        entered.append(query)
        await asyncio.sleep(.04)
        return {'sources':[{'url':f'https://example.com/{len(entered)}','title':query,'snippet':'Useful evidence for the answer.'}]}
    monkeypatch.setattr(providers,'available',lambda mode:['test'])
    monkeypatch.setattr(providers,'execute',execute)
    async def scenario():
        store=Store(str(tmp_path/'state.db'));service=Research(store)
        root=service.submit('initial question',fresh=True,reflection_enabled=False)
        await service.tasks[root['id']]
        first=service.submit_followup(root['id'],'first follow-up')
        second=service.submit_followup(first['id'],'second follow-up')
        assert store.get('runs',second['id'])['status']=='queued'
        await asyncio.gather(service.tasks[first['id']],service.tasks[second['id']])
        first_done=store.get('runs',first['id']);second_done=store.get('runs',second['id'])
        assert first_done['status']==second_done['status']=='completed'
        assert first_done['thread_id']==second_done['thread_id']==root['id']
        assert second_done['parent_id']==first['id']
        rerun=service.rerun(root['id'])
        assert rerun['rerun_of']==root['id'] and rerun['id']!=root['id']
        await service.tasks[rerun['id']]
        store.db.close()
    asyncio.run(scenario())

def test_markdown_and_pdf_exports():
    run={'id':'abc','query':'Тестовый отчёт','status':'completed','result':{'answer':'Краткий **ответ**.','research_stats':{'sites_read':1,'sites_unread':0},'sources':[{'title':'Источник','url':'https://example.com'}]},'reflection':{'status':'completed','level':2,'summary':{'recovered':1,'alternatives':0,'failed_experiments':0}}}
    markdown=markdown_report(run)
    assert '# Тестовый отчёт' in markdown and 'https://example.com' in markdown
    pdf=pdf_report(run)
    assert pdf.startswith(b'%PDF-') and len(pdf)>1000

def test_synthesis_budget_is_reserved_and_fallback_is_not_raw_pages(tmp_path,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','true')
    store=Store(str(tmp_path/'state.db'));service=Research(store)
    run={'id':'budget','status':'running','events':[],'call_budget':{'scope':'agent_messages','limit':120,'used':118,'by_kind':{}},'tool_budget':{'scope':'tool_calls','limit':2,'used':2,'by_kind':{}}}
    store.put('runs','budget',run)
    assert service.reserve_tool_call('budget','fetch','https://example.com') is False
    assert service.reserve_agent_message('budget','synthesis','answer') is True
    result={'sources':[{'url':'https://example.com','title':'Example','snippet':'RAW PAGE BODY '*1000}], 'research_stats':{'sites_read':1}}
    answer=service.synthesis_fallback('question',result,'TimeoutError')
    assert 'Синтез временно недоступен' in answer
    assert 'RAW PAGE BODY' not in answer
    store.db.close()

def test_legacy_combined_budget_is_split_by_kind(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT_MESSAGE_LIMIT','120')
    monkeypatch.setenv('TOOL_CALL_LIMIT','480')
    store=Store(str(tmp_path/'state.db'));service=Research(store)
    run={'id':'legacy','status':'running','events':[],'call_budget':{'limit':120,'used':9,'by_kind':{'planner':2,'synthesis':1,'search':3,'fetch':3}}}
    store.put('runs','legacy',run)
    assert service.reserve_agent_message('legacy','planner','next') is True
    migrated=store.get('runs','legacy')
    assert migrated['call_budget']['scope']=='agent_messages'
    assert migrated['call_budget']['used']==4
    assert migrated['tool_budget']['used']==6
    assert migrated['legacy_call_budget']['used']==9
    store.db.close()

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
        assert client.post('/api/research-settings',json={'persistence_level':4,'reflection_enabled':False,'reflection_level':3}).status_code==200
        assert client.get('/api/research-settings').json()=={'persistence_level':4,'reflection_enabled':False,'reflection_level':3}
        assert client.post('/api/runs',json={'query':'  '}).status_code==422
        assert client.post('/api/runs',json={'query':'x','limit':100}).status_code==422
        assert client.get('/api/runs/unknown').status_code==404
        app.state.store.put('runs','legacy-budget',{'id':'legacy-budget','status':'completed','events':[],'call_budget':{'limit':120,'used':7,'by_kind':{'planner':1,'fetch':4}}})
        migrated=client.get('/api/runs/legacy-budget').json()
        assert migrated['call_budget']['used']==1
        assert migrated['tool_budget']['used']==6
        assert len(client.get('/api/resources').json()['resources'])>100
        app.state.store.put('runs','interrupted',{'id':'interrupted','status':'running'})
    with TestClient(app) as client:
        assert client.get('/api/runs/interrupted').json()['status']=='interrupted'

def test_catalog_provenance():
    resources=json.loads(Path(__file__).with_name('resources.json').read_text(encoding='utf-8'))['resources']
    assert len({r['url'] for r in resources})==len(resources)
    assert all(r['description'] and r['provenance'] for r in resources)
    added={r['id']:r for r in resources if r['id'] in {f'resource-{n}' for n in range(109,115)}}
    assert len(added)==6
    assert added['resource-114']['access_model']=='free_trial' and added['resource-114']['quota']['limit']==100
    assert all(added[f'resource-{n}']['verification_status']=='metadata_verified' for n in range(109,115))

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
