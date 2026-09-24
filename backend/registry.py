import difflib
import hashlib
import json
import time
from contracts import AdapterSpec

class Registry:
    def __init__(self,store): self.store=store

    def create(self,spec):
        spec=AdapterSpec.model_validate(spec).model_dump()
        digest=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
        id=spec['name']+'@'+digest[:12]
        if self.store.load('versions',id): return self.store.load('versions',id)
        previous=self.store.load('versions',spec['parent']) if spec['parent'] else None
        if spec['parent'] and (not previous or previous['spec']['name']!=spec['name']): raise ValueError('Invalid parent version')
        record={'id':id,'digest':digest,'spec':spec,'status':'candidate','created_at':time.time(),'successes':0,'failures':0,
                'diff':'\n'.join(difflib.unified_diff((previous['spec']['code'] if previous else '').splitlines(),spec['code'].splitlines(),fromfile=spec['parent'] or 'empty',tofile=id))}
        self.store.save('versions',id,record)
        return record

    def promote(self,id):
        record=self.store.load('versions',id)
        if not record: raise ValueError('Version not found')
        report=self.store.load('evaluations',id)
        if not report or not report['eligible'] or report['digest']!=record['digest']: raise ValueError('Version has not passed its benchmark')
        old=self.store.load('active',record['spec']['name'])
        if old and old['id']==id: return record
        record.update(status='canary',previous=old['id'] if old else None,successes=0,failures=0)
        self.store.save('versions',id,record)
        self.store.save('active',record['spec']['name'],{'id':id})
        self.audit('promote',id)
        return record

    def rollback(self,id):
        record=self.store.load('versions',id)
        if not record: raise ValueError('Version not found')
        active=self.store.load('active',record['spec']['name'])
        if active and active['id']==id:
            if record.get('previous'): self.store.save('active',record['spec']['name'],{'id':record['previous']})
            else: self.store.delete('active',record['spec']['name'])
        record['status']='rolled_back';self.store.save('versions',id,record)
        self.audit('rollback',id)
        return record

    def audit(self,action,id):
        from uuid import uuid4
        self.store.save('audit',str(uuid4()),{'action':action,'version':id,'at':time.time()})

    def active(self,mode):
        result=[]
        for pointer in self.store.all('active'):
            version=self.store.load('versions',pointer['id'])
            if version and version['spec']['mode']==mode: result.append(version)
        return result

    def observe(self,id,success):
        version=self.store.load('versions',id)
        if not version: return
        version['successes' if success else 'failures']+=1
        version['recent']=(version.get('recent',[])+[bool(success)])[-10:]
        if version['status']=='canary' and version['successes']>=5: version['status']='active'
        self.store.save('versions',id,version)
        if (version['status']=='canary' and version['failures']>=2) or (len(version['recent'])>=5 and sum(version['recent'][-5:])<=2):
            self.rollback(id)
            self.store.save('notices',id,{'version':id,'reason':'runtime_regression','created_at':time.time()})
