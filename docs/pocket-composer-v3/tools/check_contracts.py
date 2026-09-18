"""Validate the reference contracts, invariants and explicit negative examples.
Does not connect to a server or perform native desktop actions.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
ROOT = Path(__file__).resolve().parents[1]

def read(name: str):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))

def digest(bundle: dict) -> str:
    clean = {k: v for k, v in bundle.items() if k != 'manifest_hash'}
    raw = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def validate(kind: str, data: dict) -> None:
    schema = read(f'contracts/{kind}.schema.json')
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
    if kind == 'bundle':
        if len(data['text'].encode('utf-8')) > 65536: raise ValueError('text byte limit')
        if not data['text'].strip() and not data['assets']: raise ValueError('empty bundle')
        if sum(a['bytes'] for a in data['assets']) > 24 * 1024 * 1024: raise ValueError('total byte limit')
        if len({a['asset_id'] for a in data['assets']}) != len(data['assets']): raise ValueError('duplicate asset id')
        if digest(data) != data['manifest_hash']: raise ValueError('manifest mismatch')
    if kind == 'attempt':
        steps=data['steps']
        if [x['index'] for x in steps] != list(range(len(steps))): raise ValueError('noncontiguous steps')
        if data['result']=='CONFIRMED' and (not steps or any(x['state']!='observed' or x['evidence'] not in ('target_attachment','target_text','user_confirmed') for x in steps)):
            raise ValueError('unproven confirmation')
        for x in steps:
            if x['state']=='observed' and x['evidence'] in ('none','os_input_count'): raise ValueError('injection is not receipt')
            if x['kind']=='text' and x['asset_id'] is not None: raise ValueError('text has asset')

results=[]
def case(name: str, callback, negative=False):
    try:
        callback()
        passed=not negative
        detail='accepted' if passed else 'incorrectly accepted'
    except Exception as e:
        passed=negative
        detail=type(e).__name__+': '+str(e).splitlines()[0]
    results.append({'name':name,'status':'PASS' if passed else 'FAIL','detail':detail})

def mutated(kind, modify):
    d=copy.deepcopy(read(f'fixtures/{kind}.valid.json'));modify(d);validate(kind,d)

def main():
    for kind in ('bundle','intent','attempt'):
        case('valid '+kind,lambda kind=kind:validate(kind,read(f'fixtures/{kind}.valid.json')))
    bad=[('extra path',lambda d:d.update(path='../../secret')),
         ('no automatic send',lambda d:d.update(auto_send=True)),
         ('reject boolean revision',lambda d:d.update(revision=True)),
         ('reject float revision',lambda d:d.update(revision=1.2)),
         ('reject unicode byte overflow',lambda d:d.update(text='图'*25000)),
         ('empty images and text',lambda d:d.update(assets=[],text='  \n')),
         ('bad asset hash',lambda d:d['assets'][0].update(sha256='x'*64)),
         ('reject source mime',lambda d:d['assets'][0].update(mime='image/svg+xml')),
         ('manifest stale',lambda d:d.update(text=d['text']+'changed')),
         ('image too big',lambda d:d['assets'][0].update(bytes=8388609)),
         ('duplicate asset id',lambda d:d['assets'].append(copy.deepcopy(d['assets'][0]))),
         ('more than six',lambda d:d.update(assets=d['assets']*7)),
         ('unexpected source layer',lambda d:d['assets'][0].update(source_json={})),
         ('reject zero dimension',lambda d:d['assets'][0].update(width=0))]
    for name,fn in bad:case(name,lambda fn=fn:mutated('bundle',fn),True)
    case('intent cannot contain keys',lambda:mutated('intent',lambda d:d.update(keys=['CTRL','V'])),True)
    case('intent cannot contain coordinates',lambda:mutated('intent',lambda d:d.update(x=20,y=100)),True)
    case('intent unknown trigger',lambda:mutated('intent',lambda d:d.update(trigger='network_reconnect')),True)
    case('injection not confirmation',lambda:mutated('attempt',lambda d:d['steps'][0].update(evidence='os_input_count')),True)
    case('unknown not confirmed',lambda:mutated('attempt',lambda d:d['steps'][0].update(state='unknown')),True)
    case('reference asset bytes',lambda:assert_asset())
    case('golden canonical bytes',lambda:assert_canonical())
    # Prove limits under otherwise-valid hashes rather than failing only on stale hash.
    def large_total():
        d=read('fixtures/bundle.valid.json');a=d['assets'][0];d['assets']=[dict(a,asset_id=f'00000000-0000-4000-8000-{i:012d}',bytes=8388608) for i in range(10,14)]
        d['manifest_hash']=digest(d);validate('bundle',d)
    case('total24MiB business rule',large_total,True)
    report={'kind':'reference_contract_checks','passed':sum(x['status']=='PASS' for x in results),'total':len(results),'product_acceptance':'NOT_RUN','results':results}
    out=ROOT/'evidence/contracts-report.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Contract checks: {report['passed']}/{report['total']}")
    if report['passed']!=report['total']:raise SystemExit(1)

def assert_asset():
    a=read('fixtures/bundle.valid.json')['assets'][0];data=(ROOT/'fixtures/sample.png').read_bytes()
    assert len(data)==a['bytes'] and hashlib.sha256(data).hexdigest()==a['sha256']

def assert_canonical():
    b=read('fixtures/bundle.valid.json');raw=(ROOT/'fixtures/manifest.canonical.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==b['manifest_hash']==digest(b)

if __name__=='__main__': main()
