import asyncio
import base64
import json
import time
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from api import app
from automation import Automation
from contracts import AdapterSpec,DomainPolicy,ParsingPipelineSpec,result_contract
from evaluation import fixtures,judge
from pipelines import PipelineEngine,PipelineRegistry,default_pipeline,path_value
from proxies import parse_proxies
from registry import Registry
from store import Store
import providers

@pytest.fixture
def auto(tmp_path,monkeypatch):
    monkeypatch.setenv('RUNTIME_DB',str(tmp_path/'runtime.db'))
    monkeypatch.setenv('ENABLE_AUTOMATION','false')
    monkeypatch.setenv('ENABLE_LLM','false')
    store=Store();manager=Automation(store)
    yield manager
    store.db.close()

def spec(name='test-adapter',parent=None):
    return {'name':name,'mode':'fetch','code':'def run(query, limit):\n    return {"content": "example"}','requirements':['httpx==0.28.1'],'parent':parent}

def test_version_gate_and_rollback(auto):
    first=auto.registry.create(spec())
    with pytest.raises(ValueError):auto.registry.promote(first['id'])
    auto.store.save('evaluations',first['id'],{'eligible':True,'digest':first['digest']})
    auto.registry.promote(first['id'])
    for _ in range(5):auto.registry.observe(first['id'],True)
    assert auto.store.load('versions',first['id'])['status']=='active'
    second_spec=spec(parent=first['id']);second_spec['code']+='\n# revision'
    second=auto.registry.create(second_spec)
    assert '+# revision' in second['diff']
    auto.store.save('evaluations',second['id'],{'eligible':True,'digest':second['digest']})
    auto.registry.promote(second['id'])
    for _ in range(2):auto.registry.observe(second['id'],False)
    assert auto.registry.active('fetch')[0]['id']==first['id']
    assert auto.store.load('versions',second['id'])['status']=='rolled_back'
    assert auto.store.all('notices')

def test_eval_requires_evidence_and_failures():
    suite=fixtures('fetch');outputs=[]
    for fixture in suite:
        outputs.append({'ok':False,'error':'expected'} if fixture.get('failure') else {'ok':True,'result':{'content':fixture['expected'],'final_url':fixture['query'],'status':200}})
    report=judge(spec(),outputs,suite)
    assert report['eligible'] and report['passed']==20
    outputs[0]['result']['content']='invented'
    outputs[11]={'ok':True,'result':{'content':'Verify you are human','final_url':suite[11]['query'],'status':200}}
    report=judge(spec(),outputs,suite)
    assert report['passed']==18
    assert not report['details'][11]['passed']
    assert not judge(spec(),outputs[:2],suite[:2])['eligible']

def test_dependency_specs_and_parent(auto):
    for dependency in ('requests','requests>=1','git+https://github.com/x/y','--index-url=x','x==1; evil','/host/secret'):
        with pytest.raises(ValueError):AdapterSpec.model_validate({**spec(),'requirements':[dependency]})
    with pytest.raises(ValueError):auto.registry.create(spec(parent='missing'))

def test_vault_and_custom_connectors(auto,monkeypatch):
    configured=auto.save_connector({'id':'my-api','mode':'search','endpoint':'https://example.com/api','monthly_limit':4,'cost':2},'private-test-key')
    assert configured['key_configured']
    assert 'private-test-key' not in json.dumps(auto.store.all('secrets'))
    assert 'private-test-key' not in json.dumps(auto.connectors())
    assert auto.vault.get('my-api')=='private-test-key'
    assert auto.reserve('api:my-api')
    assert auto.reserve('api:my-api')
    assert not auto.reserve('api:my-api')
    async def fetch(url,**kwargs):
        assert kwargs['headers']['Authorization']=='Bearer private-test-key'
        return httpx.Response(200,json={'results':[{'url':'https://example.com','title':'Reference','content':'Evidence'}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(providers,'request',fetch)
    result=asyncio.run(auto.execute('api:my-api','q',5))
    assert result['sources'][0]['snippet']=='Evidence'
    with pytest.raises(ValueError):auto.save_connector({'id':'unsafe-api','mode':'search','endpoint':'https://example.com/api','static_params':{'api_key':'embedded'}})

def test_proxy_validation():
    text='http://127.0.0.1:80\nhttp://169.254.169.254:80\nhttp://10.0.0.1:90\nhttp://8.8.8.8:8080\n8.8.8.8:8080\nsocks5://1.1.1.1:1080\nsocks4://2.2.2.2:1080\n999.1.1.1:8080'
    assert parse_proxies(text)==['http://8.8.8.8:8080','socks5://1.1.1.1:1080']

def test_policies_and_remote_budgets(auto):
    auto.save_policy(DomainPolicy(domain='example.com',timeout=30,extractors={'title':'h1'}))
    assert auto.policy('https://example.com/a')['timeout']==30
    assert len(auto.store.all('policy_revisions'))==1
    auto.store.save('remote_quotas','test',{'remaining':1,'checked_at':time.time()})
    assert auto.budget('test',100)
    assert not auto.budget('test',100)
    auto.failed_http('httpx',429,'120')
    assert not auto.reserve('httpx')

def test_discovery_and_queue_dedup(auto,monkeypatch):
    async def fetch(url,**kwargs):
        return httpx.Response(200,json={'items':[{'id':123,'name':'real-tool','html_url':'https://github.com/org/tool','full_name':'org/tool','description':'Scraper','archived':False,'stargazers_count':500,'license':{'spdx_id':'MIT'}}]})
    monkeypatch.setattr(providers,'request',fetch)
    async def scenario():
        job=auto.enqueue('discover')
        assert auto.enqueue('discover')['id']==job['id']
        auto.start()
        result=await auto.wait_job(job['id'],5)
        assert result['status']=='completed'
        assert auto.store.load('catalog','github-123')['license']=='MIT'
        await auto.close()
    asyncio.run(scenario())

def test_emergency_job_promotes_existing_queue_entry(auto):
    routine=auto.enqueue('discover',{'query':'search engine api python'})
    urgent=auto.enqueue('discover',{'query':'search engine api python'},priority=100)
    auto.enqueue('metadata',priority=10)
    assert urgent['id']==routine['id']
    assert auto.store.load('jobs',routine['id'])['priority']==100
    ordered=sorted(auto.store.all('jobs'),key=lambda job:(-job.get('priority',0),job['created_at']))
    assert ordered[0]['id']==routine['id']

def test_evaluation_to_runtime_and_regression(auto,monkeypatch):
    version=auto.registry.create(spec())
    live=json.loads(Path(__file__).with_name('live_benchmarks.json').read_text())
    suite=fixtures('fetch')+live;expected={x['query']:x for x in suite}
    async def execute(specification,inputs,timeout):
        outputs=[]
        for item in inputs:
            f=expected.get(item['query'],{'expected':'Live content '*30})
            outputs.append({'ok':False,'error':'Expected error'} if f.get('failure') else {'ok':True,'result':{'content':f['expected'],'status':200,'final_url':item['query']}})
        return {'results':outputs,'image':'test-digest'}
    monkeypatch.setattr(auto.sandbox,'execute',execute)
    async def scenario():
        job=auto.enqueue('evaluate',{'version':version['id'],'promote':True});auto.start()
        result=await auto.wait_job(job['id'],5)
        assert result['status']=='completed',result
        assert result['result']['count']==40
        assert len(result['result']['conformance']['details'])==20
        assert auto.registry.active('fetch')[0]['status']=='canary'
        out=await auto.execute('plugin:'+version['id'],'https://another.example/path',5)
        assert out['content'].startswith('Live content')
        await auto.close()
    asyncio.run(scenario())

def test_official_formats_and_archive_guard(monkeypatch):
    from extended_providers import parsed_response,execute_extended
    def response(body,type):return httpx.Response(200,text=body,headers={'content-type':type},request=httpx.Request('GET','https://example.com/feed'))
    assert parsed_response(response('{"a":1}','application/json'),'https://example.com')['structured']=={'a':1}
    assert parsed_response(response('<rss><channel><item><title>News</title><description>text</description></item></channel></rss>','application/xml'),'https://example.com')['entries'][0]['title']=='News'
    with pytest.raises(Exception):parsed_response(response('<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>','application/xml'),'https://example.com')
    with pytest.raises(ValueError):asyncio.run(execute_extended('wayback','https://example.com',5))

def test_authenticated_redirect_does_not_leak(monkeypatch):
    original=httpx.AsyncClient;calls=[]
    def transport(request):
        calls.append(str(request.url));return httpx.Response(302,headers={'Location':'https://other.example'})
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(transport),**kwargs))
    with pytest.raises(ValueError):asyncio.run(providers.request('https://example.com',trusted=True,headers={'Authorization':'Bearer secret'}))
    assert len(calls)==1

def test_management_api(auto,monkeypatch):
    async def public(url):return url
    monkeypatch.setattr(providers,'public_url',public)
    with TestClient(app) as client:
        assert client.post('/api/keys',json={'provider':'tavily','key':'not-a-real-key'}).status_code==200
        response=client.post('/api/versions',json=spec());assert response.status_code==201
        id=response.json()['id'];assert client.post(f'/api/versions/{id}/promote').status_code==409
        assert client.post('/api/policies',json={'domain':'example.com','timeout':999}).status_code==422
        assert client.post('/api/policies',json={'domain':'example.com','timeout':25}).status_code==200
        assert client.post('/api/crawls',json={'id':'test-plan','urls':['https://example.com'],'interval_seconds':2}).status_code==422
        assert client.post('/api/crawls',json={'id':'test-plan','urls':['https://example.com']}).status_code==200
        control=client.get('/api/control').json()
        assert len(control['versions'])==1 and len(control['crawls'])==1
        assert 'not-a-real-key' not in json.dumps(control)

def test_sandbox_unavailable_fails_closed(auto,monkeypatch):
    from sandbox import SandboxUnavailable
    async def fail(*args,**kwargs):raise SandboxUnavailable('No runner')
    monkeypatch.setattr(auto.sandbox,'execute',fail)
    async def scenario():
        version=auto.registry.create(spec())
        job=auto.enqueue('evaluate',{'version':version['id']})
        await auto.process({'id':job['id']})
        assert auto.store.load('jobs',job['id'])['status']=='blocked'
        assert not auto.registry.active('fetch')
    asyncio.run(scenario())

def test_model_generates_version_then_queues_tests(auto,monkeypatch):
    import models
    monkeypatch.setenv('ENABLE_LLM','true')
    auto.store.save('catalog','candidate-test',{'id':'candidate-test','name':'tool','url':'https://github.com/org/tool','repository':'org/tool','description':'HTML extractor'})
    async def fetch(url,**kwargs):
        if url.endswith('/readme'):return httpx.Response(200,json={'content':base64.b64encode(b'Use run(url) to fetch text').decode()})
        return httpx.Response(200,json=[{'sha':'a'*40}])
    class Model:
        def with_structured_output(self,type):return self
        async def ainvoke(self,messages):return AdapterSpec.model_validate(spec('generated-tool'))
    monkeypatch.setattr(providers,'request',fetch)
    monkeypatch.setattr(models,'create_chat_model',lambda:Model())
    async def scenario():
        job=auto.enqueue('generate',{'candidate':'candidate-test'})
        await auto.process({'id':job['id']})
        completed=auto.store.load('jobs',job['id'])
        assert completed['status']=='completed',completed
        assert completed['result']['repository_commit']=='a'*40
        assert auto.store.all('jobs')[-1]['kind']=='evaluate'
        assert not auto.registry.active('fetch')
    asyncio.run(scenario())

def test_adapter_can_declare_managed_service():
    item=AdapterSpec.model_validate({**spec('service-tool'),'service':{'name':'service-tool','image':'example/tool:1.2.3','port':8080,'health_path':'/health','memory_mb':256,'cpus':.25,'pids':64}})
    assert item.service.name=='service-tool' and item.service.memory_mb==256
    with pytest.raises(ValueError):AdapterSpec.model_validate({**spec('unsafe-tool'),'service':{'name':'unsafe-tool','image':'example/tool:1','port':8080,'environment':{'ACCESS_TOKEN':'secret'}}})

def test_provision_turns_tool_config_into_editable_project(auto,monkeypatch):
    calls=[]
    async def ensure_project(spec):calls.append(('project',spec));return {'name':spec['name'],'file_count':1,'bytes':12,'snapshots':[]}
    async def ensure_service(spec):calls.append(('service',spec));return {'name':spec['name'],'status':'running','healthy':True}
    monkeypatch.setattr(auto.sandbox,'ensure_project',ensure_project);monkeypatch.setattr(auto.sandbox,'ensure_service',ensure_service)
    raw={'name':'sample-tool','image':'example/tool:1','port':8080,'config_dir':'/etc/sample','config_files':{'settings.yml':'enabled: true'}}
    result=asyncio.run(auto.provision({'service':raw}))
    project=auto.store.load('managed_projects','sample-tool-files')
    assert project and project['spec']['service']=='sample-tool'
    deployed=calls[-1][1]
    assert deployed['project']=='sample-tool-files' and deployed['project_dir']=='/etc/sample'
    assert deployed['config_files']=={} and result['spec']['project']=='sample-tool-files'

def test_recovery_provisions_managed_search_before_llm(auto,monkeypatch):
    run_id='managed-recovery';auto.store.put('runs',run_id,{'id':run_id,'query':'python docs','events':[{'stage':'duckduckgo','status':'error','detail':'blocked'}]})
    calls=[]
    async def provision(payload,id=None):
        calls.append(('provision',payload));auto.store.save('managed_services','searxng',{'name':'searxng','status':'running','healthy':True});return {'status':'running'}
    async def attempt(state):
        calls.append(('attempt',state['plan'][0]));return {'result':{'sources':[{'url':'https://docs.python.org/','title':'Python','snippet':'Documentation'}]}}
    monkeypatch.setattr(auto,'provision',provision)
    async def scenario():
        result,advice=await auto.recover({'id':run_id,'query':'python docs','mode':'search','plan':['duckduckgo'],'allow_archive':False},attempt,lambda *args,**kwargs:None)
        assert result['sources'] and 'автоматически' in advice
        assert calls==[('provision',{'profile':'searxng'}),('attempt','managed:searxng')]
    asyncio.run(scenario())

def test_recovery_restarts_managed_search_after_failure(auto,monkeypatch):
    run_id='managed-restart';auto.store.put('runs',run_id,{'id':run_id,'query':'energy data','events':[{'stage':'managed:searxng','status':'error','detail':'Empty sources'}]})
    calls=[]
    async def service_action(name,action):calls.append((action,name));return {'status':'running'}
    async def provision(payload,id=None):calls.append(('provision',payload['profile']));return {'status':'running'}
    async def attempt(state):calls.append(('attempt',state['plan'][0]));return {'result':{'sources':[{'url':'https://example.org/report','title':'Report','snippet':'Evidence'}]}}
    monkeypatch.setattr(auto.sandbox,'service_action',service_action);monkeypatch.setattr(auto,'provision',provision)
    async def scenario():
        result,_=await auto.recover({'id':run_id,'query':'energy data','mode':'search','plan':['managed:searxng'],'allow_archive':False},attempt,lambda *args,**kwargs:None)
        assert result['sources'] and calls==[('restart','searxng'),('provision','searxng'),('attempt','managed:searxng')]
    asyncio.run(scenario())

def test_generation_timeout_is_retried(auto,monkeypatch):
    async def timeout(payload,id):raise TimeoutError('slow model')
    monkeypatch.setattr(auto,'generate',timeout)
    async def scenario():
        first=auto.enqueue('generate',{'candidate':'slow-candidate'})
        await auto.process({'id':first['id']})
        assert auto.store.load('jobs',first['id'])['status']=='failed'
        retries=[j for j in auto.store.all('jobs') if j['id']!=first['id']]
        assert len(retries)==1 and retries[0]['status']=='queued' and retries[0]['payload']['attempt']==1
    asyncio.run(scenario())

def test_workspace_repair_timeout_is_retried(auto,monkeypatch):
    async def timeout(payload,id):raise TimeoutError('slow model')
    monkeypatch.setattr(auto,'workspace_repair',timeout)
    async def scenario():
        first=auto.enqueue('workspace_repair',{'project':'tool-code','issue':'fix it'})
        await auto.process({'id':first['id']})
        retries=[j for j in auto.store.all('jobs') if j['id']!=first['id']]
        assert auto.store.load('jobs',first['id'])['status']=='failed'
        assert retries[-1]['kind']=='workspace_repair' and retries[-1]['payload']['attempt']==1
    asyncio.run(scenario())

def test_crawl_collects_and_exports(auto,monkeypatch):
    async def public(url):return url
    monkeypatch.setattr(providers,'public_url',public)
    class Research:
        def submit(self,url,**kwargs):
            id=str(len(auto.store.list('runs')))
            run={'id':id,'query':url,'status':'completed','result':{'content':'content','extracted':{'title':['Example']},'sources':[],'links':['https://example.com/second']}}
            auto.store.put('runs',id,run);return run
    auto.research=Research()
    auto.store.save('crawls','my-crawl',{'id':'my-crawl','urls':['https://example.com/'],'max_pages':2,'follow_links':True})
    async def scenario():
        job=auto.enqueue('crawl',{'plan':'my-crawl'});await auto.process({'id':job['id']})
        result=auto.store.load('datasets',job['id'])
        assert len(result['results'])==2
        assert result['results'][0]['extracted']['title']==['Example']
    asyncio.run(scenario())

def test_pipeline_engine_falls_through_and_extracts(monkeypatch):
    html='<html><body><main><h1>Title</h1><p>'+('verified evidence '*20)+'</p></main></body></html>'
    async def fetch(url,**kwargs):return httpx.Response(200,text=html,headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    monkeypatch.setattr(providers,'request',fetch)
    spec=ParsingPipelineSpec(name='example-pipeline',domain='example.com',stages=[
        {'id':'structured','kind':'json_ld','url':'{url}','min_chars':20},
        {'id':'semantic','kind':'html','url':'{url}','selectors':['main'],'fields':[{'name':'title','selector':'h1','many':False}],'min_chars':100},
    ])
    result=asyncio.run(PipelineEngine().execute(spec,'https://example.com/page'))
    assert result['pipeline_stage']=='semantic'
    assert result['extracted']['title']=='Title'
    assert result['pipeline_diagnostics'][0]['reason']=='empty_or_low_quality'
    assert path_value({'items':[{'name':'a'},{'name':'b'}]},'items.*.name')==['a','b']

def test_pipeline_registry_gate_canary_and_rollback(auto):
    registry=PipelineRegistry(auto.store);first=registry.create(default_pipeline('https://example.com'))
    with pytest.raises(ValueError):registry.promote(first['id'])
    auto.store.save('pipeline_evaluations',first['id'],{'eligible':True,'digest':first['digest']});registry.promote(first['id'])
    for _ in range(3):registry.observe(first['id'],True)
    assert registry.active('example.com')['status']=='active'
    revision=default_pipeline('https://example.com',parent=first['id'],name=first['spec']['name']).model_dump()
    revision['description']='changed';second=registry.create(revision)
    auto.store.save('pipeline_evaluations',second['id'],{'eligible':True,'digest':second['digest']});registry.promote(second['id'])
    registry.observe(second['id'],False);registry.observe(second['id'],False)
    assert registry.active('example.com')['id']==first['id']

def test_api_discovery_requires_real_unauthenticated_structured_response(auto,monkeypatch):
    async def inspect(url):return {'url':url,'sample':'A free tier is documented','api_links':['https://example.com/api/data'],'alternates':['https://example.com/about']}
    async def fetch(url,**kwargs):
        if '/api/' in url:return httpx.Response(200,json={'items':[1]},headers={'x-ratelimit-remaining':'9'},request=httpx.Request('GET',url))
        return httpx.Response(200,text='<html>not an api</html>',headers={'content-type':'text/html'},request=httpx.Request('GET',url))
    monkeypatch.setattr(auto,'inspect_source',inspect);monkeypatch.setattr(providers,'request',fetch)
    result=asyncio.run(auto.discover_apis({'url':'https://example.com/docs'}))
    assert len(result['candidates'])==1
    candidate=result['candidates'][0]
    assert candidate['verification_status']=='verified_unauthenticated'
    assert candidate['cost_status']=='no_charge_observed_not_guaranteed'
    assert candidate['license_status']=='unverified'
    assert candidate['rate_limit']['x-ratelimit-remaining']=='9'
    assert not candidate['usable_for_pipeline']

def test_pipeline_design_promotes_only_after_live_execution(auto,monkeypatch):
    async def inspect(url):return {'url':url,'sample':'','api_links':[],'alternates':[]}
    async def execute(spec,url,limit):return {'content':'live evidence '*20,'status':200,'final_url':url,'sources':[{'url':url,'title':'Example','snippet':'evidence'}],'pipeline_stage':'semantic-html','pipeline_diagnostics':[]}
    monkeypatch.setattr(auto,'inspect_source',inspect);monkeypatch.setattr(auto.pipeline_engine,'execute',execute)
    report=asyncio.run(auto.pipeline_design({'url':'https://example.com/page'}))
    assert report['eligible']
    active=auto.pipeline_registry.active('example.com')
    assert active and active['status']=='canary'
    assert auto.available('fetch',query='https://example.com/')[0].startswith('pipeline:')

def test_pipeline_design_continues_when_source_inspection_is_blocked(auto,monkeypatch):
    async def inspect(url):raise httpx.HTTPStatusError('blocked',request=httpx.Request('GET',url),response=httpx.Response(403))
    async def execute(spec,url,limit):return {'content':'live evidence '*20,'status':200,'final_url':url,'sources':[{'url':url,'title':'Example','snippet':'evidence'}],'pipeline_stage':'browser','pipeline_diagnostics':[{'stage':'semantic-html','status':'failed'}]}
    monkeypatch.setattr(auto,'inspect_source',inspect);monkeypatch.setattr(auto.pipeline_engine,'execute',execute)
    report=asyncio.run(auto.pipeline_design({'url':'https://blocked.example/page'}))
    assert report['eligible'] and report['stage']=='browser'
    assert auto.pipeline_registry.active('blocked.example')

def test_runtime_pipeline_failure_queues_repair(auto,monkeypatch):
    version=auto.pipeline_registry.create(default_pipeline('https://example.com'))
    auto.store.save('pipeline_evaluations',version['id'],{'eligible':True,'digest':version['digest']});auto.pipeline_registry.promote(version['id'])
    async def fail(*args):raise ValueError('Selector drift')
    monkeypatch.setattr(auto.pipeline_engine,'execute',fail)
    with pytest.raises(ValueError):asyncio.run(auto.execute('pipeline:'+version['id'],'https://example.com/page',5))
    repairs=[job for job in auto.store.all('jobs') if job['kind']=='pipeline_repair']
    assert len(repairs)==1 and repairs[0]['payload']['version']==version['id']

def test_proactive_pipeline_monitor_records_health_and_repairs(auto,monkeypatch):
    version=auto.pipeline_registry.create(default_pipeline('https://example.com/page'))
    auto.store.save('pipeline_evaluations',version['id'],{'eligible':True,'digest':version['digest']});auto.pipeline_registry.promote(version['id'])
    async def success(*args):return {'content':'evidence '*30,'status':200,'final_url':'https://example.com/page','sources':[{'url':'https://example.com/page','title':'x','snippet':'x'}],'pipeline_stage':'html','pipeline_diagnostics':[]}
    monkeypatch.setattr(auto.pipeline_engine,'execute',success)
    healthy=asyncio.run(auto.pipeline_monitor({}))['pipelines'][0]
    assert healthy['status']=='healthy' and auto.store.load('pipeline_health',version['id'])['stage']=='html'
    async def fail(*args):
        error=ValueError('drift');error.diagnostics=[{'stage':'html','reason':'selector_drift'}];raise error
    monkeypatch.setattr(auto.pipeline_engine,'execute',fail)
    degraded=asyncio.run(auto.pipeline_monitor({}))['pipelines'][0]
    assert degraded['status']=='degraded'
    assert any(job['kind']=='pipeline_repair' for job in auto.store.all('jobs'))

def test_api_monitor_marks_repeated_failures_degraded(auto,monkeypatch):
    auto.store.save('api_candidates','api-test',{'id':'api-test','endpoint':'https://example.com/api','verification_status':'verified_unauthenticated','consecutive_failures':0})
    async def fail(*args,**kwargs):raise ValueError('HTTP 503')
    monkeypatch.setattr(providers,'request',fail)
    asyncio.run(auto.api_monitor({}));result=asyncio.run(auto.api_monitor({}))['apis'][0]
    assert result=={'id':'api-test','healthy':False,'status':'degraded'}

def test_unknown_free_api_is_enabled_only_after_generated_contract_passes(auto,monkeypatch):
    import models
    monkeypatch.setenv('ENABLE_LLM','true')
    candidate={'id':'api-public-test','endpoint':'https://example.com/api','documentation_url':'https://example.com/docs','source_url':'https://example.com/docs','verification_status':'verified_unauthenticated'}
    auto.store.save('api_candidates',candidate['id'],candidate)
    async def fetch(url,**kwargs):
        if url.endswith('/docs'):return httpx.Response(200,text='GET /api?q=term returns results',request=httpx.Request('GET',url))
        return httpx.Response(200,json={'results':[{'url':'https://example.com/item','title':'Item','summary':'Evidence'}]},request=httpx.Request('GET',url))
    class Model:
        def with_structured_output(self,type):return self
        async def ainvoke(self,messages):
            from contracts import ConnectorSpec
            return ConnectorSpec(id='temporary',mode='search',endpoint='https://example.com/api',method='GET',query_param='q',sources_field='results',url_field='url',title_field='title',snippet_field='summary',enabled=False)
    monkeypatch.setattr(providers,'request',fetch);monkeypatch.setattr(models,'create_chat_model',lambda:Model())
    result=asyncio.run(auto.integrate_api({'candidate':candidate['id'],'mode':'search','test_query':'evidence'}))
    connector=auto.store.load('connectors',candidate['id'])
    assert result['sources']==1 and connector['enabled']
    assert auto.store.load('api_candidates',candidate['id'])['integration_status']=='active'
    assert 'api:'+candidate['id'] in auto.available('search')

def test_connector_inference_respects_provider_limit_parameter(auto):
    candidate={'id':'api-openalex','endpoint':'https://api.openalex.org/works?search=python&per-page=5'}
    spec=auto._infer_search_connector(candidate,{'results':[{'id':'https://openalex.org/W1','display_name':'Async Python'}]})
    assert spec.result_path=='results' and spec.query_param=='search' and spec.limit_param=='per-page'

def test_failed_api_mapping_is_versioned_and_not_enabled(auto,monkeypatch):
    import models
    monkeypatch.setenv('ENABLE_LLM','true')
    candidate={'id':'api-broken-test','endpoint':'https://example.com/api','documentation_url':'','source_url':'https://example.com','verification_status':'verified_unauthenticated'}
    auto.store.save('api_candidates',candidate['id'],candidate)
    async def fetch(url,**kwargs):return httpx.Response(200,json={'unexpected':'shape'},request=httpx.Request('GET',url))
    class Model:
        def with_structured_output(self,type):return self
        async def ainvoke(self,messages):
            from contracts import ConnectorSpec
            return ConnectorSpec(id='temporary',mode='search',endpoint=candidate['endpoint'],method='GET',sources_field='missing')
    monkeypatch.setattr(providers,'request',fetch);monkeypatch.setattr(models,'create_chat_model',lambda:Model())
    with pytest.raises(ValueError,match='live test'):asyncio.run(auto.integrate_api({'candidate':candidate['id'],'mode':'search'}))
    assert auto.store.load('connectors',candidate['id']) is None
    revision=auto.store.all('connector_revisions')[0]
    assert revision['candidate']==candidate['id'] and 'KeyError' in revision['error']
