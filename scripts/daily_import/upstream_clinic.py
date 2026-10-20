"""Independent, bounded clinic reads; preserves historical inputs by stable Drive ID.

Caller owns the source-host lock and trusted configuration. Original Google
credentials/job/cache are read-only. Cloud freshness is distinct from retained
historical bytes. Canonical clinic snapshots retain their strict existing format.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import tarfile
import tempfile
import time

try:
    from . import clinic, state
except ImportError:
    import clinic, state

MIMES = {'application/vnd.google-apps.spreadsheet',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
META_MAX = 2 * 1024 * 1024
TRANSPORT_MAX = clinic.MAX_TOTAL + clinic.MAX_FILES * 2048 + META_MAX

# Executed only inside the configured existing source container. No Django,
# source ingestion, cache deserialization, token persistence or filesystem writes.
SOURCE_CODE = r'''
import contextlib,hashlib,importlib.util,io,json,resource,sys,tarfile
from pathlib import Path
resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
resource.setrlimit(resource.RLIMIT_CPU,(120,120))
path=Path('/usr/src/BRAVO/modules/StimOptimizer/google_sheets_client.py')
assert hashlib.sha256(path.read_bytes()).hexdigest()==request['client_sha256']
with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
 spec=importlib.util.spec_from_file_location('independent_clinic_read_client',path)
 g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
 assert g.folder_id()==g.DEFAULT_FOLDER_ID==request['folder_id'] and g.credential_source()=='user'
 credential=Path(g.token_file());credential_sha=hashlib.sha256(credential.read_bytes()).hexdigest()
 drive=g.GoogleClient()._drive
 if hasattr(drive._http,'http'):drive._http.http.timeout=30
 def listing():
  rows=[];page=None
  for unused in range(4):
   result=drive.files().list(q="'"+request['folder_id']+"' in parents and trashed=false",fields='nextPageToken,files(id,mimeType,name,modifiedTime,version)',pageSize=100,pageToken=page).execute(num_retries=0)
   rows.extend(result.get('files',[]));page=result.get('nextPageToken')
   if not page:break
  assert not page and len(rows)<=400
  return sorted(rows,key=lambda row:row['id'])
 rows=listing();payloads=[];total=0
 if request['mode']=='export':
  assert rows==request['observed_rows']
  indexed={row['id']:row for row in rows};assert len(indexed)==len(rows)
  assert len(request['files'])<=256
  seen=set()
  for item in request['files']:
   ident=item['id'];assert ident not in seen;seen.add(ident)
   row=indexed[ident]
   assert 'Testing' in row['name'] and not row['name'].startswith(('[Template]','OLD - '))
   assert row['mimeType'] in ('application/vnd.google-apps.spreadsheet','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
   name=row['name'] if row['name'].endswith('.xlsx') else row['name']+'.xlsx'
   assert item['file']==name and '/' not in name and chr(92) not in name and chr(0) not in name
   method=drive.files().export(fileId=ident,mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') if row['mimeType']=='application/vnd.google-apps.spreadsheet' else drive.files().get_media(fileId=ident)
   raw=method.execute(num_retries=0)
   assert isinstance(raw,bytes) and raw.startswith(b'PK') and 0<len(raw)<=32*1024**2
   total+=len(raw);assert total<=256*1024**2
   payloads.append((name,raw))
  assert listing()==rows
 assert hashlib.sha256(credential.read_bytes()).hexdigest()==credential_sha
if request['mode']=='metadata':
 print(json.dumps({'folder_id':request['folder_id'],'rows':rows,'credential_unchanged':True},sort_keys=True))
elif request['mode']=='export':
 with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
  for name,raw in payloads:
   info=tarfile.TarInfo('workbooks/'+name);info.size=len(raw);info.mode=0o600;info.mtime=0
   archive.addfile(info,io.BytesIO(raw))
else:raise ValueError('invalid upstream mode')
'''


def validate_config(config):
    if config.get('enabled') is not True:
        raise ValueError('upstream clinic is not enabled')
    if not re.fullmatch('[A-Za-z0-9_.-]+', config['source_container']) or config['workdir'] != '/usr/src/BRAVO':
        raise ValueError('invalid source container identity')
    if not re.fullmatch('[A-Za-z0-9_-]+', config['folder_id']) or not re.fullmatch('[0-9a-f]{64}', config['client_sha256']):
        raise ValueError('invalid fixed upstream identity')
    state.uid(config['source_participant_uid'])
    if type(config['owner_uid']) is not int or config['owner_uid'] != 10001:
        raise ValueError('unexpected clinic storage owner')
    paths = [state.safe_path(config[key]) for key in ('snapshots','provenance_directory','baseline_manifest','baseline_provenance')]
    if paths[0] == paths[1] or paths[0].is_relative_to(paths[1]) or paths[1].is_relative_to(paths[0]):
        raise ValueError('provenance must be separate from strict snapshots')
    if not paths[0].is_dir() or not paths[1].is_dir():
        raise ValueError('precreated private output directories required')
    return config


def source_call(config, request, output=None):
    request = {**request, 'folder_id':config['folder_id'],'client_sha256':config['client_sha256']}
    raw = ('request='+repr(request)+'\n'+SOURCE_CODE).encode()
    if len(raw) > META_MAX:
        raise ValueError('upstream request exceeds bound')
    def bound():
        resource.setrlimit(resource.RLIMIT_FSIZE,(TRANSPORT_MAX,TRANSPORT_MAX))
    with tempfile.TemporaryFile(dir=config['provenance_directory']) as captured:
        process = subprocess.run(['docker','exec','-i','-w',config['workdir'],'-e','PYTHONDONTWRITEBYTECODE=1',config['source_container'],
                                  'timeout','--kill-after=10','600','python3','-'],input=raw,stdout=captured,stderr=subprocess.DEVNULL,timeout=620,preexec_fn=bound)
        if process.returncode or captured.tell() > TRANSPORT_MAX:
            raise ValueError('clinic upstream read failed or exceeded bounds')
        captured.seek(0)
        if output is not None:
            shutil.copyfileobj(captured,output)
            return None
        payload=captured.read(META_MAX+1)
        if len(payload)>META_MAX:
            raise ValueError('clinic metadata exceeds bound')
        return json.loads(payload)


def cloud_inventory(response, folder_id):
    if response.get('folder_id') != folder_id or response.get('credential_unchanged') is not True:
        raise ValueError('cloud scope or credential guard differs')
    rows=response['rows']
    if not isinstance(rows,list) or len(rows)>400:
        raise ValueError('cloud inventory exceeds bound')
    seen=set();files={};names=set()
    for row in rows:
        if not isinstance(row.get('id'),str) or not re.fullmatch('[A-Za-z0-9_-]+',row['id']) or row['id'] in seen or not isinstance(row.get('name'),str):
            raise ValueError('invalid/duplicate cloud identity')
        seen.add(row['id'])
        if 'Testing' not in row['name'] or row['name'].startswith(('[Template]','OLD - ')) or row.get('mimeType') not in MIMES:
            continue
        name=clinic.filename(row['name'] if row['name'].endswith('.xlsx') else row['name']+'.xlsx')
        if name.casefold() in names or not isinstance(row.get('modifiedTime'),str) or not row['modifiedTime'] or not isinstance(row.get('version'),str) or not row['version'].isdigit():
            raise ValueError('ambiguous cloud filename/version')
        names.add(name.casefold());files[row['id']]={**row,'file':name}
    if not 0<len(files)<=clinic.MAX_FILES:
        raise ValueError('empty/oversized eligible clinic inventory')
    return files


def validate_provenance(provenance, manifest, config):
    entries=clinic.validate_manifest(manifest)
    if provenance.get('format')!=1 or provenance.get('folder_id')!=config['folder_id'] or provenance.get('source_participant_uid')!=config['source_participant_uid'] or manifest['source_participant_uid']!=config['source_participant_uid']:
        raise ValueError('clinic provenance identity differs')
    files={};names=set()
    for item in provenance['files']:
        name=clinic.filename(item['file']);ident=item['id']
        if name in names or ident in files or not re.fullmatch('[A-Za-z0-9_-]+',ident) or name not in entries:
            raise ValueError('ambiguous clinic provenance mapping')
        if item['sha256']!=entries[name]['sha256'] or item['bytes']!=entries[name]['bytes'] or item['mimeType'] not in MIMES:
            raise ValueError('clinic provenance bytes differ')
        files[ident]=item;names.add(name)
    if names!=set(entries):
        raise ValueError('incomplete clinic provenance')
    return files


def previous_state(config):
    root=state.safe_path(config['provenance_directory']);current=root/'CURRENT.json'
    if current.exists():
        provenance=json.loads(clinic.read(current,META_MAX))
        snapshot=state.safe_path(config['snapshots'])/state.digest(provenance['manifest_sha256'])
        manifest=json.loads(clinic.read(snapshot/'clinic.manifest',clinic.META_LIMIT))
    else:
        baseline=state.safe_path(config['baseline_manifest']);manifest=json.loads(clinic.read(baseline,clinic.META_LIMIT))
        provenance=json.loads(clinic.read(config['baseline_provenance'],META_MAX))
        parent=baseline.parent
        snapshot=parent/state.sha(state.encoded(manifest)) if baseline.name=='CURRENT' else parent
    mapping=validate_provenance(provenance,manifest,config)
    workbooks=clinic.verify_snapshot(snapshot,manifest)
    return mapping,workbooks


def plan_files(previous, cloud):
    """One current filename per Drive ID; missing IDs retain historical bytes."""
    plan=[];names=set()
    for ident in sorted(set(previous)|set(cloud)):
        old=previous.get(ident);live=cloud.get(ident)
        if live:
            same=old is not None and old.get('version') is not None and all(old.get(k)==live.get(k) for k in ('modifiedTime','version','mimeType'))
            item={**live,'status':'cloud_current','download':not same,'previous_file':old['file'] if old else None}
        else:
            item={**old,'status':'retained_not_fresh','download':False,'previous_file':old['file']}
        if item['file'].casefold() in names:
            raise ValueError('retained/current clinic filename collision')
        names.add(item['file'].casefold());plan.append(item)
    if len(plan)>clinic.MAX_FILES:
        raise ValueError('combined clinic history exceeds bound')
    return plan


def read_downloads(stream, wanted):
    result={};total=0
    with tarfile.open(fileobj=stream,mode='r|') as archive:
        for member in archive:
            if not member.isfile() or not member.name.startswith('workbooks/') or not 0<member.size<=clinic.MAX_FILE:
                raise ValueError('unsafe cloud export member')
            name=clinic.filename(member.name[len('workbooks/'):])
            if name not in wanted or name in result:
                raise ValueError('unexpected cloud export workbook')
            raw=archive.extractfile(member).read();total+=len(raw)
            if len(raw)!=member.size or not raw.startswith(b'PK') or total>clinic.MAX_TOTAL:
                raise ValueError('invalid/bounded cloud workbook bytes')
            result[name]=raw
    if set(result)!=set(wanted):
        raise ValueError('incomplete cloud export')
    return result


def refresh(config, call=None):
    """Run under source lock. Returns no credentials, IDs, names or clinical text."""
    try:
        validate_config(config)
        call=call or (lambda request,output=None:source_call(config,request,output))
        previous,workbooks=previous_state(config)
        observed=call({'mode':'metadata'});cloud=cloud_inventory(observed,config['folder_id'])
        plan=plan_files(previous,cloud);wanted={item['file']:item for item in plan if item['download']}
        downloaded={}
        if wanted:
            with tempfile.TemporaryFile(dir=config['provenance_directory']) as stream:
                call({'mode':'export','observed_rows':observed['rows'],'files':[{'id':item['id'],'file':name} for name,item in sorted(wanted.items())]},stream)
                if stream.tell()>TRANSPORT_MAX:raise ValueError('export stream exceeds bound')
                stream.seek(0);downloaded=read_downloads(stream,wanted)
        # Recheck even a no-download run; no fresh status is published after drift.
        if call({'mode':'metadata'})!=observed:
            return {'status':'failed','deferred':True,'reason':'upstream_changed','retained_files':0,'fresh_files':0}
        payloads={};provenance=[];total=0
        for item in plan:
            if item['download']:raw=downloaded[item['file']]
            else:
                old=previous[item['id']];raw=clinic.read(workbooks/old['file']);clinic.verify_raw(raw,old)
            total+=len(raw)
            if total>clinic.MAX_TOTAL:raise ValueError('combined clinic bytes exceed bound')
            entry={'file':item['file'],'bytes':len(raw),'sha256':state.sha(raw)}
            payloads[item['file']]=raw
            provenance.append({**{k:item[k] for k in ('id','mimeType','modifiedTime')},'version':item.get('version'),**entry,'status':item['status']})
        manifest={'format':1,'source_participant_uid':config['source_participant_uid'],'files':sorted([{'file':p['file'],'bytes':p['bytes'],'sha256':p['sha256']} for p in provenance],key=lambda x:x['file']),'count':len(provenance),'total_bytes':total}
        clinic.validate_manifest(manifest);digest=state.sha(state.encoded(manifest));root=state.safe_path(config['snapshots'])
        if shutil.disk_usage(root).free<2*clinic.MAX_TOTAL+META_MAX:raise ValueError('insufficient clinic snapshot space')
        with tempfile.NamedTemporaryFile(dir=config['provenance_directory']) as stream:
            with tarfile.open(fileobj=stream,mode='w|') as archive:
                for name,raw in sorted(payloads.items()):
                    info=tarfile.TarInfo('workbooks/'+name);info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
                raw=state.encoded(manifest);info=tarfile.TarInfo('clinic.manifest');info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
            stream.flush();snapshot=clinic.receive(stream.name,root,manifest,config['owner_uid'])
        record={'format':1,'folder_id':config['folder_id'],'source_participant_uid':config['source_participant_uid'],'manifest_sha256':digest,'checked_at_unix':time.time(),'files':provenance,'fresh_files':len(cloud),'retained_files':len(plan)-len(cloud),'downloaded_files':len(wanted)}
        private=state.safe_path(config['provenance_directory']);record_sha=state.sha(state.encoded(record))
        state.atomic_json(private/(record_sha+'.json'),record)
        # Provenance first: if publication is interrupted, next run repairs CURRENT
        # from a fully verified snapshot, never from partially downloaded bytes.
        state.atomic_json(private/'CURRENT.json',record)
        clinic.publish_current(root,snapshot)
        return {'status':'success','deferred':False,'retained_files':record['retained_files'],'fresh_files':len(cloud),'downloaded_files':len(wanted),'manifest_sha256':digest,'provenance_sha256':record_sha}
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError,tarfile.TarError):
        return {'status':'failed','deferred':False,'reason':'upstream_clinic_failed','retained_files':0,'fresh_files':0}
