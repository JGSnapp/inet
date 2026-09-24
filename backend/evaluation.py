"""Frozen conformance suite plus configurable, source-attributed live benchmarks."""
import hashlib
import json
import copy
from pathlib import Path
from contracts import result_contract

def fixtures(mode):
    if mode=='search': return json.loads(Path(__file__).with_name('benchmarks.json').read_text())['search']
    return [{'query':f'http://fixtures:8081/{i}','expected':f'INET_EVIDENCE_{1 if i==10 else i:02}','failure':i in (11,12,13)} for i in range(1,21)]

def judge(spec,outputs,suite):
    details=[]
    for i,fixture in enumerate(suite):
        output=outputs[i] if i<len(outputs) else {'ok':False,'error':'missing result'}
        valid=False;reason=output.get('error','')
        try:
            if not output.get('ok'): raise ValueError(reason)
            result=result_contract(copy.deepcopy(output['result']),spec['mode'])
            text=result['content'] if spec['mode']=='fetch' else json.dumps(result['sources'],ensure_ascii=False)
            if fixture.get('failure'): raise ValueError('False positive on empty/blocked/error page')
            valid=fixture['expected'].lower() in text.lower()
            reason='' if valid else 'Expected evidence missing'
        except Exception as exc:
            # A failed adapter counts as correct only on a fixture explicitly expected to fail.
            valid=bool(fixture.get('failure') and (not output.get('ok') or not output.get('result',{}).get('content') or int(output.get('result',{}).get('status',200))>=400))
            reason='' if valid else str(exc)[:300]
        details.append({'query':fixture['query'],'passed':valid,'reason':reason})
    passed=sum(x['passed'] for x in details)
    return {'count':len(suite),'passed':passed,'score':passed/len(suite),'eligible':len(suite)>=20 and passed>=len(suite)*.8,'suite_digest':hashlib.sha256(json.dumps(suite,sort_keys=True).encode()).hexdigest(),'details':details}
