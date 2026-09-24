import os
import httpx
from contracts import ManagedProjectSpec,ManagedServiceSpec,ProjectCommand,ProjectMutation

class SandboxUnavailable(RuntimeError): pass
class SandboxExecutionError(ValueError): pass

class Sandbox:
    def _settings(self):
        return os.getenv('SANDBOX_URL','http://127.0.0.1:8090'),os.getenv('SANDBOX_TOKEN','local-development-token')

    async def execute(self,spec,inputs,timeout=180):
        base,token=self._settings()
        try:
            async with httpx.AsyncClient(timeout=timeout+20,trust_env=False) as client:
                response=await client.post(base+'/execute',headers={'Authorization':'Bearer '+token},json={'spec':spec,'inputs':inputs,'timeout':timeout})
                if response.status_code==502:raise SandboxExecutionError(str(response.json().get('detail','Sandbox execution failed'))[:1600])
                response.raise_for_status()
                return response.json()
        except (httpx.ConnectError,httpx.TimeoutException) as exc: raise SandboxUnavailable('Песочница недоступна: запустите sandbox service') from exc

    async def health(self):
        try:
            async with httpx.AsyncClient(timeout=3,trust_env=False) as client:
                r=await client.get(os.getenv('SANDBOX_URL','http://127.0.0.1:8090')+'/health')
                return r.json()
        except Exception: return {'status':'unavailable'}

    async def services(self):
        base,token=self._settings()
        try:
            async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
                response=await client.get(base+'/services',headers={'Authorization':'Bearer '+token})
                if response.status_code==502:raise SandboxUnavailable(str(response.json().get('detail','Service manager failed'))[:1200])
                response.raise_for_status();return response.json()['services']
        except (httpx.ConnectError,httpx.TimeoutException) as exc:raise SandboxUnavailable('Sandbox service manager is unavailable') from exc

    async def ensure_service(self,spec):
        service=ManagedServiceSpec.model_validate(spec)
        base,token=self._settings()
        try:
            async with httpx.AsyncClient(timeout=service.readiness_timeout+120,trust_env=False) as client:
                response=await client.post(base+'/services/ensure',headers={'Authorization':'Bearer '+token},json=service.model_dump())
                if response.status_code==502:raise SandboxUnavailable(str(response.json().get('detail','Service manager failed'))[:1200])
                response.raise_for_status();return response.json()
        except (httpx.ConnectError,httpx.TimeoutException) as exc:raise SandboxUnavailable('Sandbox service manager is unavailable') from exc

    async def service_action(self,name,action):
        if action not in ('restart','stop'):raise ValueError('Unknown service action')
        base,token=self._settings()
        try:
            async with httpx.AsyncClient(timeout=120,trust_env=False) as client:
                response=await client.post(f'{base}/services/{name}/{action}',headers={'Authorization':'Bearer '+token})
                if response.status_code==502:raise SandboxUnavailable(str(response.json().get('detail','Service manager failed'))[:1200])
                response.raise_for_status();return response.json()
        except (httpx.ConnectError,httpx.TimeoutException) as exc:raise SandboxUnavailable('Sandbox service manager is unavailable') from exc

    async def service_request(self,name,path='/',params=None,method='GET',body=None):
        base,token=self._settings()
        try:
            async with httpx.AsyncClient(timeout=45,trust_env=False) as client:
                response=await client.post(f'{base}/service-request/{name}',headers={'Authorization':'Bearer '+token},json={'path':path,'method':method,'params':params or {},'body':body})
                if response.status_code==502:raise SandboxUnavailable(str(response.json().get('detail','Managed tool request failed'))[:1200])
                response.raise_for_status();return response.json()
        except (httpx.ConnectError,httpx.TimeoutException) as exc:raise SandboxUnavailable('Managed tool request failed') from exc

    async def _project_request(self,method,path,json=None,params=None,timeout=180):
        base,token=self._settings()
        try:
            async with httpx.AsyncClient(timeout=timeout,trust_env=False) as client:
                response=await client.request(method,base+path,headers={'Authorization':'Bearer '+token},json=json,params=params)
                if response.status_code==502:raise SandboxExecutionError(str(response.json().get('detail','Project operation failed'))[:1600])
                response.raise_for_status();return response.json()
        except (httpx.ConnectError,httpx.TimeoutException) as exc:raise SandboxUnavailable('Project workspace manager is unavailable') from exc

    async def projects(self):return (await self._project_request('GET','/projects',timeout=45))['projects']

    async def ensure_project(self,spec):
        value=ManagedProjectSpec.model_validate(spec)
        return await self._project_request('POST','/projects/ensure',value.model_dump(),timeout=360)

    async def project_file(self,name,path):
        return await self._project_request('GET',f'/projects/{name}/file',params={'path':path},timeout=45)

    async def mutate_project(self,name,mutation):
        value=ProjectMutation.model_validate(mutation)
        return await self._project_request('POST',f'/projects/{name}/mutate',value.model_dump(),timeout=360)

    async def snapshot_project(self,name):return await self._project_request('POST',f'/projects/{name}/snapshot',timeout=360)

    async def rollback_project(self,name,snapshot):return await self._project_request('POST',f'/projects/{name}/rollback/{snapshot}',timeout=360)

    async def project_command(self,spec,command):
        project=ManagedProjectSpec.model_validate(spec);cmd=ProjectCommand.model_validate(command)
        return await self._project_request('POST',f'/projects/{project.name}/command',{'spec':project.model_dump(),'command':cmd.model_dump()},timeout=cmd.timeout+30)
