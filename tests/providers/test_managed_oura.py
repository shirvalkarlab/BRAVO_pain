import contextlib
from datetime import date
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest
import requests

PATH = Path(__file__).resolve().parents[2] / 'BRAVO/modules/OURA/ManagedToken.py'
spec = importlib.util.spec_from_file_location('managed_oura', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
DIGEST = hashlib.sha256(b'account').hexdigest()


class Response:
    def __init__(self, data=None, status=200, content=b'json'):
        self.data, self.status_code, self.content = data, status, content
        self.closed=False
    def iter_content(self,chunk_size):
        if self.content!=b'json': yield self.content;return
        if isinstance(self.data, Exception): raise self.data
        yield json.dumps(self.data).encode()
    def close(self):self.closed=True


class Session:
    def __init__(self, *responses): self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, Exception): raise value
        return value


def transport(*responses):
    return m.Transport('synthetic-token', DIGEST, Session(*responses))


def write(path, payload):
    path.write_text(json.dumps(payload)); path.chmod(0o600)
    return str(path)


@pytest.fixture
def config(tmp_path, monkeypatch):
    token = write(tmp_path/'token.json', {'access_token':'synthetic-token'})
    item = {'institute_uid':'study','account_id_sha256':DIGEST,'token_file':token,
            'start_date':'2025-01-01','timezone':'UTC'}
    path = tmp_path/'config.json'
    write(path, {'schema_version':1,'participants':{'person':item}})
    monkeypatch.setenv(m.CONFIG_ENV,str(path))
    return types.SimpleNamespace(uid='person',institute_id='study'), item, path


def test_private_config_valid_and_binding(config):
    person, item, path = config
    assert m.binding(person)==(item,'synthetic-token')


@pytest.mark.parametrize('mode', ['relative','symlink','public','directory','missing','badjson','list','owner','none'])
def test_private_file_rejections(tmp_path, monkeypatch, mode):
    p=tmp_path/'secret';write(p, {})
    if mode=='none': p=None
    elif mode=='relative': p=Path('relative')
    elif mode=='symlink': target=p;p=tmp_path/'link';p.symlink_to(target)
    elif mode=='public':p.chmod(0o644)
    elif mode=='directory':p=tmp_path
    elif mode=='missing':p=tmp_path/'missing'
    elif mode=='badjson':p.write_text('{')
    elif mode=='list':write(p, [])
    elif mode=='owner':monkeypatch.setattr(m.os,'getuid',lambda:-5);old=Path.stat;monkeypatch.setattr(Path,'stat',lambda self,*a,**kw:types.SimpleNamespace(st_mode=0o100600,st_uid=9999))
    with pytest.raises(m.ManagedOuraError):m.private_json(p)


@pytest.mark.parametrize('change', ['missing_env','schema','participants','unbound','institute','digest','digesttype','date','zone','missingdate','future','ancient','tokenmissing','tokentype','tokennewline','tokenpadding'])
def test_binding_rejections(config,monkeypatch,change):
    person,item,path=config
    document=json.loads(path.read_text())
    if change=='missing_env':monkeypatch.delenv(m.CONFIG_ENV)
    elif change=='schema':document['schema_version']=2
    elif change=='participants':document['participants']=[]
    elif change=='unbound':document['participants']={}
    elif change=='institute':item['institute_uid']='other'
    elif change=='digest':item['account_id_sha256']='bad'
    elif change=='digesttype':item['account_id_sha256']=None
    elif change=='date':item['start_date']='bad'
    elif change=='zone':item['timezone']='Unknown/Zone'
    elif change=='missingdate':item.pop('start_date')
    elif change=='future':item['start_date']='2999-01-01'
    elif change=='ancient':item['start_date']='1900-01-01'
    else:
        values={'tokenmissing':None,'tokentype':4,'tokennewline':'ab\ncd','tokenpadding':' token '}
        write(Path(item['token_file']),{'access_token':values[change]})
    if change not in ('participants','unbound'):document['participants']={'person':item}
    write(path,document)
    with pytest.raises(m.ManagedOuraError):m.binding(person)


def test_identity_and_request_bounds():
    t=transport(Response({'id':'account'}));assert t.query('v2/usercollection/personal_info',{})=={'id':'account'}
    url,kwargs=t.session.calls[0]
    assert url=='https://api.ouraring.com/v2/usercollection/personal_info'
    assert kwargs['allow_redirects'] is False and kwargs['timeout']==(10,30)


@pytest.mark.parametrize('value', [{},[],{'id':3},{'id':'other'}])
def test_identity_failure(value):
    with pytest.raises(m.ManagedOuraError):transport(Response(value)).query('v2/usercollection/personal_info',{})


@pytest.mark.parametrize('value', [Response({},401),Response({},403),Response({},500),Response({},302),Response({},content=b'x'*(20*1024*1024+1)),Response(ValueError()),requests.Timeout(),Response([]),Response({}),Response({'data':['bad']}),Response({'data':[{}]}),Response({'data':[{'id':[]} ]})])
def test_bad_responses_preserve_sanitized_error(value):
    with pytest.raises(m.ManagedOuraError):transport(value).query('v2/usercollection/sleep',{})


def test_endpoint_rejected_and_session_default():
    t=m.Transport('token',DIGEST)
    with pytest.raises(m.ManagedOuraError):t.query('https://wrong.test',{})


def test_pagination_and_global_dedup():
    record={'id':'first','day':'2025-01-01'}
    t=transport(Response({'data':[record],'next_token':'next'}),Response({'data':[record,{'id':'second'}]}),Response({'data':[record]}))
    assert len(t.query('v2/usercollection/sleep',{} )['data'])==2
    assert t.session.calls[1][1]['params']['next_token']=='next'
    assert t.query('v2/usercollection/sleep',{})=={'data':[]}


@pytest.mark.parametrize('token', [3,'same'])
def test_bad_page_token(token):
    t=transport(Response({'data':[],'next_token':'same'}),Response({'data':[],'next_token':token}))
    with pytest.raises(m.ManagedOuraError):t.query('v2/usercollection/sleep',{})


def test_page_limit():
    t=transport(*(Response({'data':[],'next_token':str(n)}) for n in range(100)))
    with pytest.raises(m.ManagedOuraError,match='page limit'):t.query('v2/usercollection/sleep',{})


def test_conflicting_copies_and_heart_identity():
    t=transport(Response({'data':[{'id':'x','score':1},{'id':'x','score':2}]}))
    with pytest.raises(m.ManagedOuraError,match='conflicting'):t.query('v2/usercollection/sleep',{})
    item={'timestamp':'2025-01-01T00:00:00Z','source':'rest','bpm':60}
    t=transport(Response({'data':[item,item]}));assert t.query('v2/usercollection/heartrate',{})=={'data':[item]}


def fake_api(return_value=None,exc=None):
    class API:
        calls=[]
        def __init__(self,token):pass
        def verifyToken(self): self.query('v2/usercollection/personal_info',{})
        def getter(self,start,end):
            self.calls.append((start,end))
            if exc:raise exc
            return [] if return_value is None else return_value
    for method in m.STREAMS.values():setattr(API,method,API.getter)
    return API


def test_collect_all_seven_parsers_and_boundary():
    api=fake_api([{'observed':1}]);data,receipt=m.collect(api,'token',{'account_id_sha256':DIGEST,'start_date':'2025-01-01','timezone':'UTC'},today=date(2025,2,1),session=Session(Response({'id':'account'})))
    assert set(data)==set(m.STREAMS) and len(api.calls)==14
    assert all(len(rows)==2 for rows in data.values())
    assert api.calls[0][1]==api.calls[7][0]
    assert receipt['through_date']=='2025-02-01'


@pytest.mark.parametrize('value,exc',[(3,None),(None,ValueError('private response')),(None,m.ManagedOuraError('bounded'))])
def test_collect_failures(value,exc):
    with pytest.raises(m.ManagedOuraError):m.collect(fake_api(value,exc),'token',{'account_id_sha256':DIGEST,'start_date':'2025-01-01','timezone':'UTC'},today=date(2025,1,1),session=Session(Response({'id':'account'})))


def test_collect_current_date():
    today=date.today().isoformat()
    data,receipt=m.collect(fake_api(),'token',{'account_id_sha256':DIGEST,'start_date':today,'timezone':'UTC'},session=Session(Response({'id':'account'})))
    assert receipt['start_date']==today


@pytest.fixture
def storage(tmp_path,monkeypatch):
    monkeypatch.setenv('DATASERVER_PATH',str(tmp_path))
    state={'source':None,'writes':[]}
    class Source:
        def __init__(self,**kwargs):self.metadata={};self.pointer='';self.hashed='';self.__dict__.update(kwargs)
        def save(self):state['source']=self
        @staticmethod
        def find(**kwargs):return state['source']
    participant=types.SimpleNamespace(uid='person',pk='person')
    models=types.SimpleNamespace(SourceFile=Source,Participant=types.SimpleNamespace(objects=types.SimpleNamespace(select_for_update=lambda:types.SimpleNamespace(get=lambda **kw:participant))))
    def save(data,pointer):state['writes'].append(pointer);state.setdefault('files',{})[pointer]=data;Path(pointer).write_bytes(b'synthetic');return 'a'*64
    db=types.SimpleNamespace(saveSourceFile=save,loadSourceFile=lambda p,h:state['files'][p])
    monkeypatch.setitem(sys.modules,'Server',types.SimpleNamespace(models=models))
    monkeypatch.setitem(sys.modules,'modules',types.SimpleNamespace(Database=db))
    monkeypatch.setitem(sys.modules,'django.db',types.SimpleNamespace(transaction=types.SimpleNamespace(atomic=contextlib.nullcontext)))
    return state,participant,db


def test_publish_immutable_and_idempotent(storage):
    state,person,db=storage
    assert m.publish(person,{'Sleep':[]},{})['unchanged'] is False
    first=state['source'].pointer
    assert m.publish(person,{'Sleep':[]},{})['unchanged'] is True
    assert len(state['writes'])==1
    assert m.publish(person,{'Sleep':[1]},{})['unchanged'] is False
    assert state['source'].pointer!=first


@pytest.mark.parametrize('bad',[False,'bad'])
def test_publish_failed_file_keeps_old_pointer(storage,bad):
    state,person,db=storage;m.publish(person,{},{});old=state['source'].pointer
    db.saveSourceFile=lambda *args:bad
    with pytest.raises(m.ManagedOuraError):m.publish(person,{'new':[]},{})
    assert state['source'].pointer==old


def test_refresh_bound_dispatch_and_lock(config,storage,monkeypatch):
    person,item,path=config;state,_,db=storage;person.pk=person.uid
    device=types.SimpleNamespace(owner=person)
    monkeypatch.setitem(sys.modules,'modules.OURA.DataManager',types.SimpleNamespace(OuraRingAPI=fake_api()))
    monkeypatch.setattr(m,'collect',lambda *args:({'Sleep':[]},{'counts':{'Sleep':0}}))
    assert m.refresh(device)['unchanged'] is False
    import filelock
    with filelock.FileLock(str(Path(m.os.environ['DATASERVER_PATH'])/'recordings/person/.managed-oura-refresh.lock')):
        with pytest.raises(m.ManagedOuraError,match='already running'):m.refresh(device)


def test_heart_identity_missing_rejected():
    with pytest.raises(m.ManagedOuraError):transport(Response({'data':[{}]})).query('v2/usercollection/heartrate',{})


def test_publish_authenticated_readback(storage):
    state,person,db=storage;m.publish(person,{},{});old=state['source'].pointer
    db.loadSourceFile=lambda *args:{'wrong':[]}
    with pytest.raises(m.ManagedOuraError,match='Stored'):m.publish(person,{},{})
    with pytest.raises(m.ManagedOuraError,match='New'):m.publish(person,{'new':[]},{})
    assert state['source'].pointer==old


@pytest.mark.parametrize('error',[m.ManagedOuraError('sanitized'),RuntimeError('private details')])
def test_refresh_sanitizes_publication_failures(config,storage,monkeypatch,error):
    person,item,path=config;person.pk=person.uid
    monkeypatch.setitem(sys.modules,'modules.OURA.DataManager',types.SimpleNamespace(OuraRingAPI=fake_api()))
    def fail(*args):raise error
    monkeypatch.setattr(m,'collect',fail)
    with pytest.raises(m.ManagedOuraError) as caught:m.refresh(types.SimpleNamespace(owner=person))
    assert 'private details' not in str(caught.value)


@pytest.mark.parametrize('kind',['response','totalbytes','records','pages','seconds','streamseconds'])
def test_transport_global_bounds_and_close(monkeypatch,kind):
    response=Response({'data':[{'id':'a'}]})
    t=transport(response)
    if kind=='response':monkeypatch.setattr(m,'MAX_RESPONSE_BYTES',1)
    elif kind=='totalbytes':monkeypatch.setattr(m,'MAX_TOTAL_BYTES',1)
    elif kind=='records':monkeypatch.setattr(m,'MAX_TOTAL_RECORDS',0)
    elif kind=='pages':monkeypatch.setattr(m,'MAX_TOTAL_PAGES',0)
    elif kind=='seconds':t.started-=m.MAX_SECONDS+1
    else:
        clock=iter([t.started,t.started+m.MAX_SECONDS+1]);monkeypatch.setattr(m.time,'monotonic',lambda:next(clock))
    with pytest.raises(m.ManagedOuraError):t.query('v2/usercollection/sleep',{})
    assert response.closed==(kind not in ('pages','seconds'))


def test_durability_failure_preserves_pointer(storage,monkeypatch):
    state,person,db=storage;m.publish(person,{},{});old=state['source'].pointer
    def fail(fd):raise OSError('fsync failed')
    monkeypatch.setattr(m.os,'fsync',fail)
    with pytest.raises(OSError):m.publish(person,{'new':[]},{})
    assert state['source'].pointer==old


def test_owned_session_closed(monkeypatch):
    from unittest.mock import Mock
    session=Mock();monkeypatch.setattr(m.requests,'Session',lambda:session)
    transport=m.Transport('synthetic',DIGEST);transport.close()
    session.close.assert_called_once()


def test_content_identity_ignores_aliasing_and_mapping_order_but_preserves_exact_data():
    import numpy as np
    shared="not-interned-provider-text"
    one=[{'x':shared},{'x':shared}]
    two=json.loads(json.dumps(one))
    assert m.content_digest(one)==m.content_digest(two)
    assert m.content_digest({'b':True,'a':None})==m.content_digest({'a':None,'b':True})
    assert m.content_digest(np.float64(1))==m.content_digest(1.)
    assert m.content_digest([1])!=m.content_digest((1,))
    assert m.content_digest(0.)!=m.content_digest(-0.)
    assert m.content_digest(False)!=m.content_digest(True)
    assert m.content_digest([])!=m.content_digest({})
    a=np.array([[1.,0.],[float('nan'),2.]])
    assert m.content_digest(a)==m.content_digest(a.copy(order='F'))
    assert m.content_digest(a)!=m.content_digest(a.astype('float32'))


@pytest.mark.parametrize('kind',['objectarray','badkey','unsupported'])
def test_content_identity_rejects_unsupported_types(kind):
    import numpy as np
    value=np.array([object()],dtype=object) if kind=='objectarray' else {1:2} if kind=='badkey' else object()
    with pytest.raises(m.ManagedOuraError):m.content_digest(value)


def test_storage_root_must_exist(tmp_path,monkeypatch):
    root=tmp_path/'missing-root';monkeypatch.setenv('DATASERVER_PATH',str(root))
    with pytest.raises(m.ManagedOuraError,match='storage root'):m.recording_directory(types.SimpleNamespace(uid='person'))
    assert not root.exists()


def test_new_participant_directory_entries_are_durable(storage,monkeypatch):
    state,person,db=storage;opened=[];real_open=m.os.open
    def track(path,flags,*args,**kwargs):opened.append(Path(path));return real_open(path,flags,*args,**kwargs)
    monkeypatch.setattr(m.os,'open',track)
    m.publish(person,{},{});root=Path(m.os.environ['DATASERVER_PATH'])
    assert opened==[root/'recordings/person',root/'recordings',root]
