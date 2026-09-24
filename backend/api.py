import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Literal
from research import Research
from store import Store
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from automation import Automation
from contracts import AdapterSpec,ConnectorSpec,DomainPolicy,CrawlPlan,ManagedProjectSpec,ParsingPipelineSpec,ProjectCommand,ProjectMutation

@asynccontextmanager
async def lifespan(app):
    app.state.store = Store()
    import os
    async with AsyncSqliteSaver.from_conn_string(os.getenv('RUNTIME_DB','runtime/state.sqlite3')+'.checkpoints') as saver:
        app.state.automation=Automation(app.state.store)
        app.state.research = Research(app.state.store,saver,app.state.automation)
        app.state.automation.research=app.state.research
        app.state.automation.start()
        for run in app.state.store.list('runs'):
            if run['status'] in ('running','queued'):
                run['status']='interrupted'; app.state.store.put('runs',run['id'],run)
        yield
        tasks = list(app.state.research.tasks.values())+list(app.state.research.reflection_tasks.values())
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        await app.state.automation.close()
    app.state.store.db.close()

app = FastAPI(title='INET · Research runtime',version='2.0.0',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://localhost:8501'],allow_methods=['GET','POST'],allow_headers=['Content-Type'])

class RunRequest(BaseModel):
    query: str = Field(min_length=1,max_length=4000)
    mode: Literal['auto','search','fetch'] = 'auto'
    limit: int = Field(default=5,ge=1,le=10)
    fresh: bool = False
    allow_archive: bool = False
    unique_tools: bool = False
    deep: bool = False
    instruction: str = Field(default='',max_length=2000)
    persistence_level: int | None = Field(default=None,ge=1,le=4)
    reflection_enabled: bool | None = None
    reflection_level: int | None = Field(default=None,ge=1,le=4)
    @field_validator('query')
    @classmethod
    def nonempty(cls,v):
        if not v.strip(): raise ValueError('Запрос пуст')
        return v.strip()

@app.get('/health')
async def health():
    app.state.store.db.execute('SELECT 1')
    return {'status':'ok'}

@app.get('/api/resources')
async def resources():
    return {'schema_version':2,'resources':app.state.store.all('catalog')}

class ResearchSettings(BaseModel):
    persistence_level: int = Field(default=2,ge=1,le=4)
    reflection_enabled: bool = True
    reflection_level: int = Field(default=2,ge=1,le=4)

@app.get('/api/research-settings')
async def research_settings():
    return app.state.store.load('settings','research',ResearchSettings().model_dump())

@app.post('/api/research-settings')
async def save_research_settings(payload:ResearchSettings):
    value=payload.model_dump();app.state.store.save('settings','research',value);return value

@app.get('/api/runs')
async def runs():
    items=app.state.store.list('runs')
    for item in items:
        app.state.research.ensure_budgets(item)
        app.state.store.put('runs',item['id'],item)
    return items

@app.post('/api/runs',status_code=202)
async def submit(payload:RunRequest):
    values=payload.model_dump();settings=app.state.store.load('settings','research',ResearchSettings().model_dump())
    for key in ('persistence_level','reflection_enabled','reflection_level'):
        if values[key] is None:values[key]=settings[key]
    try: return app.state.research.submit(**values)
    except ValueError as exc: raise HTTPException(422,str(exc))

@app.get('/api/runs/{id}')
async def run(id:str):
    item=app.state.store.get('runs',id)
    if not item: raise HTTPException(404,'Запрос не найден')
    app.state.research.ensure_budgets(item)
    app.state.store.put('runs',id,item)
    return item

@app.post('/api/runs/{id}/cancel')
async def cancel(id:str):
    item=await run(id)
    task=app.state.research.tasks.get(id)
    if task:
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
    # A queued task can be cancelled before its coroutine reaches Research.run(),
    # so persist the terminal state here as well.
    item=app.state.store.get('runs',id)
    if item and item.get('status') in ('queued','running'):
        item['status']='cancelled';app.state.store.put('runs',id,item)
    return await run(id)

@app.get('/api/system')
async def system():
    import providers
    auto=app.state.automation
    return {'providers':{'search':auto.available('search'),'fetch':auto.available('fetch')},'managed_services':app.state.store.all('managed_services'),'active_pipelines':app.state.store.all('active_pipelines'),'api_candidates':app.state.store.all('api_candidates'),'quotas':app.state.store.quotas(),'cases':app.state.store.list('cases')}

@app.post('/api/runs/{id}/resume',status_code=202)
async def resume(id:str):
    await run(id)
    try: return await app.state.research.resume(id)
    except ValueError as exc: raise HTTPException(409,str(exc))

@app.post('/api/runs/{id}/synthesize')
async def synthesize(id:str):
    try:return await app.state.research.resynthesize(id)
    except ValueError as exc:raise HTTPException(409,str(exc))

class ReflectionRequest(BaseModel):
    level: int = Field(default=2,ge=1,le=4)

@app.post('/api/runs/{id}/reflect',status_code=202)
async def reflect(id:str,payload:ReflectionRequest):
    await run(id)
    try:return app.state.research.start_reflection(id,payload.level)
    except ValueError as exc:raise HTTPException(409,str(exc))

@app.post('/api/runs/{id}/reflection/cancel')
async def cancel_reflection(id:str):
    await run(id);task=app.state.research.reflection_tasks.get(id)
    if task:
        task.cancel();await asyncio.gather(task,return_exceptions=True)
    return await run(id)

class FollowUpRequest(BaseModel):
    question: str = Field(min_length=1,max_length=4000)
    @field_validator('question')
    @classmethod
    def question_nonempty(cls,value):
        if not value.strip():raise ValueError('Вопрос пуст')
        return value.strip()

@app.post('/api/runs/{id}/follow-up',status_code=202)
async def follow_up(id:str,payload:FollowUpRequest):
    await run(id)
    try:return app.state.research.submit_followup(id,payload.question)
    except ValueError as exc:raise HTTPException(409,str(exc))

@app.post('/api/runs/{id}/rerun',status_code=202)
async def rerun(id:str):
    await run(id)
    try:return app.state.research.rerun(id)
    except ValueError as exc:raise HTTPException(409,str(exc))

@app.get('/api/runs/{id}/export.md')
async def export_markdown(id:str):
    item=await run(id)
    from reports import markdown_report
    return Response(markdown_report(item),media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="inet-{id[:8]}.md"'})

@app.get('/api/runs/{id}/export.pdf')
async def export_pdf(id:str):
    item=await run(id)
    from reports import pdf_report
    return Response(pdf_report(item),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="inet-{id[:8]}.pdf"'})

class JobRequest(BaseModel):
    kind: Literal['discover','generate','evaluate','proxies','quotas','metadata','repair_version','crawl','provision','services','discover_apis','pipeline_design','pipeline_evaluate','pipeline_repair','pipeline_monitor','api_monitor','integrate_api','workspace_repair']
    payload: dict = Field(default_factory=dict)

@app.post('/api/jobs',status_code=202)
async def job(payload:JobRequest):
    return app.state.automation.enqueue(payload.kind,payload.payload)

@app.get('/api/control')
async def control():
    s=app.state.store
    return {'jobs':list(reversed(s.all('jobs')))[0:100],'versions':list(reversed(s.all('versions'))),'evaluations':s.all('evaluations'),'pipeline_versions':list(reversed(s.all('pipeline_versions'))),'pipeline_evaluations':s.all('pipeline_evaluations'),'pipeline_health':s.all('pipeline_health'),'api_candidates':list(reversed(s.all('api_candidates'))),'connector_revisions':list(reversed(s.all('connector_revisions')))[0:50],'proxies':s.all('proxies'),'connectors':app.state.automation.connectors(),'managed_services':s.all('managed_services'),'managed_projects':s.all('managed_projects'),'policies':s.all('policies'),'remote_quotas':s.all('remote_quotas'),'audit':s.all('audit')[-100:],'crawls':s.all('crawls'),'datasets':[{'id':d['id'],'plan':d['plan'],'created_at':d['created_at'],'count':len(d['results'])} for d in s.all('datasets')],'failures':s.all('failures')[-20:]}

@app.post('/api/pipelines',status_code=201)
async def create_pipeline(spec:ParsingPipelineSpec):
    try:return app.state.automation.pipeline_registry.create(spec.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/api/pipelines/{id}/evaluate',status_code=202)
async def evaluate_pipeline(id:str,payload:dict):
    return app.state.automation.enqueue('pipeline_evaluate',{'version':id,**payload})

@app.get('/api/sandbox/health')
async def sandbox_health():return await app.state.automation.sandbox.health()

@app.post('/api/services/{name}/{action}')
async def managed_service_action(name:str,action:Literal['restart','stop']):
    import time
    result=await app.state.automation.sandbox.service_action(name,action)
    previous=app.state.store.load('managed_services',name,{})
    app.state.store.save('managed_services',name,{**previous,**result,'checked_at':time.time()})
    return result

@app.post('/api/projects',status_code=201)
async def create_project(spec:ManagedProjectSpec):
    import time
    state=await app.state.automation.sandbox.ensure_project(spec.model_dump())
    record={**state,'spec':spec.model_dump(),'updated_at':time.time()}
    app.state.store.save('managed_projects',spec.name,record)
    return record

@app.get('/api/projects/{name}/file')
async def project_file(name:str,path:str):
    if not app.state.store.load('managed_projects',name):raise HTTPException(404,'Project not found')
    return await app.state.automation.sandbox.project_file(name,path)

@app.post('/api/projects/{name}/mutate')
async def mutate_project(name:str,mutation:ProjectMutation):
    import time
    project=app.state.store.load('managed_projects',name)
    if not project:raise HTTPException(404,'Project not found')
    result=await app.state.automation.sandbox.mutate_project(name,mutation.model_dump())
    project.update(result);project['updated_at']=time.time();app.state.store.save('managed_projects',name,project)
    app.state.store.save('project_audit',str(time.time_ns()),{'project':name,'action':'mutate','snapshot':result.get('snapshot'),'reason':mutation.reason,'paths':sorted([*mutation.writes,*mutation.deletes]),'at':time.time()})
    return result

@app.post('/api/projects/{name}/command')
async def project_command(name:str,command:ProjectCommand):
    project=app.state.store.load('managed_projects',name)
    if not project:raise HTTPException(404,'Project not found')
    return await app.state.automation.sandbox.project_command(project['spec'],command.model_dump())

@app.post('/api/projects/{name}/rollback/{snapshot}')
async def rollback_project(name:str,snapshot:str):
    import time
    project=app.state.store.load('managed_projects',name)
    if not project:raise HTTPException(404,'Project not found')
    result=await app.state.automation.sandbox.rollback_project(name,snapshot)
    project.update(result);project['updated_at']=time.time();app.state.store.save('managed_projects',name,project)
    return result

@app.post('/api/versions',status_code=201)
async def version(spec:AdapterSpec):
    try:return app.state.automation.registry.create(spec.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc))

@app.post('/api/versions/{id}/{action}')
async def version_action(id:str,action:Literal['promote','rollback']):
    try:return getattr(app.state.automation.registry,action)(id)
    except ValueError as exc:raise HTTPException(409,str(exc))

class ConnectorInput(BaseModel):
    spec: ConnectorSpec
    key: str | None = Field(default=None,max_length=10000)

@app.post('/api/connectors')
async def connector(payload:ConnectorInput):
    import providers
    try:
        await providers.public_url(payload.spec.endpoint)
        if payload.spec.usage_endpoint:await providers.public_url(payload.spec.usage_endpoint)
        return app.state.automation.save_connector(payload.spec.model_dump(),payload.key)
    except ValueError as exc:raise HTTPException(422,str(exc))

class SecretInput(BaseModel):
    provider: Literal['tavily','firecrawl','capsolver','twocaptcha']
    key: str = Field(min_length=1,max_length=10000)

@app.post('/api/keys')
async def secret(payload:SecretInput):
    app.state.automation.vault.set(payload.provider,payload.key)
    return {'provider':payload.provider,'configured':True}

@app.post('/api/policies')
async def policy(payload:DomainPolicy):
    try:return app.state.automation.save_policy(payload.model_dump())
    except ValueError as exc:raise HTTPException(422,str(exc))

class ProxySources(BaseModel):
    sources: list[str] = Field(min_length=1,max_length=8)

@app.post('/api/proxies/sources')
async def proxy_sources(payload:ProxySources):
    import providers
    for url in payload.sources:await providers.public_url(url)
    app.state.store.save('settings','proxy_sources',payload.sources)
    app.state.store.save('settings','proxies_enabled',True)
    return {'saved':True}

@app.post('/api/crawls')
async def crawl(payload:CrawlPlan):
    import providers
    for url in payload.urls:await providers.public_url(url)
    plan=payload.model_dump();plan['next_at']=0;app.state.store.save('crawls',plan['id'],plan)
    return plan

@app.get('/api/datasets/{id}')
async def dataset(id:str,format:Literal['json','csv']='json'):
    from fastapi.responses import Response
    result=app.state.store.load('datasets',id)
    if not result:raise HTTPException(404)
    if format=='json':return result
    import csv,io
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=['url','status','content','extracted']);writer.writeheader()
    for row in result['results']:
        writer.writerow({key:json.dumps(row[key],ensure_ascii=False) if key=='extracted' else ("'"+row[key] if isinstance(row[key],str) and row[key].startswith(('=','+','-','@')) else row[key]) for key in writer.fieldnames})
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="dataset-{id}.csv"'})
