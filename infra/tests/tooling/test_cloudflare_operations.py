"""A native non-no-change plan, a source race or a state race must never reach apply."""
from pathlib import Path
import json
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tofu/cloudflare'))
import operations as ops

CIPHER=b'{"encryption_version":"v0","encrypted_data":"test-only"}'


@pytest.fixture
def operator(monkeypatch,tmp_path):
    calls=[]
    address='cloudflare_dns_record.team'
    expected={address:{'resource_id':'record-id','import_id':'zone/record-id'}}
    document={'format_version':'1.2','terraform_version':'1.12.5','errored':False,
      'resource_changes':[{'address':address,'mode':'managed','provider_name':'registry.opentofu.org/cloudflare/cloudflare',
        'change':{'actions':['no-op'],'after_unknown':{},'before':{'id':'record-id'},'after':{'id':'record-id'}}}]}
    class Storage:
        reads=0
        race=False
        def __init__(self,*args): pass
        def request(self,*args,**kwargs):
            type(self).reads+=1
            return CIPHER+b' ' if self.race and self.reads>1 else CIPHER
    def command(args,directory=None,env=None,data=None,codes=(0,)):
        calls.append(args)
        if args[1]=='plan':
            output=next(item[5:] for item in args if item.startswith('-out='))
            Path(output).write_bytes(b'test-only-native-encrypted-binary')
        return subprocess.CompletedProcess(args,0,json.dumps(document).encode() if args[1]=='show' else b'',b'')
    monkeypatch.setattr(ops,'secret_set',lambda:{})
    monkeypatch.setattr(ops,'environment',lambda *args:{key:'test-only' for key in ['AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN']})
    monkeypatch.setattr(ops,'prepare',lambda directory:expected)
    monkeypatch.setattr(ops,'initialize',lambda *args:None)
    monkeypatch.setattr(ops,'run',command)
    monkeypatch.setattr(ops,'S3',Storage)
    monkeypatch.setattr(ops,'input_digest',lambda root:'d'*64)
    monkeypatch.setattr(ops,'take_snapshot',lambda *args,**kwargs:{'sha256':'e'*64})
    monkeypatch.setattr(ops,'EVIDENCE',tmp_path)
    return calls,document,Storage


def test_guarded_import_and_no_change_followup_are_idempotent(operator):
    calls,_,_=operator
    ops.plan({},adopt=True)
    assert sum(command[1]=='apply' for command in calls)==1
    assert sum(command[1]=='plan' for command in calls)==2
    calls.clear();ops.plan({})
    assert not any(command[1]=='apply' for command in calls)


@pytest.mark.parametrize('actions',[['create'],['update'],['delete'],['delete','create']])
def test_provider_mutation_cannot_reach_apply(operator,actions):
    calls,document,_=operator
    document['resource_changes'][0]['change']['actions']=actions
    with pytest.raises(ops.OperationError): ops.plan({},adopt=True)
    assert not any(command[1]=='apply' for command in calls)


def test_state_race_cannot_reach_import_apply(operator):
    calls,_,storage=operator;storage.race=True
    with pytest.raises(ops.OperationError,match='state changed'): ops.plan({},adopt=True)
    assert not any(command[1]=='apply' for command in calls)


def test_source_race_cannot_reach_apply(operator,monkeypatch):
    calls,_,_=operator
    digests=iter(['d'*64,'e'*64])
    monkeypatch.setattr(ops,'input_digest',lambda root:next(digests))
    with pytest.raises(ops.OperationError,match='inputs changed'): ops.plan({},adopt=True)
    assert not any(command[1]=='apply' for command in calls)


def test_failed_command_never_discloses_captured_values(monkeypatch):
    monkeypatch.setattr(ops.subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args,1,b'test-only-secret-value',b'test-only-secret-value'))
    with pytest.raises(ops.OperationError) as result: ops.run(['tofu','apply'])
    assert 'test-only-secret-value' not in str(result.value)


@pytest.mark.parametrize('key,value',[('backend_bucket','foreign'),('backend_key','foreign.tfstate'),
    ('snapshot_key','recovery/cloudflare.sops.yml'),('sha256','invalid'),('expected_primary_absent',False),('schema_version',2)])
def test_recovery_request_never_overwrites_or_uses_unreviewed_object(key,value):
    request={'schema_version':1,'snapshot_key':'snapshots/20260913T000000000000Z-'+'a'*64+'.tfstate',
       'sha256':'a'*64,'backend_bucket':'dholbeat-tfstate','backend_key':'cloudflare/production.tfstate','expected_primary_absent':True}
    config={'bucket':request['backend_bucket'],'key':request['backend_key']}
    ops.validate_recovery_request(request,config)
    with pytest.raises(ops.OperationError): ops.validate_recovery_request({**request,key:value},config)


@pytest.mark.parametrize('scenario',['initial','immutable-missing','public-root','wrong-root-id'])
def test_bootstrap_is_two_stage_and_never_replaces_pinned_roots(monkeypatch,tmp_path,scenario):
    import yaml
    config=yaml.safe_load((ops.PACKAGE/'bootstrap.yml').read_text())
    backend=config['backend']
    if scenario=='initial':
        backend['authority']='initial-bootstrap';backend['bucket_id']=None;backend['recovery_bucket_id']=None
    (tmp_path/'bootstrap.yml').write_text(yaml.safe_dump(config))
    monkeypatch.setattr(ops,'PACKAGE',tmp_path)
    monkeypatch.setattr(ops,'EVIDENCE',tmp_path)
    calls=[]
    class API:
        def request(self,method,path,body=None):
            calls.append((method,path))
            if path.endswith('/r2/buckets'): return {'buckets':[]} if method=='GET' else {}
            if path.endswith('/domains/managed'):
                name=path.split('/')[-3]
                identifier='test-only-new-id' if scenario in {'initial','wrong-root-id'} else backend['bucket_id']
                return {'enabled':scenario=='public-root','bucketId':identifier}
            if path.endswith('/domains/custom'): return {'domains':[]}
            if path.endswith('/lifecycle'): return {'rules':[]}
            return {}
    if scenario in {'public-root','wrong-root-id'}:
        original=API.request
        def existing(self,method,path,body=None):
            if method=='GET' and path.endswith('/r2/buckets'):
                calls.append((method,path));return {'buckets':[{'name':backend['bucket']},{'name':backend['recovery_bucket']}]}
            return original(self,method,path,body)
        monkeypatch.setattr(API,'request',existing)
    monkeypatch.setattr(ops,'root_api',lambda inputs:API())
    if scenario=='initial':
        ops.bootstrap({});assert sum(method=='POST' for method,_ in calls)==2
        assert json.loads((tmp_path/'bootstrap-provision.json').read_text())['state_initialized'] is False
    else:
        with pytest.raises(ops.OperationError): ops.bootstrap({})
        assert not any(method=='POST' for method,_ in calls)
