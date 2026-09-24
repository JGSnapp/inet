import asyncio
import importlib.util
import json
from pathlib import Path
import pytest

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'sandbox'/file)
    loaded=importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name]=loaded
    spec.loader.exec_module(loaded)
    return loaded

def test_sandbox_container_limits_and_cleanup(monkeypatch):
    pytest.importorskip('docker')
    worker=module('sandbox_worker_test','worker.py')
    calls={}
    class Container:
        def wait(self,timeout):calls['timeout']=timeout;return {'StatusCode':0}
        def logs(self,tail):return b'INET_RESULT={"results":[{"ok":true,"result":{"content":"test"}}]}'
        def remove(self,force):calls['removed']=force
    class Containers:
        def run(self,image,command,**kwargs):calls.update(kwargs);calls['command']=command;return Container()
    class Client:
        containers=Containers()
        def close(self):calls['closed']=True
    monkeypatch.setattr(worker.docker,'from_env',lambda **kwargs:Client())
    output=worker.execute(worker.Job(spec={'code':'def run(query,limit): return {}','requirements':['httpx==0.28.1']},inputs=[{'query':'https://example.com'}]))
    assert output['results'][0]['ok']
    assert calls['read_only'] and calls['cap_drop']==['ALL']
    assert calls['user']=='1000:1000' and calls['pids_limit']==128
    assert calls['network']=='inet-sandbox' and calls['mem_limit']=='1g'
    assert calls['removed'] and calls['closed']
    assert not any(key in calls for key in ('privileged','volumes','mounts'))
    assert all('KEY' not in k and 'TOKEN' not in k for k in calls['environment'])

def test_sandbox_rejects_unpinned_installs():
    pytest.importorskip('docker')
    worker=module('sandbox_worker_validation','worker.py')
    with pytest.raises(ValueError):worker.Job(spec={'code':'x','requirements':['git+https://evil.example/repo']},inputs=[{'query':'x'}])

def test_managed_service_is_hardened_and_resource_limited(monkeypatch):
    pytest.importorskip('docker')
    worker=module('sandbox_worker_managed_test','worker.py');calls={}
    class Image:attrs={'RepoDigests':['example/tool@sha256:'+'a'*64]}
    class Images:
        def pull(self,image):calls['pulled']=image;return Image()
    class Container:
        status='running';labels={'inet.service':'tool','inet.image':'example/tool:1','inet.port':'8080'}
        attrs={'State':{'Status':'running','Running':True},'Config':{'Labels':labels},'RestartCount':0}
        def reload(self):pass
        def stats(self,stream=False):return {'memory_stats':{'usage':1024,'limit':268435456},'cpu_stats':{},'precpu_stats':{}}
    container=Container()
    class Containers:
        def get(self,name):raise worker.docker.errors.NotFound('missing')
        def run(self,image,**kwargs):calls.update(kwargs);calls['resolved']=image;container.labels=kwargs['labels'];container.attrs['Config']['Labels']=kwargs['labels'];return container
    class Volumes:pass
    class Client:
        images=Images();containers=Containers();volumes=Volumes()
        def close(self):calls['closed']=True
    monkeypatch.setattr(worker.docker,'from_env',lambda **kwargs:Client())
    monkeypatch.setattr(worker,'probe',lambda spec,timeout=5:True)
    result=worker.ensure_service_sync(worker.ManagedService(name='tool',image='example/tool:1',port=8080,memory_mb=256,cpus=.5,pids=64))
    assert result['status']=='running' and calls['pulled']=='example/tool:1'
    assert calls['read_only'] and calls['cap_drop']==['ALL'] and calls['network']=='inet-sandbox'
    assert calls['mem_limit']=='256m' and calls['nano_cpus']==500_000_000 and calls['pids_limit']==64
    assert 'ports' not in calls and 'privileged' not in calls and calls['closed']

def test_managed_service_rejects_embedded_secrets():
    pytest.importorskip('docker')
    worker=module('sandbox_worker_managed_validation','worker.py')
    with pytest.raises(ValueError):worker.ManagedService(name='tool',image='example/tool:1',port=8080,environment={'API_KEY':'secret'})
    with pytest.raises(ValueError):worker.ManagedService(name='tool',image='latest',port=8080)

def test_managed_project_rejects_escape_and_repository_credentials():
    pytest.importorskip('docker')
    worker=module('sandbox_worker_project_validation','worker.py')
    with pytest.raises(ValueError):worker.ManagedProject(name='tool-code',files={'../secret':'x'})
    with pytest.raises(ValueError):worker.ManagedProject(name='tool-code',repository='https://user:pass@example.com/repo.git')
    with pytest.raises(ValueError):worker.ProjectMutation(writes={'ok/../../secret':'x'})

def test_project_command_is_resource_limited_and_offline(monkeypatch):
    pytest.importorskip('docker')
    worker=module('sandbox_worker_project_command','worker.py');calls={}
    class Container:
        def wait(self,timeout):calls['timeout']=timeout;return {'StatusCode':0}
        def logs(self,tail):return b'tests passed'
        def remove(self,force):calls['removed']=force
    class Containers:
        def run(self,image,command,**kwargs):calls.update(kwargs);calls['image']=image;calls['command']=command;return Container()
    class Images:
        def pull(self,image):raise AssertionError('local workspace image must not be pulled')
    class Client:
        containers=Containers();images=Images()
        def close(self):calls['closed']=True
    monkeypatch.setattr(worker.docker,'from_env',lambda **kwargs:Client())
    spec=worker.ManagedProject(name='tool-code',test_commands=[])
    result=worker.run_project_command_sync('tool-code',spec,worker.ProjectCommand(argv=['python','-m','pytest'],timeout=30))
    assert result['ok'] and result['output']=='tests passed'
    assert calls['network_disabled'] and calls['read_only'] and calls['cap_drop']==['ALL']
    assert calls['volumes']=={'inet-project-tool-code':{'bind':'/workspace','mode':'rw'}}
    assert calls['mem_limit']=='1024m' and calls['pids_limit']==256 and calls['removed'] and calls['closed']

@pytest.mark.parametrize('host,port',[('127.0.0.1',80),('169.254.169.254',443),('10.0.0.1',80),('example.com',22)])
def test_egress_private_addresses(host,port):
    egress=module('egress_test','egress.py')
    with pytest.raises(ValueError):asyncio.run(egress.destination(host,port))

def test_egress_only_fixture_exception():
    egress=module('egress_fixture_test','egress.py')
    assert asyncio.run(egress.destination('fixtures',8081))=='fixtures'
    with pytest.raises(ValueError):asyncio.run(egress.destination('fixtures',8090))
