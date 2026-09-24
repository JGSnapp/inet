"""Versioned, declarative parsing pipelines with diagnosis and rollback."""
import hashlib
import json
import re
import time
from copy import deepcopy
from urllib.parse import quote, urljoin, urlsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree

from contracts import ParsingPipelineSpec
import providers

def path_value(value,path):
    """Small JSON-path subset: dotted keys, numeric indexes and '*' fan-out."""
    values=[value]
    for part in filter(None,path.replace('[','.').replace(']','').split('.')):
        next_values=[]
        for current in values:
            if part=='*' and isinstance(current,list):next_values.extend(current)
            elif isinstance(current,dict) and part in current:next_values.append(current[part])
            elif isinstance(current,list) and part.isdigit() and int(part)<len(current):next_values.append(current[int(part)])
        values=next_values
        if not values:break
    if '*' in path:return values
    return values[0] if len(values)==1 else values

def text_content(value):
    if isinstance(value,str):return value
    return json.dumps(value,ensure_ascii=False,indent=2)

def classify_error(exc):
    text=str(exc).lower()
    if '401' in text or '403' in text:return 'authentication_or_access'
    if '429' in text:return 'rate_limited'
    if 'captcha' in text or 'verify you are human' in text:return 'anti_bot'
    if 'selector' in text:return 'selector_drift'
    if 'empty' in text or 'content' in text:return 'empty_or_low_quality'
    if 'json' in text or 'xml' in text:return 'format_changed'
    if 'timeout' in text:return 'timeout'
    return 'transport_or_parser'

class PipelineRegistry:
    def __init__(self,store):self.store=store
    def create(self,spec):
        spec=ParsingPipelineSpec.model_validate(spec).model_dump()
        digest=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
        id=spec['name']+'@'+digest[:12]
        existing=self.store.load('pipeline_versions',id)
        if existing:return existing
        parent=self.store.load('pipeline_versions',spec.get('parent')) if spec.get('parent') else None
        if spec.get('parent') and (not parent or parent['spec']['name']!=spec['name']):raise ValueError('Invalid pipeline parent')
        record={'id':id,'digest':digest,'spec':spec,'status':'candidate','created_at':time.time(),'successes':0,'failures':0,'previous':None}
        self.store.save('pipeline_versions',id,record);return record
    def promote(self,id):
        record=self.store.load('pipeline_versions',id)
        report=self.store.load('pipeline_evaluations',id)
        if not record or not report or not report.get('eligible') or report.get('digest')!=record['digest']:raise ValueError('Pipeline has not passed evaluation')
        previous=self.store.load('active_pipelines',record['spec']['domain'])
        record.update(status='canary',previous=previous['id'] if previous else None)
        self.store.save('pipeline_versions',id,record);self.store.save('active_pipelines',record['spec']['domain'],{'id':id})
        return record
    def active(self,domain):
        pointer=self.store.load('active_pipelines',domain.lower())
        return self.store.load('pipeline_versions',pointer['id']) if pointer else None
    def observe(self,id,success,diagnostic=None):
        record=self.store.load('pipeline_versions',id)
        if not record:return
        record['successes' if success else 'failures']+=1
        record['recent']=(record.get('recent',[])+[bool(success)])[-10:]
        if diagnostic:record['last_diagnostic']=diagnostic
        if record['status']=='canary' and record['successes']>=3:record['status']='active'
        self.store.save('pipeline_versions',id,record)
        if (record['status']=='canary' and record['failures']>=2) or (len(record['recent'])>=5 and sum(record['recent'][-5:])<=2):self.rollback(id)
    def rollback(self,id):
        record=self.store.load('pipeline_versions',id)
        if not record:return
        pointer=self.store.load('active_pipelines',record['spec']['domain'])
        if pointer and pointer['id']==id:
            if record.get('previous'):self.store.save('active_pipelines',record['spec']['domain'],{'id':record['previous']})
            else:self.store.delete('active_pipelines',record['spec']['domain'])
        record['status']='rolled_back';self.store.save('pipeline_versions',id,record)

class PipelineEngine:
    def __init__(self,browser=None):self.browser=browser
    async def execute(self,spec,query,limit=5):
        spec=ParsingPipelineSpec.model_validate(spec)
        if (urlsplit(query).hostname or '').lower()!=spec.domain:raise ValueError('Pipeline domain mismatch')
        diagnostics=[]
        for stage in spec.stages:
            started=time.monotonic()
            try:
                result=await self._stage(stage,query,limit)
                providers.validate_content(result['content'])
                diagnostics.append({'stage':stage.id,'kind':stage.kind,'status':'success','latency_ms':round((time.monotonic()-started)*1000)})
                result['pipeline_stage']=stage.id;result['pipeline_diagnostics']=diagnostics
                return result
            except Exception as exc:
                diagnostics.append({'stage':stage.id,'kind':stage.kind,'status':'error','reason':classify_error(exc),'detail':type(exc).__name__})
        error=ValueError('All pipeline stages failed: '+','.join(x['stage']+':'+x['reason'] for x in diagnostics))
        error.diagnostics=diagnostics
        raise error
    async def _stage(self,stage,query,limit):
        if stage.kind=='browser':
            if not self.browser:raise ValueError('Browser unavailable')
            return await self.browser(query,limit)
        target=stage.url.replace('{url}',query).replace('{query}',quote(query,safe=''))
        response=await providers.request(target)
        if stage.kind=='json_api':
            data=response.json();root=path_value(data,stage.result_path) if stage.result_path else data
            content=text_content(root)
            extracted={rule.name:path_value(root,rule.path) for rule in stage.fields}
        elif stage.kind=='feed':
            root=ElementTree.fromstring(response.text);rows=[]
            for node in root.iter():
                if node.tag.split('}')[-1] not in ('item','entry','url','sitemap'):continue
                rows.append({child.tag.split('}')[-1]:(child.text or child.attrib.get('href','')).strip() for child in node})
            if not rows:raise ValueError('Empty feed')
            content=text_content(rows[:100]);extracted={'entries':rows[:100]}
        else:
            soup=BeautifulSoup(response.text,'html.parser')
            if stage.kind=='json_ld':
                rows=[]
                for node in soup.select('script[type="application/ld+json"]'):
                    try:rows.append(json.loads(node.string or node.get_text()))
                    except ValueError:continue
                if not rows:raise ValueError('Empty JSON-LD')
                content=text_content(rows);extracted={'json_ld':rows}
            else:
                selectors=stage.selectors or ['main','article','[role="main"]','body'];nodes=[]
                for selector in selectors:
                    nodes=soup.select(selector)
                    if nodes:break
                if not nodes:raise ValueError('Selector drift: no nodes matched')
                content=' '.join(node.get_text(' ',strip=True) for node in nodes[:20])
                extracted={}
                for rule in stage.fields:
                    found=soup.select(rule.selector);values=[n.get(rule.attribute,'') if rule.attribute else n.get_text(' ',strip=True) for n in found[:100]]
                    if rule.required and not values:raise ValueError('Selector drift: '+rule.name)
                    extracted[rule.name]=values if rule.many else (values[0] if values else '')
        if len(content.strip())<stage.min_chars:raise ValueError('Empty or low quality content')
        final=str(response.url);title=final
        return {'content':content[:60000],'extracted':extracted,'status':response.status_code,'final_url':final,'sources':[{'url':final,'title':title,'snippet':content[:700]}]}

def default_pipeline(url,alternates=None,parent=None,name=None):
    domain=(urlsplit(url).hostname or '').lower();safe=re.sub(r'[^a-z0-9]+','-',domain).strip('-')[:36] or 'source'
    stages=[]
    for index,alternate in enumerate(alternates or []):
        hint=alternate.lower();kind='json_api' if any(word in hint for word in ('json','/api','graphql')) else 'feed'
        stages.append({'id':f'official-{index+1}','kind':kind,'url':alternate,'min_chars':50})
    stages.extend([
        {'id':'json-ld','kind':'json_ld','url':'{url}','min_chars':50},
        {'id':'semantic-html','kind':'html','url':'{url}','selectors':['main','article','[role="main"]','body'],'min_chars':100},
        {'id':'browser','kind':'browser','url':'{url}','min_chars':100},
    ])
    return ParsingPipelineSpec(name=name or ('pipeline-'+safe)[:48],domain=domain,description='Automatically inspected structured/HTML/browser fallback pipeline',probe_url=url,stages=stages[:8],parent=parent)
