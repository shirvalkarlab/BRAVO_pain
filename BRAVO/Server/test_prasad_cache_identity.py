"""Real authenticated dispatch; synthetic metadata only, no DB or analysis execution."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from Server.test_prasad_api_boundaries import configured_api


class CacheIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = configured_api()
        from rest_framework.test import APIRequestFactory, force_authenticate
        cls.factory = APIRequestFactory()
        cls.authenticate = staticmethod(force_authenticate)

    def setUp(self):
        self.person = NS(uid='synthetic-subject')
        self.user = NS(pk=1, configuration={'ActiveStudy': 'study'}, is_authenticated=True)
        self.manifest = {'fingerprint': 'approved-one'}
        self.permissions = {'Deidentified': False}
        self.processing = {'filter': 'reviewed'}
        self.epoch = 'master:123'
        self.code = 'code-one'
        for target, changes in [
            (self.api.Database, {'checkAccessPermission': Mock(side_effect=lambda *a, **k: self.permissions),
                                 'retrieveProcessingSettings': Mock(side_effect=lambda c: (self.processing, {}))}),
            (self.api.models.Participant, {'find': Mock(return_value=self.person)}),
            (self.api.AnalysisData, {'input_manifest': Mock(side_effect=lambda p: copy.deepcopy(self.manifest))}),
            (self.api, {'analysis_code_fingerprint': Mock(side_effect=lambda: self.code),
                        'server_process_epoch': Mock(side_effect=lambda: (self.epoch, True))})]:
            p = patch.multiple(target, **changes); p.start(); self.addCleanup(p.stop)
        self.jobs = patch('modules.AnalysisJobs.get_or_start').start()
        self.addCleanup(patch.stopall)

    def request(self, body=None, authenticated=True, session='session-one'):
        request = self.factory.post('/api/queryServerIdentity',
                                    {'ParticipantId': self.person.uid} if body is None else body, format='json')
        request.session = NS(session_key=session)
        if authenticated:
            self.authenticate(request, user=self.user)
        result = self.api.QueryServerIdentity.as_view()(request)
        self.jobs.assert_not_called()
        return result

    def test_identity_stable_and_opaque_with_no_analysis_jobs(self):
        a = self.request(); b = self.request()
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.data, b.data)
        self.assertRegex(a.data['boot_token'], r'^[a-f0-9]{64}$')
        self.assertEqual(a['Cache-Control'], 'no-store')
        self.assertTrue(a.data['stable_across_workers'])
        for private in ('synthetic-subject', 'approved-one', 'code-one', 'session-one'):
            self.assertNotIn(private, str(a.data))

    def test_input_permissions_account_session_processing_restart_code_changes_invalidate(self):
        previous = self.request().data['boot_token']
        changes = [lambda: self.manifest.update(fingerprint='approved-two'),
                   lambda: self.permissions.update(Deidentified=True),
                   lambda: setattr(self.user, 'pk', 2),
                   lambda: self.processing.update(filter='changed'),
                   lambda: self.user.configuration.update(ActiveStudy='another-study'),
                   lambda: setattr(self, 'code', 'code-two'),
                   lambda: setattr(self, 'epoch', 'master:456')]
        for change in changes:
            change(); current = self.request().data['boot_token']
            self.assertNotEqual(previous, current); previous = current
        self.assertNotEqual(previous, self.request(session='new-session').data['boot_token'])
        self.assertNotEqual(previous, self.request(body={'ParticipantId': 'another-subject'}).data['boot_token'])
        with patch.dict(os.environ, {'BRAVO_MAIN_BIPOLAR': 'changed'}):
            self.assertNotEqual(previous, self.request().data['boot_token'])

    def test_unauthenticated_denied_and_missing_subject_never_read_metadata(self):
        self.assertIn(self.request(authenticated=False).status_code, (401, 403))
        self.api.Database.checkAccessPermission.assert_not_called()
        self.permissions = False
        self.assertEqual(self.request().status_code, 403)
        self.api.models.Participant.find.assert_not_called()
        self.permissions = {'Deidentified': True}
        self.api.models.Participant.find.return_value = None
        self.assertEqual(self.request().status_code, 404)
        self.api.AnalysisData.input_manifest.assert_not_called()

    def test_malformed_identity_requests_are_rejected(self):
        for body in ([], {}, {'ParticipantId': 4}, {'ParticipantId': ''}, {'ParticipantId': ' '},
                     {'ParticipantId': 'synthetic-subject', 'ProcessedPRO': []}):
            with self.subTest(body=body):
                self.assertEqual(self.request(body).status_code, 400)
        self.api.Database.checkAccessPermission.assert_not_called()
        self.api.AnalysisData.input_manifest.assert_not_called()


class ProcessEpochTests(unittest.TestCase):
    def test_reads_parent_start_even_with_parentheses_in_process_name(self):
        api = configured_api()
        with patch.object(api.os, 'getppid', return_value=42), patch.object(Path, 'read_text', return_value='42 (gunicorn (master)) '+ ' '.join(['S'] + ['0']*18 + ['987'])):
            self.assertEqual(api.server_process_epoch(), ('42:987', True))

    def test_unreadable_or_malformed_proc_is_explicitly_not_worker_stable(self):
        api = configured_api()
        with patch.object(api.os, 'getpid', return_value=99):
            with patch.object(Path, 'read_text', side_effect=OSError):
                self.assertEqual(api.server_process_epoch(), ('99', False))
            with patch.object(Path, 'read_text', return_value='broken'):
                self.assertEqual(api.server_process_epoch(), ('99', False))
