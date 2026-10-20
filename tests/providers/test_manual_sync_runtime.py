from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from test_optional_oauth_startup import isolated


@pytest.mark.parametrize("debug", [False, True])
def test_real_admin_login_csrf_binding_and_coalesced_mailbox(tmp_path, debug):
    isolated(tmp_path, '''
        import json,types,sys
        from pathlib import Path
        from django.core.management import call_command
        from django.test import Client,override_settings
        from django.middleware.csrf import _get_new_csrf_string
        from django.urls import path
        from Server import models
        from django.conf import settings
        settings.REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': [
            'Server.authentication.BRAVOAPIAuthentication',
            'rest_framework.authentication.BasicAuthentication',
            'Server.authentication.CsrfExemptSessionAuthentication' if DEBUG_MODE else 'rest_framework.authentication.SessionAuthentication']}
        from Server.APIs.ManualSync import ManualSync
        call_command('migrate',verbosity=0,interactive=False)
        admin=models.PlatformUser.create('admin@example.invalid','synthetic-only','Synthetic Admin')
        viewer=models.PlatformUser.objects.create_user(email='viewer@example.invalid',password='synthetic-only',user_name='Synthetic Viewer')
        admin.institute.join(viewer,'Member')
        person=models.Participant.objects.create(name='Synthetic',institute=admin.institute)
        other=models.Participant.objects.create(name='Other',institute=admin.institute)
        root=Path(os.environ['DATASERVER_PATH'])
        request_dir=root/'manual-request';request_dir.mkdir(mode=0o700)
        status_dir=root/'manual-status';status_dir.mkdir(mode=0o700)
        config={'request_directory':str(request_dir),'status_directory':str(status_dir),
            'target_participant_uid':person.uid,'target_institute_uid':admin.institute_id,
            'owner_uid':os.geteuid(),'source_mode':'retained_files','upstream_available':False}
        config_path=root/'manual-config.json';config_path.write_text(json.dumps(config));config_path.chmod(0o600)
        os.environ['BRAVO_MANUAL_SYNC_CONFIG_FILE']=str(config_path)
        urls=types.ModuleType('synthetic_manual_urls');urls.urlpatterns=[path('sync',ManualSync.as_view())];sys.modules[urls.__name__]=urls
        with override_settings(DEBUG=DEBUG_MODE,ALLOWED_HOSTS=['bravo.test'],ROOT_URLCONF=urls.__name__,
            MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware']):
            client=Client(enforce_csrf_checks=True,HTTP_HOST='bravo.test')
            payload={'ParticipantId':person.uid,'RequestType':'Start'}
            kwargs={'content_type':'application/json','secure':True,'HTTP_ORIGIN':'https://bravo.test'}
            assert client.post('/sync',payload,**kwargs).status_code==403
            import base64
            token=models.AuthenticationTokens.objects.create(user=admin)
            credentials=[{'HTTP_X_SECURE_API_KEY':admin.api_token},
                {'HTTP_X_SECURE_AUTH_TOKEN':token.token},
                {'HTTP_AUTHORIZATION':'Basic '+base64.b64encode(b'admin@example.invalid:synthetic-only').decode()}]
            for auth in credentials:
                for csrf_present in (False,True):
                    attempt=Client(enforce_csrf_checks=True,HTTP_HOST='bravo.test')
                    extra={**kwargs,**auth,'HTTP_ORIGIN':'https://wrong.test'}
                    if csrf_present:
                        value=_get_new_csrf_string();attempt.cookies['csrftoken']=value;extra['HTTP_X_CSRFTOKEN']=value
                    assert attempt.post('/sync',payload,**extra).status_code==403
                    extra['HTTP_ORIGIN']='https://bravo.test'
                    assert attempt.post('/sync',payload,**extra).status_code==403
                    assert not (request_dir/'request.json').exists()
            assert client.login(email=admin.email,password='synthetic-only')
            assert client.post('/sync',payload,**kwargs).status_code==403
            csrf=_get_new_csrf_string();client.cookies['csrftoken']=csrf;kwargs['HTTP_X_CSRFTOKEN']=csrf
            assert client.post('/sync',payload,**dict(kwargs,HTTP_ORIGIN='https://wrong.test')).status_code==403
            assert client.post('/sync',dict(payload,ParticipantId=other.uid),**kwargs).status_code==403
            first=client.post('/sync',payload,**kwargs)
            assert first.status_code==202, first.content
            second=client.post('/sync',payload,**kwargs)
            assert second.status_code==200 and second.json()['Job']['job_id']==first.json()['Job']['job_id']
            assert client.post('/sync',dict(payload,RequestType='Status'),**kwargs).json()['Job']['state']=='queued'
            assert set(json.loads((request_dir/'request.json').read_text()))=={'format','job_id','participant_uid','institute_uid','requester_uid','requested_at'}
            assert client.post('/sync',dict(payload,Command='forbidden'),**kwargs).status_code==400
            client.logout();assert client.login(email=viewer.email,password='synthetic-only')
            csrf=_get_new_csrf_string();client.cookies['csrftoken']=csrf;kwargs['HTTP_X_CSRFTOKEN']=csrf
            assert client.post('/sync',payload,**kwargs).status_code==403
            assert client.post('/sync',dict(payload,RequestType='Status'),**kwargs).status_code==403
    '''.replace('DEBUG_MODE', repr(debug)))
