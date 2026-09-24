"""Only this service can access Docker. No caller-controlled mounts, image or network."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.parse
import urllib.request
from urllib.parse import urlsplit
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator
import docker

SAFE_PROJECT_PATH=r'^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.@+ -]+(?:/[A-Za-z0-9_.@+ -]+)*$'

class ProjectCommand(BaseModel):
    argv:list[str]=Field(min_length=1,max_length=32)
    timeout:int=Field(default=120,ge=1,le=600)
    network:bool=False
    @field_validator('argv')
    @classmethod
    def argv_safe(cls,values):
        if any(not value or len(value)>2000 or '\x00' in value for value in values):raise ValueError('Invalid command argument')
        return values

class ManagedProject(BaseModel):
    name:str=Field(pattern=r'^[a-z][a-z0-9-]{1,40}$')
    runtime_image:str=Field(default='inet-sandbox-workspace:local',min_length=3,max_length=300)
    repository:str=Field(default='',max_length=2000)
    revision:str=Field(default='',pattern=r'^[A-Za-z0-9._/@+-]{0,160}$')
    files:dict[str,str]=Field(default_factory=dict,max_length=100)
    service:str=Field(default='',pattern=r'^[a-z][a-z0-9-]{1,40}$|^$')
    test_commands:list[ProjectCommand]=Field(default_factory=list,max_length=12)
    memory_mb:int=Field(default=1024,ge=128,le=4096)
    cpus:float=Field(default=1,ge=.1,le=4)
    pids:int=Field(default=256,ge=32,le=1024)
    @field_validator('runtime_image')
    @classmethod
    def image_ref(cls,value):
        if value!='inet-sandbox-workspace:local' and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})',value):raise ValueError('Explicit image tag or digest required')
        return value
    @field_validator('repository')
    @classmethod
    def repository_url(cls,value):
        if value:
            parsed=urlsplit(value)
            if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Only public credential-free HTTPS repositories are supported')
        return value
    @field_validator('files')
    @classmethod
    def seed_files(cls,values):
        if sum(len(value.encode()) for value in values.values())>2_000_000:raise ValueError('Project seed is too large')
        if any(not re.fullmatch(SAFE_PROJECT_PATH,name) for name in values):raise ValueError('Unsafe project path')
        return values

class ProjectMutation(BaseModel):
    writes:dict[str,str]=Field(default_factory=dict,max_length=100)
    deletes:list[str]=Field(default_factory=list,max_length=100)
    patch:str=Field(default='',max_length=1_000_000)
    reason:str=Field(default='',max_length=2000)
    @field_validator('writes')
    @classmethod
    def writes_safe(cls,values):
        if sum(len(value.encode()) for value in values.values())>2_000_000:raise ValueError('Mutation is too large')
        if any(not re.fullmatch(SAFE_PROJECT_PATH,name) for name in values):raise ValueError('Unsafe project path')
        return values
    @field_validator('deletes')
    @classmethod
    def deletes_safe(cls,values):
        if any(not re.fullmatch(SAFE_PROJECT_PATH,name) for name in values):raise ValueError('Unsafe project path')
        return values

class ProjectCommandRequest(BaseModel):
    spec:ManagedProject
    command:ProjectCommand

class ManagedService(BaseModel):
    name:str=Field(pattern=r'^[a-z][a-z0-9-]{1,40}$')
    image:str=Field(min_length=3,max_length=300)
    port:int=Field(ge=1,le=65535)
    health_path:str=Field(default='/',pattern=r'^/[A-Za-z0-9_./?&=%+-]*$',max_length=500)
    environment:dict[str,str]=Field(default_factory=dict,max_length=32)
    command:list[str]=Field(default_factory=list,max_length=32)
    config_dir:str=Field(default='',max_length=200)
    config_files:dict[str,str]=Field(default_factory=dict,max_length=8)
    data_dirs:list[str]=Field(default_factory=list,max_length=4)
    project:str=Field(default='',pattern=r'^[a-z][a-z0-9-]{1,40}$|^$')
    project_dir:str=Field(default='/workspace',pattern=r'^/[A-Za-z0-9_./-]+$',max_length=200)
    working_dir:str=Field(default='',pattern=r'^$|^/[A-Za-z0-9_./-]*$',max_length=200)
    memory_mb:int=Field(default=512,ge=128,le=2048)
    cpus:float=Field(default=.5,ge=.1,le=2)
    pids:int=Field(default=128,ge=32,le=512)
    readiness_timeout:int=Field(default=90,ge=5,le=300)
    @field_validator('image')
    @classmethod
    def image_ref(cls,value):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/-]*(?::[a-zA-Z0-9._-]+|@sha256:[a-fA-F0-9]{64})',value):raise ValueError('Explicit image tag or digest required')
        return value
    @field_validator('environment')
    @classmethod
    def safe_env(cls,values):
        for key,value in values.items():
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',key) or len(value)>4000:raise ValueError('Invalid environment')
            if any(word in key for word in ('KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL')):raise ValueError('Embedded secrets are forbidden')
        return values
    @field_validator('config_dir')
    @classmethod
    def safe_config_dir(cls,value):
        if value and (not value.startswith(('/etc/','/opt/')) or '..' in value):raise ValueError('Unsafe config directory')
        return value.rstrip('/')
    @field_validator('config_files')
    @classmethod
    def safe_files(cls,values):
        if sum(len(v) for v in values.values())>100000:raise ValueError('Configuration too large')
        if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}',name) for name in values):raise ValueError('Unsafe config filename')
        return values
    @field_validator('data_dirs')
    @classmethod
    def safe_data(cls,values):
        if any(not path.startswith(('/var/lib/','/var/cache/','/opt/')) or '..' in path for path in values):raise ValueError('Unsafe data directory')
        return list(dict.fromkeys(path.rstrip('/') for path in values))
    @field_validator('project_dir','working_dir')
    @classmethod
    def safe_project_dirs(cls,value):
        if '..' in value:raise ValueError('Unsafe project directory')
        return value.rstrip('/') or ('/' if value else '')

class ServiceRequest(BaseModel):
    path:str=Field(default='/',pattern=r'^/[A-Za-z0-9_./?&=%+-]*$',max_length=1000)
    method:str=Field(default='GET',pattern=r'^(GET|POST)$')
    params:dict[str,str|int|float|bool]=Field(default_factory=dict,max_length=30)
    body:dict|list|None=None

HARNESS = r'''
import asyncio,base64,contextlib,io,json,os,subprocess,sys,traceback
payload=json.loads(base64.b64decode(sys.argv[1]))
os.makedirs('/work/deps',exist_ok=True)
req=payload['spec'].get('requirements',[])
if req:
    installed=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-cache-dir','--target','/work/deps',*req],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=100)
    if installed.returncode: raise RuntimeError('Dependency installation failed: '+installed.stdout.decode(errors='replace')[-1500:])
sys.path.insert(0,'/work/deps')
scope={}
with contextlib.redirect_stdout(io.StringIO()): exec(compile(payload['spec']['code'],'adapter.py','exec'),scope)
results=[]
for item in payload['inputs']:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result=scope['run'](item['query'],item.get('limit',5))
            if hasattr(result,'__await__'): result=asyncio.run(result)
        results.append({'ok':True,'result':result})
    except Exception as exc: results.append({'ok':False,'error':type(exc).__name__+': '+str(exc)[:300]})
encoded=json.dumps({'results':results})
if len(encoded)>1500000: raise ValueError('Output too large')
print('INET_RESULT='+encoded)
'''

class Job(BaseModel):
    spec: dict
    inputs: list[dict] = Field(min_length=1,max_length=25)
    timeout: int = Field(default=180,ge=10,le=300)
    @field_validator('spec')
    @classmethod
    def validate_spec(cls,s):
        if len(s.get('code',''))>60000: raise ValueError('Code too large')
        if len(s.get('requirements',[]))>20: raise ValueError('Too many dependencies')
        for req in s.get('requirements',[]):
                if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*(\[[a-zA-Z0-9_,.-]+\])?==[a-zA-Z0-9_.+!-]+',req): raise ValueError('Pinned PyPI dependencies only')
        if s.get('service'):ManagedService.model_validate(s['service'])
        return s

capacity=asyncio.Semaphore(2)
service_locks={}
health_failures={}

def authorized(value):
    if not hmac.compare_digest(value,'Bearer '+os.getenv('SANDBOX_TOKEN','local-development-token')):raise HTTPException(401)

def service_name(name):return 'inet-managed-'+name
def service_url(spec):return f"http://{service_name(spec.name)}:{spec.port}"
def fingerprint(spec):return hashlib.sha256(json.dumps(spec.model_dump(),sort_keys=True).encode()).hexdigest()
def project_volume(name):return 'inet-project-'+name
def snapshot_volume(name,snapshot):return f'inet-project-{name}-snapshot-{snapshot}'
def workspace_image():return os.getenv('SANDBOX_WORKSPACE_IMAGE','inet-sandbox-workspace:local')

def helper_run(client,command,volumes,network=False,timeout=180):
    kwargs={'remove':True,'network':os.getenv('SANDBOX_NETWORK','inet-sandbox') if network else None,'network_disabled':not network,
            'volumes':volumes,'read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges'],'mem_limit':'1g','memswap_limit':'1g','nano_cpus':1_000_000_000,'pids_limit':256,
            'tmpfs':{'/tmp':'rw,nosuid,nodev,size=134217728'},'environment':{'HTTP_PROXY':'http://egress:8080','HTTPS_PROXY':'http://egress:8080','http_proxy':'http://egress:8080','https_proxy':'http://egress:8080'}}
    if command and command[0]=='chown':kwargs['cap_add']=['CHOWN']
    if not network:kwargs.pop('network')
    else:kwargs.pop('network_disabled')
    return client.containers.run(workspace_image(),command,stdout=True,stderr=True,**kwargs).decode(errors='replace')

def ensure_project_sync(spec):
    client=docker.from_env(timeout=30);created=False
    try:
        volume_name=project_volume(spec.name);seed_fingerprint=hashlib.sha256(json.dumps({'repository':spec.repository,'revision':spec.revision,'files':spec.files},sort_keys=True).encode()).hexdigest()
        try:volume=client.volumes.get(volume_name)
        except docker.errors.NotFound:
            volume=client.volumes.create(volume_name,labels={'inet.project':'true','inet.project-name':spec.name,'inet.seed-fingerprint':seed_fingerprint});created=True
        if not created and (volume.attrs.get('Labels') or {}).get('inet.seed-fingerprint') not in (None,seed_fingerprint):raise ValueError('Project name already belongs to a different source; use a new name')
        if created:
            if spec.repository:
                command=['git','clone','--depth','1','--',spec.repository,'/workspace']
                helper_run(client,command,{volume_name:{'bind':'/workspace','mode':'rw'}},True,300)
                if spec.revision:
                    helper_run(client,['git','-C','/workspace','fetch','--depth','1','origin',spec.revision],{volume_name:{'bind':'/workspace','mode':'rw'}},True,300)
                    helper_run(client,['git','-C','/workspace','checkout','--detach','FETCH_HEAD'],{volume_name:{'bind':'/workspace','mode':'rw'}})
            if spec.files:
                payload=base64.b64encode(json.dumps(spec.files).encode()).decode()
                script="""import base64,json,os,sys\nfiles=json.loads(base64.b64decode(sys.argv[1]))\nfor name,data in files.items():\n p=os.path.join('/workspace',name);os.makedirs(os.path.dirname(p),exist_ok=True);open(p,'w',encoding='utf-8').write(data)\n"""
                helper_run(client,['python','-c',script,payload],{volume_name:{'bind':'/workspace','mode':'rw'}})
            helper_run(client,['chown','-R','1000:1000','/workspace'],{volume_name:{'bind':'/workspace','mode':'rw'}})
        return inspect_project_sync(spec.name,client)
    except Exception:
        if created:
            try:client.volumes.get(project_volume(spec.name)).remove(force=True)
            except Exception:pass
        raise
    finally:client.close()

def inspect_project_sync(name,client=None):
    own=client is None;client=client or docker.from_env(timeout=15)
    try:
        volume=client.volumes.get(project_volume(name));attrs=volume.attrs
        script="""import json,os\nrows=[];total=0\nfor root,dirs,files in os.walk('/workspace'):\n dirs[:]=[d for d in dirs if d not in ('.git','node_modules','.venv','__pycache__')]\n for filename in files:\n  path=os.path.join(root,filename);rel=os.path.relpath(path,'/workspace')\n  try:size=os.path.getsize(path)\n  except OSError:continue\n  total+=size\n  if len(rows)<2000:rows.append({'path':rel,'size':size})\nprint('INET_PROJECT='+json.dumps({'files':rows,'file_count':len(rows),'bytes':total}))\n"""
        output=helper_run(client,['python','-c',script],{project_volume(name):{'bind':'/workspace','mode':'ro'}})
        marker=next(line[13:] for line in output.splitlines() if line.startswith('INET_PROJECT='));data=json.loads(marker)
        snapshots=[]
        for volume in client.volumes.list(filters={'label':['inet.project-snapshot=true',f'inet.project-name={name}']}):
            labels=volume.attrs.get('Labels') or {};snapshots.append({'id':labels.get('inet.snapshot'),'created_at':float(labels.get('inet.created-at','0'))})
        return {'name':name,'volume':attrs.get('Name',project_volume(name)),'snapshots':sorted(snapshots,key=lambda x:x['created_at'],reverse=True)[:20],**data}
    finally:
        if own:client.close()

def list_projects_sync():
    client=docker.from_env(timeout=20)
    try:
        names=[(v.attrs.get('Labels') or {}).get('inet.project-name') for v in client.volumes.list(filters={'label':'inet.project=true'})]
    finally:client.close()
    return [inspect_project_sync(name) for name in names if name]

def read_project_file_sync(name,path):
    if not re.fullmatch(SAFE_PROJECT_PATH,path):raise ValueError('Unsafe project path')
    client=docker.from_env(timeout=15)
    try:
        script="""import base64,os,sys\np=os.path.realpath('/workspace/'+sys.argv[1]);root='/workspace/'\nif not p.startswith(root) or not os.path.isfile(p):raise ValueError('File not found')\ndata=open(p,'rb').read(1000001)\nif len(data)>1000000:raise ValueError('File is too large')\nprint('INET_FILE='+base64.b64encode(data).decode())\n"""
        output=helper_run(client,['python','-c',script,path],{project_volume(name):{'bind':'/workspace','mode':'ro'}})
        encoded=next(line[10:] for line in output.splitlines() if line.startswith('INET_FILE='))
        return {'name':name,'path':path,'content':base64.b64decode(encoded).decode(errors='replace')}
    finally:client.close()

def snapshot_project_sync(name):
    client=docker.from_env(timeout=30)
    try:
        client.volumes.get(project_volume(name));snapshot=time.strftime('%Y%m%d%H%M%S')+'-'+hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        target=snapshot_volume(name,snapshot);client.volumes.create(target,labels={'inet.project-snapshot':'true','inet.project-name':name,'inet.snapshot':snapshot,'inet.created-at':str(time.time())})
        helper_run(client,['sh','-c','cp -a /source/. /target/'],{project_volume(name):{'bind':'/source','mode':'ro'},target:{'bind':'/target','mode':'rw'}},False,300)
        return {'name':name,'snapshot':snapshot}
    finally:client.close()

def mutate_project_sync(name,mutation):
    checkpoint=snapshot_project_sync(name);client=docker.from_env(timeout=30)
    try:
        payload=base64.b64encode(json.dumps({'writes':mutation.writes,'deletes':mutation.deletes}).encode()).decode()
        script="""import base64,json,os,shutil,sys\npayload=json.loads(base64.b64decode(sys.argv[1]));root='/workspace'\ndef safe(name):\n p=os.path.realpath(os.path.join(root,name));\n if not p.startswith(root+'/'):raise ValueError('Unsafe path')\n return p\nfor name in payload['deletes']:\n p=safe(name)\n if os.path.isdir(p):shutil.rmtree(p)\n elif os.path.exists(p):os.unlink(p)\nfor name,data in payload['writes'].items():\n p=safe(name);os.makedirs(os.path.dirname(p),exist_ok=True);open(p,'w',encoding='utf-8').write(data)\n"""
        helper_run(client,['python','-c',script,payload],{project_volume(name):{'bind':'/workspace','mode':'rw'}})
        if mutation.patch:
            encoded=base64.b64encode(mutation.patch.encode()).decode()
            patch_script="import base64,subprocess,sys;data=base64.b64decode(sys.argv[1]);p=subprocess.run(['patch','-p1','--forward','--batch'],cwd='/workspace',input=data,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);print(p.stdout.decode(errors='replace'));raise SystemExit(p.returncode)"
            helper_run(client,['python','-c',patch_script,encoded],{project_volume(name):{'bind':'/workspace','mode':'rw'}})
        helper_run(client,['chown','-R','1000:1000','/workspace'],{project_volume(name):{'bind':'/workspace','mode':'rw'}})
        return {**inspect_project_sync(name,client),'snapshot':checkpoint['snapshot'],'reason':mutation.reason}
    except Exception:
        rollback_project_sync(name,checkpoint['snapshot']);raise
    finally:client.close()

def rollback_project_sync(name,snapshot):
    if not re.fullmatch(r'[0-9]{14}-[a-f0-9]{8}',snapshot):raise ValueError('Invalid snapshot')
    client=docker.from_env(timeout=30)
    try:
        client.volumes.get(snapshot_volume(name,snapshot));client.volumes.get(project_volume(name))
        helper_run(client,['sh','-c','find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && cp -a /source/. /target/'],{snapshot_volume(name,snapshot):{'bind':'/source','mode':'ro'},project_volume(name):{'bind':'/target','mode':'rw'}},False,300)
        helper_run(client,['chown','-R','1000:1000','/target'],{project_volume(name):{'bind':'/target','mode':'rw'}})
        return {**inspect_project_sync(name,client),'rolled_back_to':snapshot}
    finally:client.close()

def run_project_command_sync(name,spec,command):
    client=docker.from_env(timeout=30);container=None
    try:
        if spec.runtime_image!=workspace_image():client.images.pull(spec.runtime_image)
        environment={'HOME':'/tmp/home','CI':'true'}
        if command.network:environment.update(HTTP_PROXY='http://egress:8080',HTTPS_PROXY='http://egress:8080',http_proxy='http://egress:8080',https_proxy='http://egress:8080')
        kwargs={'detach':True,'user':'1000:1000','working_dir':'/workspace','read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges'],
                'mem_limit':f'{spec.memory_mb}m','memswap_limit':f'{spec.memory_mb}m','nano_cpus':int(spec.cpus*1_000_000_000),'pids_limit':spec.pids,
                'tmpfs':{'/tmp':'rw,nosuid,nodev,size=268435456,uid=1000,gid=1000'},'volumes':{project_volume(name):{'bind':'/workspace','mode':'rw'}},'environment':environment,
                'labels':{'inet.project-command':'true','inet.project-name':name},'log_config':docker.types.LogConfig(type='json-file',config={'max-size':'5m','max-file':'1'})}
        if command.network:kwargs['network']=os.getenv('SANDBOX_NETWORK','inet-sandbox')
        else:kwargs['network_disabled']=True
        container=client.containers.run(spec.runtime_image,['timeout','--signal=KILL',str(command.timeout),*command.argv],**kwargs)
        status=container.wait(timeout=command.timeout+10);output=container.logs(tail=4000).decode(errors='replace')[-1_000_000:]
        return {'argv':command.argv,'exit_code':status['StatusCode'],'output':output,'ok':status['StatusCode']==0}
    finally:
        if container is not None:container.remove(force=True)
        client.close()

def write_config(client,spec):
    if not spec.config_files:return None
    volume_name=service_name(spec.name)+'-config'
    try:volume=client.volumes.get(volume_name)
    except docker.errors.NotFound:volume=client.volumes.create(volume_name,labels={'inet.managed':'true','inet.service':spec.name})
    payload=base64.b64encode(json.dumps(spec.config_files).encode()).decode()
    script="""import base64,json,os,sys\nfiles=json.loads(base64.b64decode(sys.argv[1]))\nos.makedirs('/config',exist_ok=True)\nfor old in os.listdir('/config'):\n p='/config/'+old\n if os.path.isfile(p): os.unlink(p)\nfor name,data in files.items():\n open('/config/'+name,'w',encoding='utf-8').write(data)\n"""
    client.containers.run(os.getenv('SANDBOX_CONFIG_IMAGE','python:3.12-slim'),['python','-c',script,payload],remove=True,network_disabled=True,volumes={volume_name:{'bind':'/config','mode':'rw'}},labels={'inet.config-writer':'true'})
    return volume_name

def inspect_service(container,spec=None):
    container.reload();attrs=container.attrs;state=attrs.get('State',{})
    stats={}
    if state.get('Running'):
        try:
            raw=container.stats(stream=False);memory=raw.get('memory_stats',{})
            cpu=raw.get('cpu_stats',{});pre=raw.get('precpu_stats',{})
            cpu_delta=cpu.get('cpu_usage',{}).get('total_usage',0)-pre.get('cpu_usage',{}).get('total_usage',0)
            system_delta=cpu.get('system_cpu_usage',0)-pre.get('system_cpu_usage',0)
            cores=cpu.get('online_cpus') or len(cpu.get('cpu_usage',{}).get('percpu_usage',[])) or 1
            stats={'memory_bytes':memory.get('usage',0),'memory_limit_bytes':memory.get('limit',0),'cpu_percent':round((cpu_delta/system_delta)*cores*100,2) if system_delta>0 else 0}
        except Exception:stats={}
    labels=attrs.get('Config',{}).get('Labels',{}) or {}
    return {'name':labels.get('inet.service'),'status':state.get('Status',container.status),'healthy':health_failures.get(labels.get('inet.service'),0)==0,'restart_count':state.get('RestartCount',attrs.get('RestartCount',0)),'image':labels.get('inet.image'),'resolved_image':labels.get('inet.resolved-image',''),'port':int(labels.get('inet.port','0')),'health_path':labels.get('inet.health-path','/'),**stats}

def probe(spec,timeout=5):
    try:
        with urllib.request.urlopen(service_url(spec)+spec.health_path,timeout=timeout) as response:return response.status<500
    except Exception:return False

def wait_ready(spec):
    deadline=time.monotonic()+spec.readiness_timeout
    while time.monotonic()<deadline:
        if probe(spec):health_failures[spec.name]=0;return
        time.sleep(1)
    raise RuntimeError('Managed service failed its readiness check')

def ensure_service_sync(spec):
    client=docker.from_env(timeout=max(10,spec.readiness_timeout))
    name=service_name(spec.name);wanted=fingerprint(spec)
    try:
        try:container=client.containers.get(name)
        except docker.errors.NotFound:container=None
        if container and (container.labels or {}).get('inet.fingerprint')!=wanted:
            container.remove(force=True);container=None
        if container is None:
            try:image=client.images.pull(spec.image)
            except docker.errors.ImageNotFound:image=client.images.pull(spec.image)
            resolved=next(iter(image.attrs.get('RepoDigests') or []),spec.image)
            volumes={}
            config_volume=write_config(client,spec)
            if config_volume:volumes[config_volume]={'bind':spec.config_dir,'mode':'rw'}
            for index,path in enumerate(spec.data_dirs):
                volume_name=f'{name}-data-{index}'
                try:client.volumes.get(volume_name)
                except docker.errors.NotFound:client.volumes.create(volume_name,labels={'inet.managed':'true','inet.service':spec.name})
                volumes[volume_name]={'bind':path,'mode':'rw'}
            if spec.project:
                client.volumes.get(project_volume(spec.project))
                volumes[project_volume(spec.project)]={'bind':spec.project_dir,'mode':'rw'}
            env={**spec.environment,'HTTP_PROXY':'http://egress:8080','HTTPS_PROXY':'http://egress:8080','http_proxy':'http://egress:8080','https_proxy':'http://egress:8080','NO_PROXY':'localhost,127.0.0.1','no_proxy':'localhost,127.0.0.1'}
            labels={'inet.managed':'true','inet.service':spec.name,'inet.fingerprint':wanted,'inet.image':spec.image,'inet.resolved-image':resolved,'inet.port':str(spec.port),'inet.health-path':spec.health_path}
            kwargs=dict(name=name,detach=True,network=os.getenv('SANDBOX_NETWORK','inet-sandbox'),environment=env,labels=labels,read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges'],mem_limit=f'{spec.memory_mb}m',memswap_limit=f'{spec.memory_mb}m',nano_cpus=int(spec.cpus*1_000_000_000),pids_limit=spec.pids,tmpfs={'/tmp':'rw,nosuid,nodev,size=268435456','/var/tmp':'rw,nosuid,nodev,size=67108864'},volumes=volumes,restart_policy={'Name':'unless-stopped'},log_config=docker.types.LogConfig(type='json-file',config={'max-size':'5m','max-file':'2'}))
            if spec.working_dir:kwargs['working_dir']=spec.working_dir
            if spec.command:kwargs['command']=spec.command
            container=client.containers.run(resolved,**kwargs)
        elif container.status!='running':
            container.update(restart_policy={'Name':'unless-stopped'});container.start()
        if not probe(spec):
            container.restart(timeout=10);wait_ready(spec)
        return inspect_service(container,spec)
    finally:client.close()

def list_services_sync():
    client=docker.from_env(timeout=10)
    try:return [inspect_service(c) for c in client.containers.list(all=True,filters={'label':'inet.managed=true'})]
    finally:client.close()

async def monitor_services():
    while True:
        await asyncio.sleep(20)
        try:
            for item in await asyncio.to_thread(list_services_sync):
                name=item.get('name')
                if not name:continue
                client=docker.from_env(timeout=10)
                try:
                    container=client.containers.get(service_name(name));labels=container.labels or {}
                    spec=ManagedService(name=name,image=labels['inet.image'],port=int(labels['inet.port']),health_path=labels.get('inet.health-path','/'))
                    container.reload();restart_policy=container.attrs.get('HostConfig',{}).get('RestartPolicy',{}).get('Name','')
                    if container.status!='running' and restart_policy=='no':continue
                    ok=container.status=='running' and await asyncio.to_thread(probe,spec)
                    health_failures[name]=0 if ok else health_failures.get(name,0)+1
                    if health_failures[name]>=3:container.restart(timeout=10);health_failures[name]=0
                finally:client.close()
        except Exception:pass

@asynccontextmanager
async def lifespan(app):
    task=asyncio.create_task(monitor_services())
    yield
    task.cancel();await asyncio.gather(task,return_exceptions=True)

app=FastAPI(title='INET isolated runner and managed tool control plane',lifespan=lifespan)

def execute(job):
    client=docker.from_env(timeout=10)
    container=None
    try:
        if job.spec.get('service'):ensure_service_sync(ManagedService.model_validate(job.spec['service']))
        payload=base64.b64encode(json.dumps(job.model_dump()).encode()).decode()
        service=ManagedService.model_validate(job.spec['service']) if job.spec.get('service') else None
        runtime_env={'HTTP_PROXY':'http://egress:8080','HTTPS_PROXY':'http://egress:8080','http_proxy':'http://egress:8080','https_proxy':'http://egress:8080','HOME':'/work','PLAYWRIGHT_BROWSERS_PATH':'/ms-playwright'}
        if service:runtime_env['NO_PROXY']=runtime_env['no_proxy']=service_name(service.name)+',fixtures,localhost,127.0.0.1'
        container=client.containers.run(os.getenv('SANDBOX_IMAGE','inet-sandbox-runtime:local'),['timeout','--signal=KILL',str(job.timeout),'python','-c',HARNESS,payload],detach=True,
            user='1000:1000',working_dir='/work',read_only=True,cap_drop=['ALL'],security_opt=['no-new-privileges'],
            mem_limit='1g',memswap_limit='1g',nano_cpus=1_000_000_000,pids_limit=128,
            tmpfs={'/work':'rw,nosuid,nodev,size=536870912,uid=1000,gid=1000','/tmp':'rw,nosuid,nodev,size=134217728,uid=1000,gid=1000'},
            network=os.getenv('SANDBOX_NETWORK','inet-sandbox'),
            environment=runtime_env,
            labels={'inet.sandbox':'true'},log_config=docker.types.LogConfig(type='json-file',config={'max-size':'2m','max-file':'1'}))
        status=container.wait(timeout=job.timeout)
        output=container.logs(tail=1000).decode(errors='replace')[-1600000:]
        if status['StatusCode']!=0: raise RuntimeError('Sandbox exit '+str(status['StatusCode'])+': '+output[-1500:])
        lines=[line[12:] for line in output.splitlines() if line.startswith('INET_RESULT=')]
        if not lines: raise RuntimeError('Adapter did not produce result')
        return {**json.loads(lines[-1]),'image':os.getenv('SANDBOX_IMAGE','inet-sandbox-runtime:local')}
    finally:
        if container is not None: container.remove(force=True)
        client.close()

@app.get('/health')
async def health():
    try:
        def ping():
            client = docker.from_env(timeout=3)
            try:
                return client.ping()
            finally:
                client.close()
        await asyncio.to_thread(ping)
        return {'status':'ok'}
    except Exception: return {'status':'docker_unavailable'}

@app.post('/execute')
async def run(job:Job,authorization:str=Header(default='')):
    authorized(authorization)
    if len(json.dumps(job.model_dump()))>120000: raise HTTPException(413)
    async with capacity:
        try: return await asyncio.to_thread(execute,job)
        except Exception as exc: raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1600])

@app.get('/services')
async def services(authorization:str=Header(default='')):
    authorized(authorization)
    try:return {'services':await asyncio.to_thread(list_services_sync)}
    except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:800])

@app.get('/projects')
async def projects(authorization:str=Header(default='')):
    authorized(authorization)
    try:return {'projects':await asyncio.to_thread(list_projects_sync)}
    except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1000])

@app.post('/projects/ensure')
async def ensure_project(spec:ManagedProject,authorization:str=Header(default='')):
    authorized(authorization)
    lock=service_locks.setdefault('project:'+spec.name,asyncio.Lock())
    async with lock:
        try:return await asyncio.to_thread(ensure_project_sync,spec)
        except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1600])

@app.get('/projects/{name}/file')
async def project_file(name:str,path:str,authorization:str=Header(default='')):
    authorized(authorization)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise HTTPException(400)
    try:return await asyncio.to_thread(read_project_file_sync,name,path)
    except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1000])

@app.post('/projects/{name}/mutate')
async def mutate_project(name:str,mutation:ProjectMutation,authorization:str=Header(default='')):
    authorized(authorization)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise HTTPException(400)
    lock=service_locks.setdefault('project:'+name,asyncio.Lock())
    async with lock:
        try:return await asyncio.to_thread(mutate_project_sync,name,mutation)
        except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1600])

@app.post('/projects/{name}/snapshot')
async def snapshot_project(name:str,authorization:str=Header(default='')):
    authorized(authorization)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise HTTPException(400)
    try:return await asyncio.to_thread(snapshot_project_sync,name)
    except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1000])

@app.post('/projects/{name}/rollback/{snapshot}')
async def rollback_project(name:str,snapshot:str,authorization:str=Header(default='')):
    authorized(authorization)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise HTTPException(400)
    lock=service_locks.setdefault('project:'+name,asyncio.Lock())
    async with lock:
        try:return await asyncio.to_thread(rollback_project_sync,name,snapshot)
        except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1000])

@app.post('/projects/{name}/command')
async def project_command(name:str,payload:ProjectCommandRequest,authorization:str=Header(default='')):
    authorized(authorization)
    if name!=payload.spec.name:raise HTTPException(400,'Project name mismatch')
    async with capacity:
        try:return await asyncio.to_thread(run_project_command_sync,name,payload.spec,payload.command)
        except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1600])

@app.post('/services/ensure')
async def ensure_service(spec:ManagedService,authorization:str=Header(default='')):
    authorized(authorization)
    lock=service_locks.setdefault(spec.name,asyncio.Lock())
    async with lock:
        try:return await asyncio.to_thread(ensure_service_sync,spec)
        except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:1200])

@app.post('/services/{name}/{action}')
async def service_action(name:str,action:str,authorization:str=Header(default='')):
    authorized(authorization)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name) or action not in ('restart','stop'):raise HTTPException(400)
    def apply():
        client=docker.from_env(timeout=30)
        try:
            container=client.containers.get(service_name(name))
            if action=='restart':container.update(restart_policy={'Name':'unless-stopped'});container.restart(timeout=10)
            else:container.update(restart_policy={'Name':'no'});container.stop(timeout=10);health_failures[name]=0
            return inspect_service(container)
        finally:client.close()
    try:return await asyncio.to_thread(apply)
    except docker.errors.NotFound:raise HTTPException(404,'Managed service not found')

@app.post('/service-request/{name}')
async def service_request(name:str,payload:ServiceRequest,authorization:str=Header(default='')):
    authorized(authorization)
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,40}',name):raise HTTPException(400)
    def call():
        client=docker.from_env(timeout=10)
        try:
            container=client.containers.get(service_name(name));labels=container.labels or {};port=int(labels['inet.port'])
        finally:client.close()
        url=f'http://{service_name(name)}:{port}'+payload.path
        if payload.params:url+='?'+urllib.parse.urlencode(payload.params)
        data=json.dumps(payload.body).encode() if payload.body is not None else None
        request=urllib.request.Request(url,data=data,method=payload.method,headers={'Content-Type':'application/json'} if data else {})
        with urllib.request.urlopen(request,timeout=40) as response:
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('Managed service response is too large')
            return {'status':response.status,'data':json.loads(raw)}
    try:return await asyncio.to_thread(call)
    except Exception as exc:raise HTTPException(502,type(exc).__name__+': '+str(exc)[:800])
