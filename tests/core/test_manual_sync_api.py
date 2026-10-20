"""Endpoint decision tests; real production auth/CSRF is separately exercised in runtime tests."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock
import tempfile
from cryptography.fernet import Fernet
import django
from django.conf import settings
import pytest
APP=Path(__file__).resolve().parents[2]/'BRAVO'
sys.path.insert(0,str(APP));sys.path.append(str(APP/'modules'))
_storage=tempfile.TemporaryDirectory(prefix='manual-sync-api-test-')
os.environ['DATASERVER_PATH']=_storage.name+os.sep
os.environ['DATASERVER_ENCRYPTION']=Fernet.generate_key().decode()
os.environ['DATASERVER_HASHKEY']='synthetic-only'
if not settings.configured:
    settings.configure(SECRET_KEY='synthetic',DEBUG=False,INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes','Server'],DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}},AUTH_USER_MODEL='Server.PlatformUser',DEFAULT_AUTO_FIELD='django.db.models.BigAutoField')
django.setup()
from Server.APIs import ManualSync as api

@pytest.fixture
def setup(monkeypatch):
    person=NS(uid='a'*32,institute_id='b'*32,institute=NS())
    relation=NS(permission={'Position':'Admin'})
    config={'target_participant_uid':person.uid,'target_institute_uid':person.institute_id,'source_mode':'retained_files','upstream_available':False}
    monkeypatch.setattr(api.Database,'checkAccessPermission',Mock(return_value=True))
    monkeypatch.setattr(api.models.Participant,'find',Mock(return_value=person))
    monkeypatch.setattr(api.models.InstituteRel,'find',Mock(return_value=relation))
    monkeypatch.setattr(api.protocol,'load_config',Mock(return_value=config))
    monkeypatch.setattr(api.protocol,'status',Mock(return_value={'state':'queued'}))
    monkeypatch.setattr(api.protocol,'submit',Mock(return_value=({'state':'queued'},True)))
    return NS(person=person,relation=relation,config=config)

def request(data=None):
    r=NS(user=NS(uid='c'*32,configuration={}),data=data if data is not None else {'ParticipantId':'a'*32,'RequestType':'Status'})
    return api.ManualSync.post.__wrapped__(api.ManualSync(),r)

def test_status_start_and_coalescing(setup):
    response=request();assert response.status_code==200 and response.data['CanSync'] is True and response.data['Sources']['Mode']=='retained_files'
    assert request({'ParticipantId':'a'*32,'RequestType':'Start'}).status_code==202
    api.protocol.submit.return_value=({'state':'running'},False)
    assert request({'ParticipantId':'a'*32,'RequestType':'Start'}).status_code==200

@pytest.mark.parametrize('data',[[],{}, {'ParticipantId':'wrong','RequestType':'Status'}, {'ParticipantId':'a'*32,'RequestType':'other'}, {'ParticipantId':'a'*32,'RequestType':'Start','Command':'forbidden'}])
def test_malformed_denied(setup,data):
    assert request(data).status_code==400
    assert not api.protocol.submit.called

@pytest.mark.parametrize('case',['access','missing','institute','relation','member','participant_binding','institute_binding'])
def test_unauthorized_denied_before_submit(setup,case):
    s=setup
    if case=='access':api.Database.checkAccessPermission.return_value=False
    if case=='missing':api.models.Participant.find.return_value=None
    if case=='institute':s.person.institute_id=None
    if case=='relation':api.models.InstituteRel.find.return_value=None
    if case=='member':s.relation.permission['Position']='Member'
    if case=='participant_binding':s.config['target_participant_uid']='d'*32
    if case=='institute_binding':s.config['target_institute_uid']='d'*32
    assert request({'ParticipantId':'a'*32,'RequestType':'Start'}).status_code==403
    assert not api.protocol.submit.called

def test_failure_is_sanitized(setup):
    api.protocol.load_config.side_effect=OSError('secret private location')
    response=request();assert response.status_code==503 and response.data['Available'] is False
    assert 'secret' not in str(response.data)
