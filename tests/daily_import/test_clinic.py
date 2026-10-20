import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pandas as pd
from pandas.testing import assert_frame_equal
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'daily_import'))
import clinic as m
import state
RAW=b'synthetic workbook bytes'
NAME='2026_Jan1_clinic.xlsx'
ENTRY={'file':NAME,'bytes':len(RAW),'sha256':m.digest(RAW)}
MAN={'format':1,'source_participant_uid':'a'*32,'count':1,'total_bytes':len(RAW),'files':[ENTRY]}


def archive(members):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as tar:
        for name,raw in members:
            item=tarfile.TarInfo(name)
            if raw is None:
                item.type=tarfile.SYMTYPE;item.linkname='/other';tar.addfile(item)
            else:
                item.size=len(raw);tar.addfile(item,io.BytesIO(raw))
    return output.getvalue()


@pytest.fixture
def tree(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/NAME).write_bytes(RAW)
    (source/'_Template_.xlsx').write_bytes(b'excluded')
    parent=tmp_path/'snapshots';parent.mkdir()
    monkeypatch.setattr(m.os,'chown',Mock())
    return source,parent


def test_export_receive_idempotent_roundtrip(tree,tmp_path):
    source,parent=tree;output=io.BytesIO()
    m.export({'source_folder':str(source),'manifest':MAN},output)
    path=tmp_path/'archive';path.write_bytes(output.getvalue())
    destination=m.receive(path,parent,MAN)
    assert m.verify_snapshot(destination,MAN)==destination/'workbooks'
    assert (destination/'workbooks'/NAME).read_bytes()==RAW
    assert m.receive(path,parent,MAN)==destination
    assert len(list(parent.iterdir()))==1


@pytest.mark.parametrize('name',['relative','../file.xlsx','x\\file.xlsx','x\x00.xlsx','file.csv','_Template_.xlsx'])
def test_bad_names(name):
    with pytest.raises(ValueError):m.filename(name)


def test_safe_and_read_bounds(tmp_path,monkeypatch):
    file=tmp_path/'file';file.write_bytes(RAW)
    assert m.read(file)==RAW
    for path in ('relative',tmp_path/'..'/'other'):
        with pytest.raises(ValueError):m.safe(path)
    link=tmp_path/'link';link.symlink_to(file)
    with pytest.raises(ValueError):m.safe(link)
    with pytest.raises(ValueError):m.read(file,1)
    empty=tmp_path/'empty';empty.touch()
    with pytest.raises(ValueError):m.identity(empty)



@pytest.mark.parametrize('change',[
    lambda x:x.update(format=True),lambda x:x.update(source_participant_uid='wrong'),
    lambda x:x.update(files=x['files']*2),lambda x:x['files'][0].update(sha256='wrong'),
    lambda x:x['files'][0].update(bytes=True),lambda x:x['files'][0].update(bytes=0),
    lambda x:x.update(count=0),lambda x:x.update(total_bytes=0),lambda x:x.update(files=[]),
])
def test_manifest_invalid(change):
    value=copy.deepcopy(MAN);change(value)
    with pytest.raises(ValueError):m.validate_manifest(value)


def test_source_changed_or_corrupt(tree,monkeypatch):
    source,parent=tree;config={'source_folder':source,'manifest':MAN}
    (source/NAME).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='payload'):m.export(config,io.BytesIO())
    (source/NAME).write_bytes(RAW)
    (source/'extra.xlsx').write_bytes(RAW)
    with pytest.raises(ValueError,match='inventory'):m.export(config,io.BytesIO())
    (source/'extra.xlsx').unlink()
    original=m.folder_files;calls=[0]
    def changed(folder):
        calls[0]+=1;return original(folder) if calls[0]==1 else set()
    monkeypatch.setattr(m,'folder_files',changed)
    with pytest.raises(ValueError,match='during'):m.export(config,io.BytesIO())


@pytest.mark.parametrize('members',[
    [('workbooks/'+NAME,None)],[('workbooks/'+NAME,b'')],[('bad',RAW)],
    [('workbooks/extra.xlsx',RAW)],[('workbooks/'+NAME,b'wrong')],
    [('workbooks/'+NAME,RAW),('workbooks/'+NAME,RAW)],
    [('clinic.manifest',b'{}'),('clinic.manifest',b'{}')],
    [('workbooks/'+NAME,RAW)],
    [('workbooks/'+NAME,RAW),('clinic.manifest',b'{}')],
])
def test_bad_archive_not_published(tree,tmp_path,members):
    source,parent=tree;path=tmp_path/'archive';path.write_bytes(archive(members))
    with pytest.raises(ValueError):m.receive(path,parent,MAN)
    assert list(parent.iterdir())==[]


def test_receiver_bounds(tree,tmp_path,monkeypatch):
    source,parent=tree;path=tmp_path/'archive'
    path.write_bytes(archive([('workbooks/'+NAME,RAW),('clinic.manifest',m.encoded(MAN))]))
    monkeypatch.setattr(m,'META_LIMIT',1)
    with pytest.raises(ValueError,match='manifest'):m.receive(path,parent,MAN)
    monkeypatch.setattr(m,'META_LIMIT',1024)
    # Bound the received stream separately from already validated configuration.
    original=m.validate_manifest
    def bounds(manifest):
        result=original(manifest);monkeypatch.setattr(m,'MAX_TOTAL',1);return result
    monkeypatch.setattr(m,'validate_manifest',bounds)
    with pytest.raises(ValueError,match='total'):m.receive(path,parent,MAN)


def test_snapshot_tamper(tree,tmp_path):
    source,parent=tree;path=tmp_path/'archive';out=io.BytesIO()
    m.export({'source_folder':source,'manifest':MAN},out);path.write_bytes(out.getvalue())
    snapshot=m.receive(path,parent,MAN)
    (snapshot/'COMPLETE').write_bytes(b'wrong')
    with pytest.raises(ValueError,match='manifest'):m.verify_snapshot(snapshot,MAN)
    (snapshot/'COMPLETE').write_text(m.digest(m.encoded(MAN)))
    (snapshot/'extra').touch()
    with pytest.raises(ValueError,match='files'):m.verify_snapshot(snapshot,MAN)
    (snapshot/'extra').unlink();(snapshot/'workbooks'/NAME).write_bytes(b'wrong')
    with pytest.raises(ValueError,match='payload'):m.verify_snapshot(snapshot,MAN)


def canonical():
    steps=pd.DataFrame({'file':[NAME,NAME],'sha256':[ENTRY['sha256']]*2,'setting':['clinic','home'],'pain':[3.0,None]})
    manifest=pd.DataFrame({'file':[NAME],'error':[''],'n_unparsed_prose':[1],'n_skipped_no_setting':[2]})
    saved={'steps':steps.copy(),'manifest':manifest.copy()}
    store=NS(load=Mock(return_value=saved),load_newest=Mock(return_value=(saved,{'signature_key':'signature'})),
        product_key=Mock(return_value='kind/person/signature'),signature_key=Mock(return_value='signature'),read_stamp=Mock(return_value={'same':True}))
    clinic=NS(parse_folder=Mock(return_value=(steps,manifest)),folder_signature=Mock(return_value=('signature',)),
        _cache_store=store,CLINIC_PAIN_KIND='clinic',ingest_and_store=Mock(return_value={'written':False,'store_key':'kind/person/signature'}),
        rated_steps=lambda frame:frame.dropna(subset=['pain']))
    return clinic


def test_canonical_acceptance_exact_frames_noop():
    clinic=canonical();command=Mock();person=NS(uid='b'*32)
    report=m.accept_canonical(person,'/received',MAN,clinic,command,assert_frame_equal)
    assert report=={'workbook_files':1,'parsed_steps':2,'rated_steps':1,'clinic_steps':1,'home_steps':1,
        'unparsed_prose':1,'skipped_no_setting':2,'canonical_store_key':'kind/person/signature','repeat_wrote':False}
    command.assert_called_once_with('ingest_clinic_sheets',participant=person.uid,folder='/received')
    clinic.parse_folder.assert_called_once_with('/received',keep_unrated=True)


@pytest.mark.parametrize('failure',['empty','missingfile','parseerror','badsha','unknownfile','nostore','wrongsteps','newest','retrywrite','retrystamp'])
def test_canonical_failure(failure):
    clinic=canonical();steps,manifest=clinic.parse_folder.return_value
    if failure=='empty':clinic.parse_folder.return_value=(steps.iloc[0:0],manifest)
    if failure=='missingfile':manifest.loc[0,'file']='other.xlsx'
    if failure=='parseerror':manifest.loc[0,'error']='parse failed'
    if failure=='badsha':steps.loc[0,'sha256']='wrong'
    if failure=='unknownfile':steps.loc[0,'file']='other.xlsx'
    if failure=='nostore':clinic._cache_store.load.return_value=None
    if failure=='wrongsteps':clinic._cache_store.load.return_value['steps'].loc[0,'pain']=3.00001
    if failure=='newest':clinic._cache_store.load_newest.return_value=(None,{})
    if failure=='retrywrite':clinic.ingest_and_store.return_value['written']=True
    if failure=='retrystamp':clinic._cache_store.read_stamp.side_effect=[{'before':True},{'after':True}]
    with pytest.raises((ValueError,AssertionError)):
        m.accept_canonical(NS(uid='b'*32),'/received',MAN,clinic,Mock(),assert_frame_equal)


def test_target_identity_and_wrapper(monkeypatch):
    clinic=canonical()
    db={'NAME':'target','USER':'target'};person=NS(uid='b'*32)
    for name,value in {
        'django':NS(setup=Mock()),'django.conf':NS(settings=NS(DATABASES={'default':db})),
        'django.core.management':NS(call_command=Mock()),'Server':NS(models=NS(Participant=NS(objects=NS(get=Mock(return_value=person))))),
        'modules.StimOptimizer':NS(clinic_pain=clinic),
    }.items():monkeypatch.setitem(sys.modules,name,value)
    monkeypatch.setenv('BRAVO_BUILD_REVISION','e'*40)
    monkeypatch.setattr(m,'verify_snapshot',Mock(return_value='/received'))
    config={'database_name':'target','database_user':'target','runtime_revision':'e'*40,'target_participant_uid':'b'*32,
        'target_institute_uid':'c'*32,'participant_name':'synthetic','snapshot':'/private/snapshot','manifest':MAN}
    report=m.accept_target(config)
    assert report['parsed_steps']==2
    assert m.verify_snapshot.call_count==2
    person.uid='a'*32
    with pytest.raises(ValueError,match='independent'):m.accept_target(config)
    db['NAME']='wrong'
    with pytest.raises(ValueError,match='runtime'):m.accept_target(config)


def source_config(tree,tmp_path):
    source,parent=tree
    output=io.BytesIO();m.export({'source_folder':source,'manifest':MAN},output)
    path=tmp_path/'initial.tar';path.write_bytes(output.getvalue())
    initial=m.receive(path,parent,MAN)
    return {'source_folder':str(source),'source_participant_uid':'a'*32,'snapshots':str(parent),
        'baseline_manifest':str(initial/'clinic.manifest'),'owner_uid':10001,'observation_seconds':1}


def reader(config):
    def call(request,output=None):
        out=output if output is not None else io.BytesIO()
        m.transport({**request,'config':config},out)
        return json.loads(out.getvalue()) if output is None else None
    return call


def test_source_snapshot_fullfolder_updated_noop_deletion(tree,tmp_path):
    config=source_config(tree,tmp_path);call=reader(config)
    first=m.refresh_source(config,call,lambda seconds:None)
    assert not first['published'] and not first['deferred']
    source,parent=tree
    assert m.current_manifest(config)==MAN
    # An edit produces a complete new folder snapshot, preserving the old one.
    (source/NAME).write_bytes(RAW+b' edit')
    (source/'2026_Jan2_home.xlsx').write_bytes(RAW+b' home')
    result=m.refresh_source(config,call,lambda seconds:None)
    assert result['published'] and result['workbook_files']==2
    current=m.current_manifest(config)
    snapshot=parent/result['manifest_sha256']
    assert {p.name for p in m.verify_snapshot(snapshot,current).glob('*.xlsx')} == {NAME, '2026_Jan2_home.xlsx'}
    assert (parent/m.digest(m.encoded(MAN))).exists()
    assert m.refresh_source(config,call,lambda seconds:None)['published'] is False
    (source/NAME).unlink()
    with pytest.raises(ValueError,match='disappeared'):
        m.refresh_source(config,call,lambda seconds:None)
    assert m.current_manifest(config)==current


def test_inventory_bounds_and_changed(tree,monkeypatch):
    source,parent=tree;config={'source_folder':source,'source_participant_uid':'a'*32}
    assert m.inventory(config)['manifest']==MAN
    with monkeypatch.context() as patch:
        patch.setattr(m,'MAX_FILES',0)
        with pytest.raises(ValueError,match='bounds'):m.inventory(config)
    original=m.folder_files;calls=[0]
    def changed(folder):
        calls[0]+=1;return original(folder) if calls[0]==1 else set()
    monkeypatch.setattr(m,'folder_files',changed)
    with pytest.raises(ValueError,match='changed'):m.inventory(config)
    with pytest.raises(ValueError,match='transport'):
        m.transport({'mode':'invalid'},io.BytesIO())


def test_source_defer_bad_interval_identity(tree,tmp_path):
    config=source_config(tree,tmp_path)
    call=reader(config);before=call({'mode':'inventory'});after=copy.deepcopy(before)
    after['identities'][NAME][-1]+=1
    requests=Mock(side_effect=[before,after])
    assert m.refresh_source(config,requests,lambda seconds:None)=={'deferred':True,'published':False,'workbook_files':1}
    for interval in (True,0,301):
        with pytest.raises(ValueError,match='interval'):
            m.refresh_source({**config,'observation_seconds':interval},call)
    with pytest.raises(ValueError,match='identity'):
        m.current_manifest({**config,'source_participant_uid':'b'*32})
    after['manifest']['source_participant_uid']='b'*32
    with pytest.raises(ValueError,match='observed'):
        m.refresh_source(config,Mock(side_effect=[after,after]),lambda seconds:None)


def test_source_disk_and_stream_bounds(tree,tmp_path,monkeypatch):
    config=source_config(tree,tmp_path);source,parent=tree
    (source/NAME).write_bytes(RAW+b' changed')
    monkeypatch.setattr(m.shutil,'disk_usage',lambda path:NS(free=0))
    with pytest.raises(ValueError,match='space'):
        m.refresh_source(config,reader(config),lambda seconds:None)
    monkeypatch.setattr(m.shutil,'disk_usage',lambda path:NS(free=10**12))
    call=reader(config)
    def too_large(request,output=None):
        if output is None:return call(request)
        output.seek(m.MAX_TOTAL+m.MAX_FILES*1024+m.META_LIMIT+1)
    with pytest.raises(ValueError,match='stream'):
        m.refresh_source(config,too_large,lambda seconds:None)
    assert not (parent/'CURRENT').exists()


def test_publish_pointer_failure_retains_prior(tree,tmp_path,monkeypatch):
    config=source_config(tree,tmp_path);source,parent=tree
    initial=parent/m.digest(m.encoded(MAN))
    m.publish_current(parent,initial)
    original=(parent/'CURRENT').read_bytes()
    monkeypatch.setattr(m.os,'replace',Mock(side_effect=OSError('interrupted')))
    with pytest.raises(OSError):m.publish_current(parent,initial)
    assert (parent/'CURRENT').read_bytes()==original
    assert not list(parent.glob('.pending-current-*'))


def test_target_refresh_revalidates_receipt_and_checks_before_ingest(tree,tmp_path,monkeypatch):
    import target_adapter
    config=source_config(tree,tmp_path);source,parent=tree
    m.refresh_source(config,reader(config),lambda seconds:None)
    receipts=tmp_path/'receipts';receipts.mkdir(mode=0o700)
    target={'source_participant_uid':'a'*32,'target_participant_uid':'b'*32,
            'clinic':{'snapshots':str(parent),'receipts':str(receipts)}}
    report={'canonical_store_key':'synthetic','runtime_revision':'e'*40,'manifest_sha256':m.digest(m.encoded(MAN))}
    accept=Mock(return_value=report);monkeypatch.setattr(m,'accept_target',accept)
    assert m.refresh_target(target)==report
    assert m.refresh_target(target)==report
    assert accept.call_count==2 # Existing receipt never masks a lost product.
    receipt=json.loads(next(receipts.iterdir()).read_text())
    assert receipt['target_participant_uid']=='b'*32
    receipts.chmod(0o500)
    with pytest.raises(ValueError,match='receipt'):m.refresh_target(target)
    assert accept.call_count==2
    receipts.chmod(0o700)
    with pytest.raises(ValueError,match='identity'):
        m.refresh_target({**target,'source_participant_uid':'c'*32})
