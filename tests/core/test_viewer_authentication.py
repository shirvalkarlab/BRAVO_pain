"""Auth adapter branches; session/CSRF/route isolation is tested against Django separately."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

from cryptography.fernet import Fernet
from django.conf import settings
import django
import pytest

APP = Path(__file__).resolve().parents[2] / 'BRAVO'
sys.path.insert(0, str(APP));sys.path.append(str(APP / 'modules'))
os.environ.setdefault('DATASERVER_ENCRYPTION', Fernet.generate_key().decode())
os.environ.setdefault('DATASERVER_HASHKEY', 'synthetic-only')
if not settings.configured:
    settings.configure(SECRET_KEY='synthetic',INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes','Server'],DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}},AUTH_USER_MODEL='Server.PlatformUser')
django.setup()
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from Server import authentication as auth


def user(viewer=False,active=1):
    return NS(configuration={'SharedReadOnly':viewer},is_authenticated=True,is_active=active)


@pytest.mark.parametrize('who',[None,user(),user(True)])
def test_session_adapter(monkeypatch,who):
    result = None if who is None else (who,None)
    monkeypatch.setattr(auth.SessionAuthentication,'authenticate',lambda *_:result)
    req=NS(path='/api/queryProfile',method='POST',data={},query_params={})
    assert auth.ReadOnlySessionAuthentication().authenticate(req)==result
    req.path='/api/deleteParticipantInformation'
    if who is not None and who.configuration['SharedReadOnly']:
        with pytest.raises(PermissionDenied): auth.ReadOnlySessionAuthentication().authenticate(req)
    else:
        assert auth.ReadOnlySessionAuthentication().authenticate(req)==result
    assert auth.CsrfExemptSessionAuthentication().enforce_csrf(req) is None


@pytest.mark.parametrize('who',[None,user(),user(True)])
def test_basic_adapter(monkeypatch,who):
    result=None if who is None else (who,None)
    monkeypatch.setattr(auth.BasicAuthentication,'authenticate',lambda *_:result)
    if who is not None and who.configuration['SharedReadOnly']:
        with pytest.raises(AuthenticationFailed):auth.ReadOnlyBasicAuthentication().authenticate(NS())
    else:
        assert auth.ReadOnlyBasicAuthentication().authenticate(NS())==result


@pytest.mark.parametrize('mode',['key','token'])
@pytest.mark.parametrize('state',['absent','inactive','viewer','owner'])
def test_api_identity_denial_before_session_fallback(monkeypatch,mode,state):
    who=None if state=='absent' else user(state=='viewer',int(state!='inactive'))
    if mode=='key':
        monkeypatch.setattr(auth.models.PlatformUser,'find',lambda **_:who)
        headers={'X-Secure-API-Key':'synthetic'}
    else:
        manager=Mock();manager.filter.return_value.first.return_value=None if who is None else NS(user=who)
        monkeypatch.setattr(auth.models.AuthenticationTokens,'objects',manager)
        headers={'X-Secure-Auth-Token':'synthetic'}
    req=NS(headers=headers)
    if state=='viewer':
        with pytest.raises(AuthenticationFailed):auth.BRAVOAPIAuthentication().authenticate(req)
        assert not hasattr(req,'csrf_processing_done')
    elif state=='owner':
        assert auth.BRAVOAPIAuthentication().authenticate(req)==(who,None)
        assert req.csrf_processing_done and who.api_access
    else:
        assert auth.BRAVOAPIAuthentication().authenticate(req) is None
    assert auth.BRAVOAPIAuthentication().authenticate(NS(headers={})) is None


def test_legacy_csrf_middleware_passthrough(monkeypatch):
    middleware=auth.BRAVOCSRFViewMiddleware(lambda _:None)
    assert middleware.process_view(NS(headers={'X-Secure-API-Key':'synthetic'}),None,(),{}) is None
    monkeypatch.setattr(auth.CsrfViewMiddleware,'process_view',lambda *a,**kw:'checked')
    assert middleware.process_view(NS(headers={}),None,(),{})=='checked'


def test_only_the_actual_read_only_spa_handler_is_exempt():
    from Server.views import Homepage, StaticProxy
    viewer=user(True)
    for view, allowed in ((Homepage(),True),(StaticProxy(),False),(NS(),False),(None,False)):
        request=NS(path='/database',method='GET',data={},query_params={},parser_context={'view':view})
        if allowed:
            auth.enforce_read_only(request,viewer)
        else:
            with pytest.raises(PermissionDenied):auth.enforce_read_only(request,viewer)
    request=NS(path='/api/unknown',method='GET',data={},query_params={},parser_context={'view':Homepage()})
    with pytest.raises(PermissionDenied):auth.enforce_read_only(request,viewer)
