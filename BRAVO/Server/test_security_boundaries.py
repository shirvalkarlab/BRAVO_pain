"""Synthetic privacy persistence and real authentication boundary regressions."""
import base64
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from Server import models
from Server.authentication import (
    BRAVOAPIAuthentication, BRAVOCSRFViewMiddleware, ReadOnlyBasicAuthentication,
)
from Server.Middlewares.ReadOnlyAccount import ReadOnlyAccountMiddleware
from modules import DataCurator, Database
from modules.PerceptPresentationPrivacy import (
    deidentify_stored_source, sanitize_patient_identifiers,
)


class PrivacySchemaTests(SimpleTestCase):
    def test_invalid_shapes_fail_before_any_output_is_returned(self):
        reports = [[], None, {'PatientInformation': []},
                   {'PatientInformation': {'Initial': None}},
                   {'PatientInformation': {'Initial': {'PatientId': ['synthetic']}}}]
        for report in reports:
            with self.subTest(report=report), self.assertRaises(ValueError):
                sanitize_patient_identifiers(json.dumps(report).encode())
        with self.assertRaises(ValueError):
            sanitize_patient_identifiers(b'{malformed')

    def test_absent_or_already_blank_identifiers_preserve_original_bytes(self):
        for report in [{}, {'PatientInformation': {}}, {'PatientInformation': {
                'Initial': {'PatientFirstName': None, 'PatientLastName': 0,
                            'PatientId': 'RCS08', 'PatientDateOfBirth': '\u2588\u2588'}}}]:
            raw = json.dumps(report, indent=2).encode()
            self.assertEqual(sanitize_patient_identifiers(raw), (raw, []))

    def test_custom_study_alias_preserves_scientific_metadata(self):
        raw = json.dumps({'PatientInformation': {'Initial': {'PatientId': 12345}},
                          'Timestamp': '2026-01-01T00:00:00Z'}).encode()
        cleaned, fields = sanitize_patient_identifiers(raw, study_id='TEST-07')
        self.assertEqual(json.loads(cleaned), {
            'PatientInformation': {'Initial': {'PatientId': 'TEST-07'}},
            'Timestamp': '2026-01-01T00:00:00Z'})
        self.assertEqual(fields, ['PatientInformation.Initial.PatientId'])

    def test_non_latin_identifiers_are_removed_without_changing_masked_values(self):
        report = {'PatientInformation': {
            'Initial': {'PatientFirstName': '\u738b', 'PatientLastName': '\u0418\u0432\u0430\u043d\u043e\u0432',
                        'PatientId': '\u03b1\u03b2\u03b3', 'PatientDateOfBirth': '\u0661\u0669\u0669\u0660'},
            'Final': {'PatientFirstName': '\u2588\u2588\u2588', 'PatientLastName': '',
                      'PatientId': None, 'PatientDateOfBirth': 0}},
            'ScientificDescription': '\u03b1 rhythm', 'Time': '2026-01-01T00:00:00Z'}
        raw = json.dumps(report, ensure_ascii=False).encode()
        cleaned, fields = sanitize_patient_identifiers(raw, 'TEST-07')
        parsed = json.loads(cleaned)
        self.assertEqual(parsed['PatientInformation']['Initial'], {
            'PatientFirstName': '', 'PatientLastName': '',
            'PatientId': 'TEST-07', 'PatientDateOfBirth': ''})
        self.assertEqual(parsed['PatientInformation']['Final'], report['PatientInformation']['Final'])
        self.assertEqual(parsed['ScientificDescription'], report['ScientificDescription'])
        self.assertEqual(parsed['Time'], report['Time'])
        self.assertEqual(len(fields), 4)
        self.assertEqual(sanitize_patient_identifiers(cleaned, 'TEST-07'), (cleaned, []))


class PrivacyPersistenceTests(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='bravo-synthetic-privacy-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for target, value in [('modules.Database.DATABASE_PATH', str(self.root) + '/'),
                              ('modules.Database.HASH_KEY', 'synthetic-hash-key'),
                              ('modules.DataCurator.secureEncoder', Fernet(Fernet.generate_key()))]:
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.raw = b'{"PatientInformation":{"Initial":{"PatientFirstName":"Synthetic","PatientId":"TEST-MRN"}},"Samples":[1,2,3]}'
        self.pointer = str(self.root / 'original.json')
        self.source = models.SourceFile.objects.create(
            pointer=self.pointer,
            hashed=Database.saveSourceFile(DataCurator.secureEncoder.encrypt(self.raw), self.pointer, bytes=True),
            metadata={'UniqueHashed': 'synthetic-dedup', 'ScientificField': 'preserved'})
        self.original_hash = self.source.hashed

    def assert_original_retained(self):
        self.source.refresh_from_db()
        self.assertEqual(self.source.pointer, self.pointer)
        self.assertEqual(self.source.hashed, self.original_hash)
        self.assertEqual(DataCurator.loadCacheFile(self.source), self.raw)

    def test_encrypted_replacement_persists_and_deletes_old_file_only_after_commit(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            cleaned, fields = deidentify_stored_source(self.source, 'TEST-07')
        self.source.refresh_from_db()
        self.assertNotEqual(self.source.pointer, self.pointer)
        self.assertEqual(DataCurator.loadCacheFile(self.source), cleaned)
        self.assertEqual(json.loads(cleaned)['Samples'], [1, 2, 3])
        self.assertEqual(json.loads(cleaned)['PatientInformation']['Initial'], {
            'PatientFirstName': '', 'PatientId': 'TEST-07'})
        self.assertEqual(self.source.metadata, {
            'UniqueHashed': 'synthetic-dedup', 'ScientificField': 'preserved',
            'DirectIdentifierPolicy': 1, 'DirectIdentifierFieldsRemoved': fields})
        self.assertTrue(Path(self.pointer).exists())
        self.assertGreaterEqual(len(callbacks), 1)
        with patch('modules.Database.deleteSourceFile', wraps=Database.deleteSourceFile) as deletion:
            for callback in callbacks:
                callback()
        deletion.assert_called_once_with(self.pointer)
        self.assertFalse(Path(self.pointer).exists())
        self.assertTrue(Path(self.source.pointer).exists())
        # A repeat request must not rewrite the stored bytes or schedule deletion.
        with self.captureOnCommitCallbacks(execute=True) as repeated:
            self.assertEqual(deidentify_stored_source(self.source, 'TEST-07'), (cleaned, []))
        self.assertEqual(repeated, [])

    def test_failed_write_preserves_source_reference_and_original_bytes(self):
        with patch('modules.Database.saveSourceFile', return_value=False):
            with self.assertRaisesRegex(ValueError, 'could not be written'):
                deidentify_stored_source(self.source)
        self.assert_original_retained()

    def test_failed_readback_verification_preserves_original_database_record(self):
        with patch.object(DataCurator.secureEncoder, 'decrypt', side_effect=[self.raw, b'different']):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                deidentify_stored_source(self.source)
        self.assert_original_retained()

    def test_database_failure_does_not_schedule_original_source_deletion(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with patch.object(self.source, 'save', side_effect=RuntimeError('synthetic write failure')):
                with self.assertRaisesRegex(RuntimeError, 'synthetic write failure'):
                    deidentify_stored_source(self.source)
        self.assertEqual(callbacks, [])
        self.assert_original_retained()


class AuthenticationBoundaryTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.viewer = models.PlatformUser.objects.create_user(
            'synthetic-viewer@example.test', 'synthetic-test-password')
        self.viewer.configuration = {'ReadOnly': True}
        self.viewer.save(update_fields=['configuration'])
        self.token = models.AuthenticationTokens.objects.create(user=self.viewer)

    def request(self, path='/api/queryParticipants', **headers):
        return self.factory.post(path, data='{}', content_type='application/json', **headers)

    def test_real_basic_credentials_allow_read_and_deny_write(self):
        encoded = base64.b64encode(b'synthetic-viewer@example.test:synthetic-test-password').decode()
        headers = {'HTTP_AUTHORIZATION': 'Basic ' + encoded}
        authenticated, _ = ReadOnlyBasicAuthentication().authenticate(self.request(**headers))
        self.assertEqual(authenticated.pk, self.viewer.pk)
        with self.assertRaises(PermissionDenied):
            ReadOnlyBasicAuthentication().authenticate(self.request('/api/uploadData', **headers))

    def test_absent_and_invalid_basic_credentials_never_authenticate(self):
        self.assertIsNone(ReadOnlyBasicAuthentication().authenticate(self.request()))
        encoded = base64.b64encode(b'synthetic-viewer@example.test:wrong-password').decode()
        with self.assertRaises(AuthenticationFailed):
            ReadOnlyBasicAuthentication().authenticate(self.request(HTTP_AUTHORIZATION='Basic ' + encoded))

    def test_real_key_and_desktop_token_have_equivalent_viewer_restrictions(self):
        for headers in [{'HTTP_X_SECURE_API_KEY': self.viewer.api_token},
                        {'HTTP_X_SECURE_AUTH_TOKEN': self.token.token}]:
            with self.subTest(header=next(iter(headers))):
                request = self.request(**headers)
                user, credential = BRAVOAPIAuthentication().authenticate(request)
                self.assertEqual(user.pk, self.viewer.pk)
                self.assertIsNone(credential)
                self.assertTrue(user.api_access)
                self.assertTrue(request.csrf_processing_done)
                denied = self.request('/api/uploadData', **headers)
                with self.assertRaises(PermissionDenied):
                    BRAVOAPIAuthentication().authenticate(denied)
                self.assertFalse(getattr(denied, 'csrf_processing_done', False))

    def test_unknown_credentials_and_missing_credentials_do_not_authenticate(self):
        for headers in [{}, {'HTTP_X_SECURE_API_KEY': 'unknown'},
                        {'HTTP_X_SECURE_AUTH_TOKEN': 'unknown'},
                        {'HTTP_X_SECURE_API_KEY': 'unknown', 'HTTP_X_SECURE_AUTH_TOKEN': self.token.token}]:
            self.assertIsNone(BRAVOAPIAuthentication().authenticate(self.request(**headers)))

    def test_orphan_token_record_fails_closed(self):
        with patch('Server.authentication.models.AuthenticationTokens.objects.filter') as query:
            query.return_value.first.return_value = SimpleNamespace(user=None)
            request = self.request(HTTP_X_SECURE_AUTH_TOKEN='synthetic-orphan')
            self.assertIsNone(BRAVOAPIAuthentication().authenticate(request))
            self.assertFalse(getattr(request, 'csrf_processing_done', False))

    def test_desktop_token_creation_time_enforces_five_hour_window(self):
        now = 2_000_000_000.0
        for age, accepted in [(0, True), (1, True), (18_000, True),
                              (18_000.01, False), (365 * 86400, False), (-1, False)]:
            with self.subTest(age=age), patch('Server.authentication.models.current_time', return_value=now):
                models.AuthenticationTokens.objects.filter(pk=self.token.pk).update(date=now-age)
                request = self.request(HTTP_X_SECURE_AUTH_TOKEN=self.token.token)
                result = BRAVOAPIAuthentication().authenticate(request)
                self.assertEqual(result is not None, accepted)
                self.assertEqual(getattr(request, 'csrf_processing_done', False), accepted)


class ViewerAndCsrfBoundaryTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ReadOnlyAccountMiddleware(lambda request: HttpResponse(status=204))
        self.viewer = SimpleNamespace(is_authenticated=True, configuration={'ReadOnly': True})

    def test_malformed_or_nonobject_mixed_requests_are_denied(self):
        for body in [b'', b'not-json', b'\xff', b'[]', b'null', b'{}', b'{"RequestType":"Delete"}']:
            request = self.factory.post('/api/querySourceFiles', data=body, content_type='application/json')
            request.user = self.viewer
            self.assertEqual(self.middleware(request).status_code, 403)

    def test_structured_request_types_and_malformed_profile_body_are_denied(self):
        for path in ['/api/queryProfile', '/api/querySourceFiles']:
            for body in [b'not-json', b'[]', b'null', b'{"RequestType":[]}',
                         b'{"RequestType":{}}', b'{"RequestType":1}', b'{"RequestType":true}']:
                with self.subTest(path=path, body=body):
                    request = self.factory.post(path, data=body, content_type='application/json')
                    request.user = self.viewer
                    self.assertEqual(self.middleware(request).status_code, 403)

    def test_profile_read_and_allowed_explicit_type_still_work(self):
        for path, body in [('/api/queryProfile', b''), ('/api/queryProfile', b'{}'),
                           ('/api/queryProfile', b'{"RequestType":null}'),
                           ('/api/querySourceFiles/', b'{"RequestType":"All"}')]:
            request = self.factory.post(path, data=body, content_type='application/json')
            request.user = self.viewer
            self.assertEqual(self.middleware(request).status_code, 204)

    def test_public_pages_and_missing_users_pass_to_existing_authentication(self):
        for path in ['/', '/database', '/apiary/example']:
            request = self.factory.get(path)
            request.user = self.viewer
            self.assertEqual(self.middleware(request).status_code, 204)
        self.assertEqual(self.middleware(self.factory.post('/api/uploadData')).status_code, 204)

    def test_allowed_post_cannot_be_reused_with_other_verbs(self):
        for method in ['get', 'put', 'delete', 'patch']:
            request = getattr(self.factory, method)('/api/queryParticipants/')
            request.user = self.viewer
            self.assertEqual(self.middleware(request).status_code, 403)

    def test_session_csrf_is_enforced_and_api_key_path_delegates_authentication(self):
        middleware = BRAVOCSRFViewMiddleware(lambda request: HttpResponse())
        callback = lambda request: HttpResponse()
        denied = middleware.process_view(self.factory.post('/api/queryParticipants'), callback, (), {})
        self.assertEqual(denied.status_code, 403)
        self.assertIsNone(middleware.process_view(self.factory.get('/api/queryParticipants'), callback, (), {}))
        keyed = self.factory.post('/api/queryParticipants', HTTP_X_SECURE_API_KEY='synthetic-key')
        self.assertIsNone(middleware.process_view(keyed, callback, (), {}))
