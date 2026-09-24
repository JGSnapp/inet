"""Run a live, evidence-preserving network research acceptance suite."""
from __future__ import annotations

import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
API='http://127.0.0.1:8001/api'
OUT=ROOT/'artifacts'/'network-research-20260924'
OUT.mkdir(parents=True,exist_ok=True)

RESEARCH_CASES=[
    {'id':'postgres-logical-replication','query':'PostgreSQL 17 logical replication improvements compared with PostgreSQL 16 official documentation benchmarks limitations','limit':10},
    {'id':'eu-ai-act-gpai','query':'EU AI Act general-purpose AI obligations implementation timeline 2025 2026 official sources code of practice enforcement','limit':10},
    {'id':'cpython-free-threading','query':'CPython free-threaded Python 3.13 3.14 ecosystem support performance limitations official documentation 2025','limit':10},
]

PARSING_TARGETS=[
    ('python-docs','https://docs.python.org/3/library/asyncio.html'),
    ('rfc-html','https://www.rfc-editor.org/rfc/rfc9110.html'),
    ('react-docs','https://react.dev/learn'),
    ('wikipedia','https://en.wikipedia.org/wiki/Web_scraping'),
    ('github-json','https://api.github.com/repos/psf/requests'),
    ('openalex-json','https://api.openalex.org/works?search=web%20search&per-page=3'),
    ('rss-feed','https://hnrss.org/frontpage'),
    ('js-rendered','https://quotes.toscrape.com/js/'),
]

def request(method,path,payload=None,timeout=240):
    data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    req=urllib.request.Request(API+path,data=data,method=method,headers={'Content-Type':'application/json'} if data else {})
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.loads(response.read())

def wait_run(run_id,timeout=360):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        state=request('GET','/runs/'+run_id,timeout=30)
        if state['status'] not in ('running','queued'):return state
        time.sleep(2)
    raise TimeoutError('run '+run_id)

def execute_run(payload):
    started=time.time();submitted=request('POST','/runs',payload)
    try:state=wait_run(submitted['id'])
    except Exception as exc:return {'id':submitted['id'],'query':payload['query'],'status':'harness_error','error':type(exc).__name__+': '+str(exc),'elapsed_seconds':round(time.time()-started,2)}
    state['elapsed_seconds']=round(time.time()-started,2)
    return state

def wait_jobs(ids,timeout=900):
    deadline=time.monotonic()+timeout;states={}
    while time.monotonic()<deadline:
        control=request('GET','/control',timeout=60);all_jobs={item['id']:item for item in control['jobs']}
        states={job_id:all_jobs.get(job_id,{'id':job_id,'status':'missing'}) for job_id in ids}
        if all(item['status'] not in ('queued','running') for item in states.values()):return states,control
        time.sleep(3)
    return states,request('GET','/control',timeout=60)

def public_sources(run):
    return (run.get('result') or {}).get('sources') or []

def main():
    suite_started=time.time()
    health=urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=10).read().decode()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(execute_run,{'query':case['query'],'mode':'search','limit':case['limit'],'fresh':True,'allow_archive':False,'instruction':''}):case for case in RESEARCH_CASES}
        searches=[]
        for future,case in futures.items():
            result=future.result();result['case_id']=case['id'];searches.append(result)
    chosen=[];seen_urls=set();per_case={}
    for run in searches:
        case_urls=[];domains=set()
        for source in public_sources(run):
            url=source.get('url','');domain=(urlsplit(url).hostname or '').lower()
            if not url or url in seen_urls or domain in domains:continue
            seen_urls.add(url);domains.add(domain);case_urls.append(url);chosen.append({'case_id':run['case_id'],'url':url,'domain':domain,'title':source.get('title','')})
            if len(case_urls)>=5:break
        per_case[run['case_id']]=case_urls
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(execute_run,{'query':item['url'],'mode':'fetch','limit':5,'fresh':True,'allow_archive':False,'instruction':'Extract the primary factual content and preserve source metadata.'}):item for item in chosen}
        fetches=[]
        for future,item in futures.items():
            result=future.result();result['parent_case']=item['case_id'];fetches.append(result)
    jobs=[]
    for target_id,url in PARSING_TARGETS:
        job=request('POST','/jobs',{'kind':'pipeline_design','payload':{'url':url}});jobs.append({'target_id':target_id,'url':url,'job_id':job['id']})
    job_states,control=wait_jobs([item['job_id'] for item in jobs])
    parsing=[]
    for item in jobs:
        state=job_states[item['job_id']]
        result=state.get('result') or {}
        parsing.append({**item,'status':state.get('status'),'error':state.get('error'),'events':state.get('events',[]),'eligible':result.get('eligible'),'stage':result.get('stage'),'latency_ms':result.get('latency_ms'),'sample_chars':result.get('sample_chars'),'diagnostics':result.get('diagnostics',[])})
    search_domains=sorted({(urlsplit(source.get('url','')).hostname or '').lower() for run in searches for source in public_sources(run) if source.get('url')})
    fetch_domains=sorted({(urlsplit(run.get('query','')).hostname or '').lower() for run in fetches if run.get('query')})
    providers=Counter((run.get('result') or {}).get('provider','none') for run in [*searches,*fetches])
    report={
        'suite':'INET live multi-site research and parsing acceptance',
        'started_at':datetime.fromtimestamp(suite_started,timezone.utc).isoformat(),
        'finished_at':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':round(time.time()-suite_started,2),
        'backend_health':json.loads(health),
        'summary':{
            'research_cases':len(searches),'research_completed':sum(x.get('status')=='completed' for x in searches),
            'search_sources':sum(len(public_sources(x)) for x in searches),'unique_search_domains':len(search_domains),
            'deep_fetches':len(fetches),'deep_fetch_completed':sum(x.get('status')=='completed' for x in fetches),'unique_fetch_domains':len(fetch_domains),
            'parsing_targets':len(parsing),'parsing_passed':sum(x.get('status')=='completed' and x.get('eligible') for x in parsing),
            'providers':dict(providers),
        },
        'search_domains':search_domains,'fetch_domains':fetch_domains,'research_runs':searches,'selected_deep_reads':chosen,'fetch_runs':fetches,'parsing_matrix':parsing,
        'active_pipelines':control.get('pipeline_versions',[]),'pipeline_evaluations':control.get('pipeline_evaluations',[]),
    }
    (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# INET live network research acceptance report','',f"Started: {report['started_at']}",f"Finished: {report['finished_at']}",f"Duration: {report['elapsed_seconds']} s",'', '## Summary','']
    for key,value in report['summary'].items():lines.append(f'- {key}: {value}')
    lines+=['','## Research cases','']
    for run in searches:
        lines += [f"### {run['case_id']}",'',f"- Status: {run.get('status')}",f"- Provider: {(run.get('result') or {}).get('provider')}",f"- Sources: {len(public_sources(run))}",f"- Elapsed: {run.get('elapsed_seconds')} s",'']
        for source in public_sources(run):lines.append(f"- [{source.get('title','source')}]({source.get('url','')})")
        lines.append('')
    lines+=['## Parsing matrix','','| Target | Status | Stage | Characters | Latency, ms |','| --- | --- | --- | ---: | ---: |']
    for item in parsing:lines.append(f"| {item['target_id']} | {item['status']} | {item.get('stage') or '-'} | {item.get('sample_chars') or 0} | {item.get('latency_ms') or 0} |")
    failures=[x for x in [*searches,*fetches] if x.get('status')!='completed']
    lines+=['','## Failures and fallbacks','',f'- Non-completed research/fetch runs: {len(failures)}',f"- Rejected parsing targets: {sum(x.get('status')!='completed' for x in parsing)}",'', 'Full events, answers, diagnostics and extracted content are preserved in `results.json`.']
    (OUT/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'summary':report['summary']},ensure_ascii=False,indent=2))
    return 0 if report['summary']['research_completed']>=2 and report['summary']['parsing_passed']>=4 else 2

if __name__=='__main__':sys.exit(main())
