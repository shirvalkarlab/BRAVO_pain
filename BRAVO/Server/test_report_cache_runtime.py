"""Real cache/DRF runtime tests using synthetic users and temporary storage only."""
import gzip
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import patch

from django.http import HttpResponse
from django.test import SimpleTestCase
from filelock import FileLock
from rest_framework.response import Response
from rest_framework.views import APIView

from modules import Database, ReportCache


class ReportCacheRuntimeTests(SimpleTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        for context in (
            patch.dict(os.environ, DATASERVER_PATH=temporary.name),
            patch.object(Database, 'checkAccessPermission', return_value={'Deidentified': False}),
            patch.object(Database, 'retrieveProcessingSettings', return_value=({}, False)),
            patch.object(ReportCache.transaction, 'on_commit', side_effect=lambda callback: callback()),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.calls = 0

    def request(self, encoding='', data=None, configuration=None, api=False):
        user = NS(configuration=configuration or {})
        if api:
            user.api_access = True
        return NS(path='/runtime-report', headers={'Accept-Encoding': encoding}, user=user,
                  data={'ParticipantId': 'synthetic', 'RequestType': 'RequestAll'} if data is None else data)

    def report(self):
        @ReportCache.cached_report
        def calculate(view, request):
            self.calls += 1
            return Response({'generation': self.calls, 'values': [0, None, 4]})
        return calculate

    def decoded(self, response):
        content = response.content
        if response.get('Content-Encoding') == 'gzip':
            content = gzip.decompress(content)
        return json.loads(content)

    def test_non_read_requests_and_missing_participant_delegate_without_cache_or_access_query(self):
        report = self.report()
        with patch.object(Database, 'checkAccessPermission') as permission:
            for body in ({}, {'ParticipantId': 'synthetic', 'RequestType': 'Delete'},
                         {'ParticipantId': '', 'RequestType': 'RequestAll'}):
                self.assertIsInstance(report(None, self.request(data=body)), Response)
            permission.assert_not_called()
        self.assertEqual(list(ReportCache.directory().glob('*.gz')), [])

    def test_revoked_access_delegates_even_if_authorized_result_is_cached(self):
        report = self.report()
        report(None, self.request())
        with patch.object(Database, 'checkAccessPermission', return_value=False):
            result = report(None, self.request())
        self.assertIsInstance(result, Response)
        self.assertEqual(result.data['generation'], 2)
        self.assertEqual(len(list(ReportCache.directory().glob('*.gz'))), 1)

    def test_encoding_negotiation_preserves_json_and_never_allows_browser_storage(self):
        report = self.report()
        for encoding, compressed in [('br, gzip;q=0.4', True), ('gzip;q=0', False),
                                      ('deflate', False), ('gzip;q=invalid', False),
                                      ('gzip;level=2;q=1', True), ('', False)]:
            with self.subTest(encoding=encoding):
                response = report(None, self.request(encoding))
                self.assertEqual(response.get('Content-Encoding') == 'gzip', compressed)
                self.assertEqual(self.decoded(response)['values'], [0, None, 4])
                self.assertEqual(response['Cache-Control'], 'no-store')
                self.assertEqual(response['Vary'], 'Accept-Encoding')
        self.assertEqual(self.calls, 1)

    def test_cache_identity_separates_permissions_processing_api_mode_and_request(self):
        report = self.report()
        self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')
        self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'HIT')
        for request in (self.request(api=True), self.request(data={'ParticipantId': 'other'})):
            self.assertEqual(report(None, request)['X-BRAVO-Report-Cache'], 'MISS')
        with patch.object(Database, 'checkAccessPermission', return_value={'Deidentified': True}):
            self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')
        with patch.object(Database, 'retrieveProcessingSettings', return_value=({'filter': 2}, False)):
            self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')
        with patch.object(ReportCache, 'analysis_policy_identity', return_value='new-policy'):
            self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')
        self.assertEqual(report(NS(cache_version="oura-v1"), self.request())["X-BRAVO-Report-Cache"], "MISS")
        self.assertEqual(report(NS(cache_version="oura-v1"), self.request())["X-BRAVO-Report-Cache"], "HIT")
        self.assertEqual(report(NS(cache_version="oura-v2"), self.request())["X-BRAVO-Report-Cache"], "MISS")
        self.assertEqual(self.calls, 8)

    def test_expired_report_recomputes_only_when_max_age_is_enabled(self):
        report = self.report()
        report(None, self.request())
        path = next(ReportCache.directory().glob('*.gz'))
        old = time.time() - 100
        os.utime(path, (old, old))
        self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'HIT')
        with patch.object(ReportCache, 'MAX_AGE', 10):
            self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')
        self.assertEqual(self.calls, 2)

    def test_sync_serves_previous_report_but_warmer_recalculates_current_revision(self):
        report = self.report()
        report(None, self.request())
        ReportCache.invalidate()
        with FileLock(str(ReportCache.directory() / 'preparing.lock')):
            self.assertTrue(ReportCache.refresh_in_progress())
            previous = report(None, self.request())
            self.assertEqual(previous['X-BRAVO-Report-Cache'], 'UPDATING')
            self.assertEqual(self.decoded(previous)['generation'], 1)
            token = ReportCache._warming.set(True)
            try:
                current = report(None, self.request())
            finally:
                ReportCache._warming.reset(token)
            self.assertEqual(current['X-BRAVO-Report-Cache'], 'MISS')
            self.assertEqual(self.decoded(current)['generation'], 2)
        self.assertFalse(ReportCache.refresh_in_progress())

    def test_cache_miss_during_sync_computes_instead_of_returning_nonexistent_stale_report(self):
        with FileLock(str(ReportCache.directory() / 'preparing.lock')):
            self.assertEqual(self.report()(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')

    def test_lock_contention_returns_retryable_503_without_duplicate_calculation(self):
        report = self.report()
        report(None, self.request())
        path = next(ReportCache.directory().glob('*.gz'))
        ReportCache.invalidate()
        with FileLock(str(path) + '.lock'):
            with patch.object(ReportCache, 'FileLock', side_effect=lambda path, timeout: FileLock(path, timeout=0)):
                result = report(None, self.request())
        self.assertEqual(result.status_code, 503)
        self.assertEqual(result['Retry-After'], '5')
        self.assertEqual(self.calls, 1)
        self.assertEqual(report(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')

    def test_parallel_readers_reuse_result_after_lock(self):
        def compute(view, request):
            self.calls += 1
            time.sleep(.06)
            return Response({'generation': self.calls})
        report = ReportCache.cached_report(compute)
        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(executor.map(lambda _: report(None, self.request()), range(4)))
        self.assertEqual(self.calls, 1)
        self.assertEqual(sorted(r['X-BRAVO-Report-Cache'] for r in responses), ['HIT', 'HIT', 'HIT', 'MISS'])

    def test_uncommitted_revision_is_not_published_and_neural_revision_changes_only_when_requested(self):
        callbacks = []
        with patch.object(ReportCache.transaction, 'on_commit', side_effect=callbacks.append):
            ReportCache.invalidate(neural=True)
        self.assertEqual(ReportCache.revision(), 'initial')
        callbacks.pop()()
        neural = ReportCache.revision('neural-revision')
        self.assertEqual(neural, ReportCache.revision())
        ReportCache.invalidate()
        self.assertEqual(neural, ReportCache.revision('neural-revision'))
        self.assertNotEqual(neural, ReportCache.revision())

    def test_changed_input_during_compute_is_never_published_and_context_resets(self):
        @ReportCache.cached_report
        def report(view, request):
            captured = ReportCache.calculation_revision()
            ReportCache.invalidate()
            self.assertEqual(ReportCache.calculation_revision(), captured)
            return Response({'value': 1})
        report(None, self.request())
        self.assertEqual(list(ReportCache.directory().glob('*.gz')), [])
        self.assertEqual(ReportCache.calculation_revision(), ReportCache.revision())

    def test_errors_non_json_responses_and_serialization_failure_are_not_cached(self):
        for result in (Response({'error': 'unavailable'}, status=422), HttpResponse('plain')):
            with self.subTest(status=result.status_code):
                self.assertIs(ReportCache.cached_report(lambda *_: result)(None, self.request()), result)
        def fail(*_):
            raise RuntimeError('synthetic compute failure')
        with self.assertRaisesRegex(RuntimeError, 'synthetic compute failure'):
            ReportCache.cached_report(fail)(None, self.request())
        with self.assertRaises(ValueError):
            ReportCache.cached_report(lambda *_: Response({'value': float('nan')}))(None, self.request())
        self.assertIsNone(ReportCache._calculation_revision.get())
        self.assertEqual(list(ReportCache.directory().glob('*.gz')), [])
        self.assertEqual(self.report()(None, self.request())['X-BRAVO-Report-Cache'], 'MISS')

    def test_derived_sources_and_recordings_do_not_invalidate_but_raw_changes_do(self):
        with patch.object(ReportCache, 'invalidate') as invalidate:
            for name, instance in [
                ('SourceFile', NS(type='CachedResult')),
                ('Recording', NS(original_id='parent')),
                ('Recording', NS(original_id=None, type='ProcessedData')),
                ('Recording', NS(original_id=None, type='Snapshot', source=NS(type='ChronicNeuralActivitySource'))),
            ]:
                ReportCache.data_changed(type(name, (), {}), instance)
            invalidate.assert_not_called()
            for name, instance, neural in [
                ('SourceFile', NS(type='MedtronicJSON'), True),
                ('SourceFile', NS(type='OuraRingAPISource'), False),
                ('Recording', NS(original_id=None, type='MedtronicBrainSenseSurvey', source=NS(type='MedtronicJSON')), True),
                ('Recording', NS(original_id=None, type='Other', source=NS(type='Other')), False),
                ('Therapy', NS(), True), ('ScaleRecord', NS(), False),
            ]:
                ReportCache.data_changed(type(name, (), {}), instance)
                invalidate.assert_called_with(neural=neural)
            invalidate.reset_mock()
            ReportCache.relations_changed(None, 'pre_add')
            invalidate.assert_not_called()
            for action in ('post_add', 'post_remove', 'post_clear'):
                ReportCache.relations_changed(None, action)
            self.assertEqual(invalidate.call_count, 3)
            invalidate.assert_called_with(neural=True)

    def prepare_users(self):
        # Production DRF requests and authentication are retained; only database
        # inventory and URL targets are replaced with synthetic, read-only fixtures.
        from Server import models
        users = [NS(configuration={'ActiveStudy': 'study'}, is_active=True, uid=uid)
                 for uid in ['denied', 'one', 'duplicate', 'different']]
        contexts = [
            patch.object(models.PlatformUser.objects, 'filter', return_value=users),
            patch.object(Database, 'checkAccessPermission',
                         side_effect=lambda user, *a, **kw: False if user.uid == 'denied' else {'scope': user.uid if user.uid == 'different' else 'shared'}),
        ]
        for context in contexts:
            context.start()
            self.addCleanup(context.stop)
        return NS(uid='synthetic', institute='synthetic-institute')

    def test_prewarm_uses_effective_configuration_once_and_real_authenticated_requests(self):
        participant = self.prepare_users()
        requests = []
        class SyntheticView(APIView):
            authentication_classes = []
            permission_classes = []
            def post(inner, request):
                requests.append((request.path, request.data, request.user.uid, request.headers['Accept-Encoding']))
                self.assertTrue(ReportCache._warming.get())
                self.assertTrue(ReportCache.refresh_in_progress())
                if request.path.endswith('queryTherapyHistory'):
                    return HttpResponse('{}', content_type='application/json')
                return Response({'ok': True})
        with patch('django.urls.resolve', return_value=NS(func=SyntheticView.as_view())):
            results = ReportCache.prewarm_participant(participant)
        self.assertEqual(len(results), 12)
        self.assertEqual({entry[2] for entry in requests}, {'one', 'different'})
        self.assertTrue(all(entry[1]['ParticipantId'] == 'synthetic' and entry[3] == 'gzip' for entry in requests))
        self.assertEqual([result['report'] for result in results[:4]], ['neural', 'multimodal', 'snapshot', 'therapy'])
        self.assertEqual([entry[1] for entry in requests if entry[0].endswith('queryOuraFreeReps')], [{'ParticipantId': 'synthetic'}] * 2)
        self.assertFalse(ReportCache._warming.get())
        self.assertFalse(ReportCache.refresh_in_progress())

    def test_failed_prewarm_restores_context_releases_lock_and_can_retry(self):
        participant = self.prepare_users()
        def fail(request):
            self.assertTrue(ReportCache._warming.get())
            return HttpResponse('{}', status=503, content_type='application/json')
        with patch('django.urls.resolve', return_value=NS(func=fail)):
            with self.assertRaisesRegex(RuntimeError, 'neural.*503'):
                ReportCache.prewarm_participant(participant)
        self.assertFalse(ReportCache._warming.get())
        self.assertFalse(ReportCache.refresh_in_progress())
        with patch('django.urls.resolve', return_value=NS(func=lambda request: HttpResponse('{}'))):
            self.assertEqual(len(ReportCache.prewarm_participant(participant)), 12)
