"""Real DRF dispatch and pure synthetic analysis boundaries; never touches a DB or patient store."""
import ast
import copy
import importlib
import json
import math
import os
from pathlib import Path
import re
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
API_PATH = ROOT / 'Server/APIs/PrasadAnalysis.py'


def configured_api():
    import django
    from cryptography.fernet import Fernet
    os.environ.setdefault("DATASERVER_ENCRYPTION", Fernet.generate_key().decode())
    os.environ.setdefault("DATASERVER_HASHKEY", "synthetic-hash-key")
    from django.conf import settings
    if not settings.configured:
        settings.configure(SECRET_KEY='synthetic-tests-only', DEBUG=True,
                           INSTALLED_APPS=['django.contrib.auth', 'django.contrib.contenttypes', 'Server'],
                           AUTH_USER_MODEL='Server.PlatformUser',
                           DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
                           REST_FRAMEWORK={'DEFAULT_AUTHENTICATION_CLASSES': [], 'UNAUTHENTICATED_USER': None})
    django.setup()
    from Server.APIs import PrasadAnalysis
    return PrasadAnalysis


def helpers():
    api = configured_api()
    return {'validated_controls': api.validated_controls, 'deidentified_result': api.deidentified_result}


class ControlValidationTests(unittest.TestCase):
    def setUp(self):
        self.validate = helpers()['validated_controls']

    def test_defaults_preserved_and_work_multipliers_bounded(self):
        self.assertEqual(self.validate({'ParticipantId': 'synthetic'}, 'queryStimOptimizer'), {'ParticipantId': 'synthetic'})
        for key, value in [('NBatches', 0), ('NBatches', 11), ('Q', 100000), ('Q', 2.5), ('Q', True),
                           ('WashinMin', -1), ('WashinMin', 'nan'), ('BandWidthHz', 'inf'),
                           ('CenterHz', True), ('NBoot', 5001), ('WindowMonths', 121), ('WashinMin', 'not-numeric')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.validate({'ParticipantId': 'synthetic', key: value}, 'queryStimOptimizer')
        controls = self.validate({'NBatches': '3', 'Q': 4, 'WashinMin': 1}, 'queryStimOptimizer')
        self.assertEqual(controls, {'NBatches': 3, 'Q': 4, 'WashinMin': 1.0})

    def test_actual_biomarker_ui_snapshot_keys_and_current_default_payload(self):
        client = ROOT.parent / "Client/src/views/Reports/Biomarkers/index.js"
        source = client.read_text()
        block = re.search(r"const snapshot = \(\) => \(\{(.*?)\}\);", source, re.S).group(1)
        keys = {field.strip().split(":")[0].strip() for field in block.split(",") if field.strip()}
        defaults = {"source": "both", "LabelMetric": "nrs", "LabelStrategy": "tertile",
                    "PercentileLow": 33.3, "PercentileHigh": 66.7, "MatchToleranceMin": 60,
                    "MaxPerRating": 3, "RefractoryMin": 2, "MatchDirection": "pro_first",
                    "UseLiveMatching": True, "MatchExtentSec": 30, "AllowWindowReuse": False,
                    "SlidingWindow": False}
        self.assertEqual(keys, set(defaults))
        for operation in ("queryBiomarkerAnalysis", "queryBandValidation", "emitBandCandidate",
                          "queryDeploymentROC", "queryLsbPower", "queryPsdLsbConversion",
                          "queryDeploymentRocByEra", "queryDeploymentSummary", "queryClosedLoopResearch"):
            body = {"ParticipantId": "synthetic", "Channel": "ONE_THREE_LEFT", "CenterHz": 20.5,
                    "BandWidthHz": 5, **defaults}
            self.assertEqual(self.validate(body, operation), body)
        for mode in ("prior", "nearest", "pro_first", "pro"):
            self.validate({**defaults, "MatchDirection": mode}, "queryBiomarkerAnalysis")

    def test_existing_disable_and_window_semantics(self):
        values = {'OutlierNMad': 0, 'MatchToleranceMin': -1, 'SlidingWindow': False,
                  'WindowMonths': None, 'WindowStep': '', 'AllowWindowReuse': 'false'}
        actual = self.validate(values, 'queryBiomarkerAnalysis')
        self.assertEqual(actual['OutlierNMad'], 0)
        self.assertEqual(actual['MatchToleranceMin'], -1)
        self.assertFalse(actual['AllowWindowReuse'])
        self.assertNotIn('WindowMonths', actual)

    def test_shapes_enums_and_percentiles(self):
        for controls in ({'Sites': 'back'}, {'Sites': ['back', 'back']}, {'Sites': ['unknown']},
                         {'Hemispheres': [{}]}, {'Backend': []}, {'UseLiveMatching': []},
                         {'LabelMetric': {}}, {'Channel': ''}, {'ForceRefresh': []},
                         {'PercentileLow': 80, 'PercentileHigh': 20}, {'Unexpected': []}):
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                self.validate(controls, 'queryStimOptimizer')
        self.assertEqual(self.validate({'Sites': ['back'], 'Hemispheres': ['Left']}, 'queryStimOptimizer')['Sites'], ['back'])

    def test_supported_refresh_aliases_preserve_requested_refresh(self):
        for value in (None, False, True, "matrix", "all", "full", "none"):
            with self.subTest(value=value):
                self.assertEqual(self.validate({"ForceRefresh": value}, "queryBiomarkerAnalysis"), {"ForceRefresh": value})

    def test_deidentified_recursive_metadata_keys_and_names(self):
        person = NS(uid='synthetic-uid', name='Renamed Subject', code='', mrn='MRN123')
        original = {'participant': 'OLD42', 'pipeline': {'special': 'OLD42 calibration for Renamed Subject'},
                    'metadata': {'Name': 'Renamed Subject', 'MRN': 'MRN123', 'DOB': 123},
                    'InputManifest': {'participant_uid': person.uid, 'model_hashes': {'OLD42.json': 'abc'}},
                    'channels': [{'name': 'LEFT_ZERO_THREE', 'values': [1, 2], 'date': 1754000000}]}
        before = copy.deepcopy(original)
        result = helpers()['deidentified_result'](original, person)
        encoded = json.dumps(result)
        for identifier in ['OLD42', 'Renamed Subject', 'MRN123']:
            self.assertNotIn(identifier, encoded)
        self.assertEqual(result['metadata'], {'Name': person.uid, 'MRN': '', 'DOB': 0})
        self.assertEqual(result['channels'], original['channels'])
        self.assertEqual(original, before)


class RealDRFBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = configured_api()
        cls.code_hash = staticmethod(cls.api.analysis_code_fingerprint)
        from rest_framework.test import APIRequestFactory, force_authenticate
        cls.factory = APIRequestFactory()
        cls.authenticate = staticmethod(force_authenticate)

    def setUp(self):
        self.person = NS(uid='synthetic-uid', name='SYN42', code='', mrn='synthetic-mrn')
        self.user = NS(configuration={'ActiveStudy': 'synthetic-study'}, is_authenticated=True)
        self.manifest = {'fingerprint': 'approved-one', 'participant_uid': self.person.uid,
                         'model_hashes': {'SYN42.json': 'model-hash'}}
        self.permission = {'Deidentified': False}
        self.service = NS(pain_scores_for_participant=Mock(return_value={'participant': 'SYN42', 'values': [1, 2]}))
        self.jobs = Mock(side_effect=lambda identity, compute: (200, compute()))
        for target, kwargs in [(self.api.Database, {'checkAccessPermission': Mock(side_effect=lambda *a, **k: self.permission),
                                                  'retrieveProcessingSettings': Mock(return_value=({}, {}))}),
                               (self.api.models.Participant, {'find': Mock(return_value=self.person)}),
                               (self.api.AnalysisData, {'input_manifest': Mock(side_effect=lambda p: copy.deepcopy(self.manifest))}),
                               (self.api, {'analysis_code_fingerprint': Mock(return_value='code'),
                                           'close_old_connections': Mock(), 'connections': NS(close_all=Mock()),
                                           'importlib': NS(import_module=Mock(return_value=self.service))})]:
            patcher = patch.multiple(target, **kwargs)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch('modules.AnalysisJobs.get_or_start', self.jobs)
        patcher.start(); self.addCleanup(patcher.stop)

    def request(self, body=None, authenticated=True, operation='queryPainScores'):
        request = self.factory.post('/api/' + operation, {'ParticipantId': self.person.uid} if body is None else body, format='json')
        if authenticated:
            self.authenticate(request, user=self.user)
        return self.api.ResearchAnalysis.as_view(operation=operation)(request)

    def test_real_dispatch_rejects_malformed_required_fields_and_overrides(self):
        for body in ([], {}, {"ParticipantId": 3}, {"ParticipantId": self.person.uid, "ProcessedPRO": []},
                     {"ParticipantId": self.person.uid, "_internal": True}):
            with self.subTest(body=body):
                self.assertEqual(self.request(body).status_code, 400)
        self.assertEqual(self.request({"ParticipantId": self.person.uid}, operation="queryBandValidation").status_code, 400)
        for controls in ({"Channel": [], "CenterHz": 20}, {"Channel": "ONE_THREE_LEFT", "CenterHz": "nan"},
                         {"Channel": "ONE_THREE_LEFT", "CenterHz": "bad"}):
            with self.subTest(controls=controls):
                self.assertEqual(self.request({"ParticipantId": self.person.uid, **controls}, operation="queryBandValidation").status_code, 400)
        self.jobs.assert_not_called()
        self.api.AnalysisData.input_manifest.assert_not_called()

    def test_valid_band_job_pending_has_retry_header_and_missing_participant_404(self):
        self.jobs.side_effect = None
        self.jobs.return_value = (202, {"status": "queued"})
        response = self.request({"ParticipantId": self.person.uid, "Channel": "ONE_THREE_LEFT", "CenterHz": 20.5}, operation="queryBandValidation")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response["Retry-After"], "3")
        self.api.models.Participant.find.return_value = None
        self.assertEqual(self.request().status_code, 404)
        self.assertEqual(self.jobs.call_count, 1)

    def test_real_code_fingerprint_reads_source_and_is_stable(self):
        self.code_hash.cache_clear()
        first = self.code_hash()
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, self.code_hash())
        self.code_hash.cache_clear()

    def test_snapshot_change_after_compute_discards_result(self):
        self.api.AnalysisData.input_manifest.side_effect = [self.manifest, self.manifest, {"fingerprint": "changed"}]
        with self.assertRaisesRegex(RuntimeError, "changed during"):
            self.request()
        self.service.pain_scores_for_participant.assert_called_once()
        self.api.connections.close_all.assert_called_once()

    def test_real_dispatch_requires_authentication_and_access_even_for_cached_result(self):
        self.assertIn(self.request(authenticated=False).status_code, (401, 403))
        self.permission = False
        self.assertEqual(self.request().status_code, 403)
        self.jobs.assert_not_called()

    def test_invalid_controls_rejected_before_manifest_and_enqueue(self):
        response = self.request({'ParticipantId': self.person.uid, 'NBatches': 100000}, operation='queryStimOptimizer')
        self.assertEqual(response.status_code, 400)
        self.jobs.assert_not_called()
        self.api.AnalysisData.input_manifest.assert_not_called()

    def test_deidentified_response_and_permission_cache_separation(self):
        full = self.request()
        first_identity = self.jobs.call_args.args[0]
        self.assertEqual(full.data['participant'], 'SYN42')
        self.permission = {'Deidentified': True}
        limited = self.request()
        self.assertEqual(limited.status_code, 200)
        self.assertNotIn('SYN42', json.dumps(limited.data))
        self.assertEqual(limited.data['participant'], self.person.uid)
        self.assertNotEqual(first_identity['permission'], self.jobs.call_args.args[0]['permission'])
        self.assertEqual(limited['Cache-Control'], 'no-store')

    def test_scientific_environment_changes_cache_identity(self):
        with patch.dict(os.environ, {'BRAVO_MAIN_BIPOLAR': 'LEFT_ZERO_THREE'}):
            self.request(); first = self.jobs.call_args.args[0]
        with patch.dict(os.environ, {'BRAVO_MAIN_BIPOLAR': 'RIGHT_ZERO_THREE'}):
            self.request(); second = self.jobs.call_args.args[0]
        self.assertNotEqual(first['scientific_environment'], second['scientific_environment'])

    def test_changed_snapshot_and_exceptions_do_not_become_success(self):
        self.api.AnalysisData.input_manifest.side_effect = [self.manifest, {'fingerprint': 'changed'}]
        with self.assertRaises(RuntimeError):
            self.request()
        self.service.pain_scores_for_participant.assert_not_called()
        self.api.AnalysisData.input_manifest.side_effect = lambda p: self.manifest
        self.service.pain_scores_for_participant.side_effect = RuntimeError('synthetic source failed')
        with self.assertRaises(RuntimeError):
            self.request()


class ServiceExceptionTests(unittest.TestCase):
    def test_scientific_service_failures_raise_instead_of_persisting_empty_success(self):
        for package, minimum in [('StimOptimizer', 2), ('ClosedLoopDeployment', 1)]:
            path = ROOT / 'modules' / package / 'bravo_service.py'
            tree = ast.parse(path.read_text())
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_for_participant')
            # Rendering can now report an explicit per-figure error while retaining a valid
            # scientific result. Canonical-input/model failures must still fail the whole job.
            # The renderer's structured, sanitized error contract has dedicated service tests.
            handlers = [node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)
                        and isinstance(node.type, ast.Name) and node.type.id == 'Exception'
                        and any(isinstance(child, ast.Raise) for child in ast.walk(node))]
            self.assertGreaterEqual(len(handlers), minimum)
            for handler in handlers:
                # Execute the actual branch against synthetic logging/exception globals.
                context = {'RuntimeError': RuntimeError, '_log': NS(exception=Mock()),
                           'log': NS(exception=Mock()), 'uid': 'synthetic', 'e': ValueError('private detail'),
                           'exc': ValueError('private detail')}
                with self.assertRaises(RuntimeError) as raised:
                    exec(compile(ast.Module(body=handler.body, type_ignores=[]), str(path), 'exec'), context)
                self.assertNotIn('private detail', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
