"""Validated, versionable contracts shared by agent, evaluation and runtime."""
import re
from urllib.parse import urlsplit
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

SAFE_PROJECT_PATH = r'^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.@+ -]+(?:/[A-Za-z0-9_.@+ -]+)*$'

class ProjectCommand(BaseModel):
    argv: list[str] = Field(min_length=1,max_length=32)
    timeout: int = Field(default=120,ge=1,le=600)
    network: bool = False
    @field_validator('argv')
    @classmethod
    def bounded_argv(cls,values):
        if any(not value or len(value)>2000 or '\x00' in value for value in values):raise ValueError('Invalid command argument')
        return values

class ManagedProjectSpec(BaseModel):
    """Editable source tree kept in a Docker volume and executed in an isolated container."""
    name: str = Field(pattern=r'^[a-z][a-z0-9-]{1,40}$')
    runtime_image: str = Field(default='inet-sandbox-workspace:local',min_length=3,max_length=300)
    repository: str = Field(default='',max_length=2000)
    revision: str = Field(default='',pattern=r'^[A-Za-z0-9._/@+-]{0,160}$')
    files: dict[str,str] = Field(default_factory=dict,max_length=100)
    service: str = Field(default='',pattern=r'^[a-z][a-z0-9-]{1,40}$|^$')
    test_commands: list[ProjectCommand] = Field(default_factory=list,max_length=12)
    memory_mb: int = Field(default=1024,ge=128,le=4096)
    cpus: float = Field(default=1,ge=.1,le=4)
    pids: int = Field(default=256,ge=32,le=1024)
    @field_validator('runtime_image')
    @classmethod
    def pinned_image(cls,value):
        if value!='inet-sandbox-workspace:local' and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})',value):
            raise ValueError('Use an explicit runtime image tag or digest')
        return value
    @field_validator('repository')
    @classmethod
    def public_repository(cls,value):
        if value:
            parsed=urlsplit(value)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Only public credential-free HTTPS repositories are supported')
        return value
    @field_validator('files')
    @classmethod
    def safe_files(cls,values):
        if sum(len(value.encode()) for value in values.values())>2_000_000:raise ValueError('Project seed is too large')
        if any(not re.fullmatch(SAFE_PROJECT_PATH,name) for name in values):raise ValueError('Unsafe project path')
        return values

class ProjectMutation(BaseModel):
    writes: dict[str,str] = Field(default_factory=dict,max_length=100)
    deletes: list[str] = Field(default_factory=list,max_length=100)
    patch: str = Field(default='',max_length=1_000_000)
    reason: str = Field(default='',max_length=2000)
    @field_validator('writes')
    @classmethod
    def safe_writes(cls,values):
        if sum(len(value.encode()) for value in values.values())>2_000_000:raise ValueError('Mutation is too large')
        if any(not re.fullmatch(SAFE_PROJECT_PATH,name) for name in values):raise ValueError('Unsafe project path')
        return values
    @field_validator('deletes')
    @classmethod
    def safe_deletes(cls,values):
        if any(not re.fullmatch(SAFE_PROJECT_PATH,name) for name in values):raise ValueError('Unsafe project path')
        return values

class WorkspaceRepairPlan(ProjectMutation):
    explanation: str = Field(default='',max_length=4000)
    commands: list[ProjectCommand] = Field(default_factory=list,max_length=12)

class ManagedServiceSpec(BaseModel):
    """A persistent tool deployed by the sandbox control plane."""
    name: str = Field(pattern=r'^[a-z][a-z0-9-]{1,40}$')
    image: str = Field(min_length=3,max_length=300)
    port: int = Field(ge=1,le=65535)
    health_path: str = Field(default='/',pattern=r'^/[A-Za-z0-9_./?&=%+-]*$',max_length=500)
    environment: dict[str,str] = Field(default_factory=dict,max_length=32)
    command: list[str] = Field(default_factory=list,max_length=32)
    config_dir: str = Field(default='',max_length=200)
    config_files: dict[str,str] = Field(default_factory=dict,max_length=8)
    data_dirs: list[str] = Field(default_factory=list,max_length=4)
    project: str = Field(default='',pattern=r'^[a-z][a-z0-9-]{1,40}$|^$')
    project_dir: str = Field(default='/workspace',pattern=r'^/[A-Za-z0-9_./-]+$',max_length=200)
    working_dir: str = Field(default='',pattern=r'^$|^/[A-Za-z0-9_./-]*$',max_length=200)
    memory_mb: int = Field(default=512,ge=128,le=2048)
    cpus: float = Field(default=.5,ge=.1,le=2)
    pids: int = Field(default=128,ge=32,le=512)
    readiness_timeout: int = Field(default=90,ge=5,le=300)
    @field_validator('image')
    @classmethod
    def image_reference(cls,value):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})',value):
            raise ValueError('Use a registry image with an explicit tag or sha256 digest')
        return value
    @field_validator('environment')
    @classmethod
    def safe_environment(cls,values):
        for key,value in values.items():
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',key) or len(value)>4000:
                raise ValueError('Invalid service environment')
            if any(word in key for word in ('KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL')):
                raise ValueError('Secrets must not be embedded in a managed service specification')
        return values
    @field_validator('config_dir')
    @classmethod
    def safe_config_dir(cls,value):
        if value and (not value.startswith(('/etc/','/opt/')) or '..' in value):
            raise ValueError('config_dir must be an absolute /etc or /opt path')
        return value.rstrip('/')
    @field_validator('config_files')
    @classmethod
    def safe_config_files(cls,values):
        if sum(len(v) for v in values.values())>100000:return (_ for _ in ()).throw(ValueError('Service configuration is too large'))
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',name) for name in values):raise ValueError('Config file names must be flat and safe')
        return values
    @field_validator('data_dirs')
    @classmethod
    def safe_data_dirs(cls,values):
        if any(not path.startswith(('/var/lib/','/var/cache/','/opt/')) or '..' in path for path in values):raise ValueError('Persistent data paths must be under /var/lib, /var/cache or /opt')
        return list(dict.fromkeys(path.rstrip('/') for path in values))

    @model_validator(mode='after')
    def safe_project_mount(self):
        if '..' in self.project_dir or '..' in self.working_dir:raise ValueError('Unsafe project directory')
        if self.project and any(self.project_dir==path or self.project_dir.startswith(path+'/') or path.startswith(self.project_dir+'/') for path in self.data_dirs):raise ValueError('Project and data mounts overlap')
        return self

class AdapterSpec(BaseModel):
    name: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,48}$')
    mode: Literal['fetch','search'] = 'fetch'
    description: str = Field(default='',max_length=2000)
    source_url: str = ''
    code: str = Field(min_length=30,max_length=60000,description='Python function run(query: str, limit: int) -> dict; may be async')
    requirements: list[str] = Field(default_factory=list,max_length=20)
    service: ManagedServiceSpec | None = None
    parent: str | None = None
    @field_validator('requirements')
    @classmethod
    def pinned(cls,items):
        for item in items:
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*(\[[a-zA-Z0-9_,.-]+\])?==[a-zA-Z0-9_.+!-]+',item):
                raise ValueError('Зависимости должны быть зафиксированы: package==version')
        return items

class ExtractionRule(BaseModel):
    """A bounded declarative extraction rule; no generated code is executed."""
    name: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
    selector: str = Field(default='',max_length=300)
    path: str = Field(default='',pattern=r'^[a-zA-Z0-9_.*\[\]-]*$',max_length=300)
    attribute: str = Field(default='',pattern=r'^[a-zA-Z_:][-a-zA-Z0-9_:.]*$',max_length=80)
    required: bool = False
    many: bool = True

class PipelineStage(BaseModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,40}$')
    kind: Literal['json_api','feed','json_ld','html','browser']
    url: str = Field(default='{url}',max_length=2000)
    result_path: str = Field(default='',pattern=r'^[a-zA-Z0-9_.*\[\]-]*$',max_length=300)
    selectors: list[str] = Field(default_factory=list,max_length=12)
    fields: list[ExtractionRule] = Field(default_factory=list,max_length=30)
    min_chars: int = Field(default=100,ge=20,le=10000)
    timeout: int = Field(default=20,ge=2,le=60)
    @field_validator('url')
    @classmethod
    def safe_template(cls,value):
        cleaned=value.replace('{url}','').replace('{query}','')
        if '{' in cleaned or '}' in cleaned:raise ValueError('Only {url} and {query} templates are supported')
        if value not in ('{url}','{query}') and not value.startswith(('http://','https://')):raise ValueError('Stage URL must be HTTP(S) or an input template')
        return value
    @field_validator('selectors')
    @classmethod
    def bounded_selectors(cls,values):
        if any(not value.strip() or len(value)>300 for value in values):raise ValueError('Invalid selector')
        return list(dict.fromkeys(values))

class ParsingPipelineSpec(BaseModel):
    name: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,48}$')
    domain: str = Field(pattern=r'^[a-zA-Z0-9.-]{1,253}$')
    mode: Literal['fetch','search'] = 'fetch'
    description: str = Field(default='',max_length=2000)
    probe_url: str = Field(default='',max_length=2000)
    stages: list[PipelineStage] = Field(min_length=1,max_length=8)
    parent: str | None = None
    @field_validator('domain')
    @classmethod
    def normalized_domain(cls,value):
        value=value.lower().strip('.')
        if '..' in value or value.startswith('-') or value.endswith('-'):raise ValueError('Invalid domain')
        return value
    @model_validator(mode='after')
    def probe_matches_domain(self):
        if self.probe_url:
            parsed=urlsplit(self.probe_url)
            if parsed.scheme not in ('http','https') or (parsed.hostname or '').lower()!=self.domain:
                raise ValueError('probe_url must be a public HTTP(S) URL on the pipeline domain')
        return self

class FreeApiCandidate(BaseModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,48}$')
    endpoint: str = Field(max_length=2000)
    documentation_url: str = Field(default='',max_length=2000)
    source_url: str = Field(max_length=2000)
    auth: Literal['none','api_key','oauth','unknown'] = 'unknown'
    evidence: list[str] = Field(default_factory=list,max_length=12)

class DomainPolicy(BaseModel):
    domain: str = Field(min_length=1,max_length=253)
    timeout: float = Field(default=20,ge=2,le=60)
    wait_selector: str = Field(default='body',max_length=300)
    min_chars: int = Field(default=100,ge=20,le=5000)
    blocked_markers: list[str] = Field(default_factory=lambda:['verify you are human','captcha challenge','access denied','just a moment...'],max_length=30)
    preferred: list[str] = Field(default_factory=list,max_length=12)
    use_proxy: bool = False
    official_urls: list[str] = Field(default_factory=list,max_length=10)
    extractors: dict[str,str] = Field(default_factory=dict,max_length=30)

class CrawlPlan(BaseModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,48}$')
    urls: list[str] = Field(min_length=1,max_length=50)
    max_pages: int = Field(default=10,ge=1,le=50)
    follow_links: bool = False
    interval_seconds: int = Field(default=0,ge=0,le=2592000)
    enabled: bool = True
    @field_validator('interval_seconds')
    @classmethod
    def interval(cls,value):
        if value and value<300:raise ValueError('Минимальный интервал 300 секунд')
        return value

class BrowserAction(BaseModel):
    action: Literal['read','click','wait','scroll','goto','extract']
    selector: str = Field(default='body',max_length=300)
    value: str = Field(default='',max_length=2000)

class RecoveryDecision(BaseModel):
    explanation: str
    policy: DomainPolicy | None = None
    candidate_id: str | None = None
    retry_provider: str | None = None
    discover_query: str | None = None
    need_proxy: bool = False

class ConnectorSpec(BaseModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{1,48}$')
    mode: Literal['fetch','search']
    endpoint: str = Field(max_length=2000)
    method: Literal['GET','POST'] = 'POST'
    query_param: str = 'query'
    limit_param: str = Field(default='limit',pattern=r'^[a-zA-Z0-9_.-]{0,64}$')
    static_params: dict[str,str] = Field(default_factory=dict,max_length=20)
    auth_header: str = 'Authorization'
    auth_prefix: str = 'Bearer '
    result_path: str = ''
    content_field: str = 'content'
    sources_field: str = 'results'
    url_field: str = 'url'
    title_field: str = 'title'
    snippet_field: str = 'content'
    monthly_limit: int = Field(default=100,ge=0,le=10000000)
    cost: int = Field(default=1,ge=1,le=10000)
    usage_endpoint: str = ''
    remaining_path: str = 'remaining'
    documentation_url: str = ''
    enabled: bool = True
    @field_validator('static_params')
    @classmethod
    def safe_static_params(cls,values):
        for key,value in values.items():
            if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_.-]{0,63}',key) or len(value)>500:raise ValueError('Invalid static API parameter')
            if any(word in key.upper() for word in ('KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL')):raise ValueError('Secrets must be stored in the vault')
        return values

def result_contract(result, mode):
    from providers import normalize_url
    if not isinstance(result,dict): raise ValueError('Adapter must return an object')
    if mode=='fetch':
        content=result.get('content','')
        if not isinstance(content,str) or not content.strip(): raise ValueError('Empty content')
        result['content']=content[:60000]
        result['final_url']=normalize_url(result['final_url'])
        if int(result.get('status',200))>=400: raise ValueError('HTTP failure')
        result.setdefault('sources',[{'url':result['final_url'],'title':result.get('title',result['final_url']),'snippet':content[:700]}])
    if not isinstance(result.get('sources'),list) or not result['sources']: raise ValueError('Empty sources')
    sources=[]
    for item in result['sources'][:10]:
        sources.append({'url':normalize_url(item['url']),'title':str(item.get('title',item['url']))[:500],'snippet':str(item.get('snippet',''))[:5000]})
    return {**result,'sources':sources}
