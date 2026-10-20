"""Shared viewer authorization with real Django sessions and isolated storage."""
from test_optional_oauth_startup import isolated


def test_shared_viewer_sessions_and_fail_closed_routes(tmp_path):
    isolated(tmp_path, '''
        import base64, json
        from django.core.management import call_command
        from django.test import Client, override_settings
        from django.middleware.csrf import _get_new_csrf_string
        from django.urls import get_resolver, URLResolver
        from Server import models
        from django.conf import settings
        settings.REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES': [
            'Server.authentication.BRAVOAPIAuthentication',
            'Server.authentication.ReadOnlyBasicAuthentication',
            'Server.authentication.ReadOnlySessionAuthentication']}
        call_command('migrate', verbosity=0, interactive=False)
        owner = models.PlatformUser.create('owner@example.invalid', 'synthetic-password', 'Owner')
        viewer = models.PlatformUser.objects.create_user(email='shirvalkarlab', password='synthetic-viewer', user_name='Lab viewer')
        viewer.configuration = {'SharedReadOnly': True}
        viewer.institute = owner.institute
        viewer.save()
        owner.institute.join(viewer, 'Viewer')
        person = models.Participant.objects.create(name='Synthetic participant', institute=owner.institute)
        outside = models.Institute.create('Outside')
        hidden = models.Participant.objects.create(name='Not shared', institute=outside)
        study = models.Study.create('Study')
        models.StudyRel.objects.create(study=study, member=viewer, permission={'Position': 'Viewer'})
        assert viewer.get_info()['ReadOnly'] is True
        assert 'InviteCode' not in viewer.get_info()['Studies'][0]
        assert 'Members' not in viewer.get_info()['Studies'][0]
        assert owner.institute.has_permission(viewer)
        for permission in ('Upload', 'Delete', 'Edit', 'AddEvent'):
            assert not owner.institute.has_permission(viewer, permission)
        def routes(patterns):
            for route in patterns:
                if isinstance(route, URLResolver):
                    yield from routes(route.url_patterns)
                else:
                    yield route
        guarded = {'Server.authentication.BRAVOAPIAuthentication',
                   'Server.authentication.ReadOnlyBasicAuthentication',
                   'Server.authentication.ReadOnlySessionAuthentication'}
        for route in routes(get_resolver().url_patterns):
            view = getattr(route.callback, 'cls', None)
            if view and hasattr(view, 'authentication_classes'):
                names = {a.__module__ + '.' + a.__name__ for a in view.authentication_classes}
                assert names and names <= guarded, (str(route.pattern), names)
        with override_settings(DEBUG=False, ALLOWED_HOSTS=['bravo.test'],
                MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware',
                            'django.contrib.auth.middleware.AuthenticationMiddleware']):
            def post(client, endpoint, data):
                token = client.cookies.get('csrftoken')
                if token is None:
                    client.cookies['csrftoken'] = _get_new_csrf_string()
                return client.post(endpoint, data, content_type='application/json', secure=True,
                    HTTP_ORIGIN='https://bravo.test', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
            clients = []
            for _ in range(20):
                client = Client(enforce_csrf_checks=True, HTTP_HOST='bravo.test')
                result = post(client, '/api/login', {'Email':'shirvalkarlab','Password':'synthetic-viewer','Persistent':False})
                assert result.status_code == 200, result.content
                assert result.json()['ReadOnly'] is True
                clients.append(client)
            assert len({c.cookies['sessionid'].value for c in clients}) == 20
            for client in clients:
                result = post(client, '/api/queryParticipants', {})
                assert result.status_code == 200, result.content
                assert [p['Id'] for p in result.json()] == [person.uid]
            assert post(clients[0], '/api/logout', {}).status_code == 204
            assert post(clients[0], '/api/queryParticipants', {}).status_code == 403
            client = clients[1]
            assert post(client, '/api/queryParticipants', {}).status_code == 200
            from Server import views
            from django.http import HttpResponse
            with patch.object(views, 'render', return_value=HttpResponse('synthetic SPA shell')):
                for url in ('/database', '/reports/aditya', '/'):
                    assert client.get(url, secure=True).status_code == 200
                assert client.get('/api/unknown', secure=True).status_code == 403
                assert client.get('/service/unknown', secure=True).status_code == 403
            profile = post(client, '/api/queryProfile', {}).json()
            assert 'APIKey' not in profile
            assert post(client, '/api/queryParticipantInformation', {'ParticipantId': hidden.uid}).status_code == 403
            before = dict(models.PlatformUser.find(email='shirvalkarlab').configuration)
            blocked = {
                '/api/updateSessions': {'SharedReadOnly':False},
                '/api/queryProfile': {'RequestType':'RefreshAPIToken'},
                '/api/createParticipantInformation': {'Name':'Forbidden'},
                '/api/updateParticipantInformation': {'ParticipantId':person.uid,'Tags':['wrong']},
                '/api/deleteParticipantInformation': {'ParticipantId':person.uid},
                '/api/queryClosedLoopChosenBand': {'ParticipantId':person.uid,'Action':'clear'},
                '/api/queryChronicTimeline': {'ParticipantId':person.uid,'RequestType':'DeleteCache'},
                '/api/manualSync': {'ParticipantId':person.uid,'RequestType':'Start'},
                '/api/importRedcapCSV': {'ParticipantId':person.uid,'AutoImport':True},
                '/api/manageStudyInformation': {'RequestType':'CreateStudy','StudyName':'Forbidden'},
                '/api/exportTitrationSheet': {'ParticipantId':person.uid},
                '/api/queryPainScores': {'ParticipantId':person.uid,'ForceRefresh':True},
                '/api/queryBiomarkerAnalysis': {'ParticipantId':person.uid,'RedcapRecordId':'outside'},
                '/api/register': {'Email':'new@example.invalid','Password':'synthetic-password','UserName':'X','Institute':''},
            }
            for endpoint, payload in blocked.items():
                response = post(client, endpoint, payload)
                assert response.status_code == 403, (endpoint, response.status_code, response.content)
            assert models.PlatformUser.find(email='shirvalkarlab').configuration == before
            assert models.Participant.objects.count() == 2
            assert models.Study.objects.count() == 1
            assert client.get('/api/downloadData?CacheType=ClearDataUpload',secure=True).status_code == 403
            fresh = Client(enforce_csrf_checks=True, HTTP_HOST='bravo.test')
            assert post(fresh, '/api/login', {'Email':'shirvalkarlab','Password':'synthetic-viewer','DesktopAuthentication':True}).status_code == 403
            assert not models.AuthenticationTokens.objects.filter(user=viewer).exists()
            token = models.AuthenticationTokens.objects.create(user=viewer)
            modes = [
                {'HTTP_X_SECURE_API_KEY':viewer.api_token},
                {'HTTP_X_SECURE_AUTH_TOKEN':token.token},
                {'HTTP_AUTHORIZATION':'Basic '+base64.b64encode(b'shirvalkarlab:synthetic-viewer').decode()},
            ]
            for mode in modes:
                attempt = Client(enforce_csrf_checks=True, HTTP_HOST='bravo.test', **mode)
                response = post(attempt,'/api/queryParticipants',{})
                assert response.status_code in (401,403), (mode.keys(),response.content)
            # Owner management remains available; no production resources are used.
            admin = Client(enforce_csrf_checks=True, HTTP_HOST='bravo.test')
            assert post(admin,'/api/login',{'Email':owner.email,'Password':'synthetic-password'}).status_code == 200
            response = post(admin,'/api/queryAnalysisConfigurations',{'RequestType':'UpdateConfigurations','Configurations':{}})
            assert response.status_code == 200, response.content
    ''')


def test_viewer_reads_do_not_create_devices_or_expose_submission_passcodes(tmp_path):
    isolated(tmp_path, '''
        from django.core.management import call_command
        from unittest.mock import patch
        from types import SimpleNamespace as NS
        from Server import models
        from Server.APIs import EventAnnotationHandler as surveys
        from Server.APIs import OuraRingDashboard, FitbitDashboard, GoogleHealthDashboard
        call_command('migrate',verbosity=0,interactive=False)
        owner=models.PlatformUser.create('owner@example.invalid','synthetic-password','Owner')
        viewer=models.PlatformUser.objects.create_user(email='shirvalkarlab',password='synthetic-viewer')
        viewer.configuration={'SharedReadOnly':True};viewer.institute=owner.institute;viewer.save()
        owner.institute.join(viewer,'Viewer')
        person=models.Participant.objects.create(name='Synthetic',institute=owner.institute)
        form=models.ScaleForms.objects.create(name='Synthetic Form',institute=owner.institute)
        link=models.ParticipantLinkRel.create(person,form)
        request=NS(user=viewer,data={'ParticipantId':person.uid,'RequestType':'RequestAll'})
        result=surveys.QueryParticipantSurveyRecords.post.__wrapped__(surveys.QueryParticipantSurveyRecords(),request)
        assert result.status_code==200
        assert result.data['Links'][0]['Id']==''
        assert result.data['Links'][0]['FormId']==form.uid
        assert link.link_code not in str(result.data)
        request.user=owner
        result=surveys.QueryParticipantSurveyRecords.post.__wrapped__(surveys.QueryParticipantSurveyRecords(),request)
        assert result.data['Links'][0]['Id']==link.link_code
        request.user=viewer;request.data['RequestType']='RequestOverview'
        for module,view,model in ((OuraRingDashboard,'QueryOuraRingData','OuraRingDevice'),
                                 (FitbitDashboard,'QueryFitbitData','FitbitDevice'),
                                 (GoogleHealthDashboard,'QueryGoogleHealthData','GoogleHealth')):
            cls=getattr(module,view)
            device=getattr(models,model)
            with patch.object(device,'create',side_effect=AssertionError('viewer device creation')):
                result=cls.post.__wrapped__(cls(),request)
                assert result.status_code==200, result.data
                assert 'No stored' in result.data['message']
            assert not device.objects.filter(owner=person).exists()
    ''')


def test_viewer_burst_never_schedules_or_reads_another_participant(tmp_path):
    isolated(tmp_path, '''
        from types import SimpleNamespace as NS
        from unittest.mock import patch
        from Server.APIs import DataAnalysis as api
        viewer=NS(configuration={'SharedReadOnly':True})
        request=NS(user=viewer,data={'ParticipantId':'allowed','RequestType':'RequestData',
            'RecordingIds':['recording'],'Channel':'channel','CenterFrequency':20})
        view=api.QueryBurstAnalysis()
        for recording in (None,NS(source=NS(owner_id='outside')),NS(source=NS(owner_id='allowed'))):
            with patch.object(api.Database,'checkAccessPermission',return_value=True), \\
                 patch.object(api.Database,'retrieveProcessingSettings',return_value=({},False)), \\
                 patch.object(api.models.Recording,'find',side_effect=[recording,None]), \\
                 patch.object(api.ProcessingScheduler,'ScheduleSlurmJob',side_effect=AssertionError('viewer cannot schedule')):
                result=api.QueryBurstAnalysis.post.__wrapped__(view,request)
                assert result.status_code==(200 if recording is not None and recording.source.owner_id=='allowed' else 403)
                if result.status_code==200:assert result.data==[]
    ''')
