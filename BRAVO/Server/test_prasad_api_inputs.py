"""Mock-boundary tests of the actual PrasadAnalysis request method and snapshot closure.

The post body is compiled directly from production with its CSRF decorator omitted. The optional
DRF test exercises IsAuthenticated with the real APIView dispatch when Django is configured.
No model/database, background worker, participant data, or network is used by these tests.
"""
import ast
import copy
import importlib
import json
import math
import os
import re
from pathlib import Path
import sys
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'Server/APIs/PrasadAnalysis.py'


class Response(dict):
    def __init__(self, data=None, status=200):
        self.data = data
        self.status_code = status


def load_post(context):
    tree = ast.parse(PATH.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('OPERATIONS', 'FORBIDDEN_INPUTS'):
                    context[target.id] = ast.literal_eval(node.value)
    context.update(os=os, re=re)
    helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"validated_controls", "deidentified_result"}]
    exec(compile(ast.Module(body=helpers, type_ignores=[]), str(PATH), "exec"), context)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ResearchAnalysis')
    post = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'post'))
    post.decorator_list = []
    exec(compile(ast.Module(body=[post], type_ignores=[]), str(PATH), 'exec'), context)
    return context['post']


class ResearchRequestTests(unittest.TestCase):
    def setUp(self):
        self.person = NS(uid='patient', name='RCS08')
        self.manifest = {'fingerprint': 'approved-1', 'participant_uid': 'patient'}
        self.analysis = NS(input_manifest=Mock(side_effect=lambda p: copy.deepcopy(self.manifest)))
        self.config = {'filter': 'original'}
        self.database = NS(checkAccessPermission=Mock(return_value={'Deidentified': False}),
                           retrieveProcessingSettings=Mock(side_effect=lambda c: (copy.deepcopy(self.config), {})))
        self.models = NS(Participant=NS(find=Mock(return_value=self.person)))
        self.service = NS(pain_scores_for_participant=Mock(return_value={'metrics': [{'key': 'nrs'}]}))
        self.importer = NS(import_module=Mock(return_value=self.service))
        self.jobs = ModuleType('modules.AnalysisJobs')
        self.jobs.get_or_start = Mock(return_value=(202, {'state': 'running'}))
        self.patched = patch.dict(sys.modules, {'modules.AnalysisJobs': self.jobs})
        self.patched.start()
        self.addCleanup(self.patched.stop)
        self.context = dict(Response=Response, math=math, json=json, AnalysisData=self.analysis,
                            Database=self.database, models=self.models, analysis_code_fingerprint=lambda: 'code-1',
                            importlib=self.importer, json_compliant_handler=lambda x: x,
                            close_old_connections=Mock(), connections=NS(close_all=Mock()))
        self.post = load_post(self.context)
        self.user = NS(configuration={'ActiveStudy': 'study'}, is_authenticated=True)

    def request(self, data=None, operation='queryPainScores'):
        return self.post(NS(operation=operation), NS(data={'ParticipantId': 'patient'} if data is None else data, user=self.user))

    def test_nonobject_missing_and_nonstr_participant_rejected(self):
        for body in ([], 'invalid', {}, {'ParticipantId': 3}):
            with self.subTest(body=body):
                self.assertEqual(self.request(body).status_code, 400)
        self.database.checkAccessPermission.assert_not_called()
        self.jobs.get_or_start.assert_not_called()

    def test_forbidden_canonical_overrides_rejected_without_job(self):
        for key in ('ProcessedPRO', 'RedcapFieldMap', 'PtConfig', 'RedcapRecordId', 'Stages', 'Participant', '_internal'):
            with self.subTest(key=key):
                self.assertEqual(self.request({'ParticipantId': 'patient', key: []}).status_code, 400)
        self.jobs.get_or_start.assert_not_called()

    def test_missing_channel_and_invalid_frequency_rejected(self):
        operation = 'queryBandValidation'
        self.assertEqual(self.request({'ParticipantId': 'patient'}, operation).status_code, 400)
        for value in (-1, 0, float('nan'), float('inf'), {}, 'not a number'):
            with self.subTest(value=value):
                body = {'ParticipantId': 'patient', 'Channel': 'ZERO_THREE_RIGHT', 'CenterHz': value}
                self.assertEqual(self.request(body, operation).status_code, 400)
        self.assertEqual(self.request({'ParticipantId': 'patient', 'Channel': [], 'CenterHz': 20}, operation).status_code, 400)
        self.jobs.get_or_start.assert_not_called()

    def test_participant_access_enforced_before_data_loading(self):
        self.database.checkAccessPermission.return_value = False
        response = self.request()
        self.assertEqual(response.status_code, 403)
        self.database.checkAccessPermission.assert_called_once_with(self.user, 'patient', study_uid='study')
        self.analysis.input_manifest.assert_not_called()
        self.jobs.get_or_start.assert_not_called()

    def test_deleted_participant_rejected(self):
        self.models.Participant.find.return_value = None
        self.assertEqual(self.request().status_code, 404)
        self.jobs.get_or_start.assert_not_called()

    def test_processing_and_dataset_identity_are_both_cache_inputs(self):
        response = self.request()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response['Retry-After'], '3')
        first = copy.deepcopy(self.jobs.get_or_start.call_args.args[0])
        self.config['filter'] = 'changed'
        self.request()
        second = copy.deepcopy(self.jobs.get_or_start.call_args.args[0])
        self.assertNotEqual(first, second)
        self.manifest['fingerprint'] = 'approved-2'
        self.request()
        third = self.jobs.get_or_start.call_args.args[0]
        self.assertNotEqual(second, third)
        self.assertEqual(third['input'], 'approved-2')
        self.assertEqual(third['code'], 'code-1')
        self.assertEqual(third['request'], {'ParticipantId': 'patient'})

    def test_success_uses_service_and_stamps_manifest(self):
        self.request()
        compute = self.jobs.get_or_start.call_args.args[1]
        result = compute()
        self.importer.import_module.assert_called_once_with('modules.Biomarkers.bravo_service')
        self.service.pain_scores_for_participant.assert_called_once_with({'ParticipantId': 'patient'})
        self.assertEqual(result['InputManifest']['fingerprint'], 'approved-1')
        self.assertEqual(result['InputManifest']['analysis_code'], 'code-1')
        self.context['connections'].close_all.assert_called_once()

    def test_changed_input_before_compute_refuses_old_snapshot(self):
        self.request()
        compute = self.jobs.get_or_start.call_args.args[1]
        self.manifest['fingerprint'] = 'changed'
        with self.assertRaisesRegex(RuntimeError, 'changed before'):
            compute()
        self.importer.import_module.assert_not_called()
        self.context['connections'].close_all.assert_called_once()

    def test_changed_input_during_compute_refuses_mixed_snapshot(self):
        self.request()
        def service(arguments):
            self.manifest['fingerprint'] = 'changed'
            return {'metrics': []}
        self.service.pain_scores_for_participant.side_effect = service
        with self.assertRaisesRegex(RuntimeError, 'changed during'):
            self.jobs.get_or_start.call_args.args[1]()
        self.context['connections'].close_all.assert_called_once()

    def test_all_imported_operations_have_required_control_definitions(self):
        operations = self.context['OPERATIONS']
        self.assertEqual(len(operations), 13)
        self.assertEqual(operations['queryStimOptimizer'][:2], ('StimOptimizer', 'run_for_participant'))
        for name, (package, function, required) in operations.items():
            self.assertIn(package, ('Biomarkers', 'StimOptimizer', 'ClosedLoopDeployment'))
            self.assertTrue(function)
            self.assertIsInstance(required, tuple)

    def test_authentication_permission_declared_and_real_dispatch_when_available(self):
        tree = ast.parse(PATH.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ResearchAnalysis')
        permissions = next(n for n in cls.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'permission_classes' for t in n.targets))
        self.assertEqual(ast.unparse(permissions.value), '[IsAuthenticated]')
        try:
            from django.conf import settings
            if not settings.configured:
                self.skipTest('Django not configured; authentication declaration checked, live dispatch remains integration gate')
            from rest_framework.views import APIView
            from rest_framework.permissions import IsAuthenticated
            from rest_framework.test import APIRequestFactory
        except ImportError:
            self.skipTest('Django/DRF unavailable; authentication declaration checked, live dispatch remains integration gate')
        def forbidden_post(view, request):
            raise AssertionError('Unauthenticated request reached analysis method')
        view = type('AuthBoundary', (APIView,), {'permission_classes': [IsAuthenticated], 'post': forbidden_post})
        response = view.as_view()(APIRequestFactory().post('/analysis', {'ParticipantId': 'patient'}, format='json'))
        self.assertIn(response.status_code, (401, 403))


if __name__ == '__main__':
    unittest.main()
