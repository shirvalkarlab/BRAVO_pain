"""Synthetic checks of policy ownership and policy-aware report cache identity."""
import ast
from contextvars import ContextVar
from functools import wraps
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from filelock import FileLock, Timeout
from modules.RCS08DataPolicy import applies_to

ROOT = Path(__file__).resolve().parents[1]


def load_function(path, name, context):
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), context)
    return context[name]


class PolicyAssociationTests(unittest.TestCase):
    def setUp(self):
        self.owner = NS(uid='stable-owner', name='Renamed display')
        self.other = NS(uid='unrelated', name='Another participant')
        self.models = NS(SourceFile=Mock(), Participant=Mock())
        self.models.SourceFile.include.side_effect = lambda **kw: kw == {'owner': self.owner, 'type': 'RCS08SurveyAudit'}
        self.server = patch.dict(sys.modules, {'Server': NS(models=self.models)})
        self.server.start()
        self.addCleanup(self.server.stop)

    def test_legacy_name_and_renamed_audit_owner_apply_but_unrelated_and_none_do_not(self):
        self.assertTrue(applies_to(NS(uid='legacy', name='RCS08')))
        self.assertTrue(applies_to(self.owner))
        self.assertFalse(applies_to(self.other))
        self.assertFalse(applies_to(None))

    def resolve(self, owners, create=False, named=None):
        self.models.Participant.find.side_effect = lambda **kw: named if 'name' in kw else self.owner
        self.models.SourceFile.objects.filter.return_value.values_list.return_value.distinct.return_value = owners
        resolve = load_function(ROOT/'modules/RCS08Sync.py', 'resolve_participant',
                                {'models': self.models, 'PARTICIPANT_NAME': 'RCS08', 'SyncError': RuntimeError})
        return resolve(create=create)

    def test_sync_resolves_renamed_unique_owner_without_creating_duplicate(self):
        self.assertIs(self.resolve(['stable-owner'], create=True), self.owner)
        self.models.Participant.assert_not_called()
        self.models.SourceFile.objects.filter.assert_called_once_with(type='RCS08SurveyAudit', owner__isnull=False)

    def test_sync_refuses_ambiguous_audit_owners_even_when_create_requested(self):
        with self.assertRaisesRegex(RuntimeError, 'Multiple participants'):
            self.resolve(['one', 'two'], create=True)
        self.models.Participant.assert_not_called()

    def test_sync_existing_name_keeps_legacy_resolution(self):
        named = NS(uid='legacy', name='RCS08')
        self.assertIs(self.resolve([], named=named), named)
        self.models.SourceFile.objects.filter.assert_not_called()

    def test_sync_missing_name_and_audit_raises_without_create(self):
        with self.assertRaisesRegex(RuntimeError, 'does not exist'):
            self.resolve([])

    def test_renamed_oura_loader_applies_qc_default_but_preserves_explicit_raw(self):
        raw = {'raw': True}
        clean = {'cleaned': True}
        qc = Mock(return_value=(clean, []))
        source = NS(pointer='synthetic', hashed='source-hash')
        self.models.SourceFile.find.return_value = source
        loader = load_function(ROOT/'modules/OURA/DataManager.py', 'loadOuraRingData',
                               {'models': self.models, 'Database': NS(loadSourceFile=Mock(return_value=raw))})
        with patch.dict(sys.modules, {'modules.OURA.QualityControl': NS(apply_quality_control=qc)}):
            self.assertEqual(loader(self.owner), clean)
            self.assertEqual(loader(self.owner, raw=True), raw)
            self.assertEqual(loader(self.other), raw)
        qc.assert_called_once_with(raw)

    def test_renamed_neural_import_still_quarantines_benchtop_source(self):
        source = NS(owner=self.owner, metadata={}, save=Mock())
        report = {'DeviceInformation': {'Final': {'DeviceName': 'Benchtop test'}}}
        decoder = load_function(ROOT/'modules/DataCurator.py', 'MedtronicPerceptJSONDecoder',
                                {'json': json, 'loadCacheFile': lambda source: json.dumps(report)})
        # This policy test isolates stored-file I/O; privacy has its own real
        # ingestion tests. The new privacy hook must still run for renamed owners.
        with patch('modules.PerceptPresentationPrivacy.deidentify_stored_source',
                   return_value=(json.dumps(report).encode(), [])) as sanitize:
            self.assertTrue(decoder(source, person=self.owner))
        sanitize.assert_called_once_with(source, "RCS08")
        self.assertIn('Benchtop', source.metadata['AnalysisExclusion'])
        self.assertIs(source.owner, self.owner)
        source.save.assert_called_once()


class PolicyCacheIdentityTests(unittest.TestCase):
    def test_policy_file_edit_invalidates_outer_and_nested_identity_without_global_revision_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'modules/OURA').mkdir(parents=True)
            (root/'config').mkdir()
            for path in (root/'modules/RCS08DataPolicy.py', root/'modules/OURA/QualityControl.py',
                         root/'config/rcs08_oura_exclusion_windows.csv'):
                path.write_text('first')
            cache = root/'cache'
            cache.mkdir()
            context = {'Path': Path, 'hashlib': hashlib, 'json': json,
                       '__file__': str(root/'modules/ReportCache.py'), 'wraps': wraps,
                       'VERSION': 'synthetic', 'MAX_AGE': None, 'gzip': gzip,
                       'directory': lambda: cache, 'revision': lambda: 'unchanged-input',
                       '_calculation_revision': ContextVar('synthetic-policy-cache', default=None),
                       '_warming': NS(get=lambda: False), 'refresh_in_progress': lambda: False,
                       'FileLock': FileLock, 'Timeout': Timeout,
                       'JSONRenderer': lambda: NS(render=lambda data: json.dumps(data).encode()),
                       '_response': lambda compressed, request, state: NS(data=json.loads(gzip.decompress(compressed)), cache=state)}
            identity = load_function(ROOT/'modules/ReportCache.py', 'analysis_policy_identity', context)
            before = identity()
            wrapper = load_function(ROOT/'modules/ReportCache.py', 'cached_report', context)
            nested_cache = {}
            identities = []
            def report(view, request):
                current = context['_calculation_revision'].get()
                identities.append(current)
                nested_cache.setdefault(current, {'generation': len(identities)})
                return NS(status_code=200, data=nested_cache[current])
            request = NS(data={'ParticipantId': 'synthetic', 'RequestType': 'RequestAll'},
                         user=NS(configuration={}), path='/synthetic')
            database = NS(checkAccessPermission=lambda *a, **k: True,
                          retrieveProcessingSettings=lambda config: ({}, {}))
            with patch.dict(sys.modules, {'modules': NS(Database=database)}):
                wrapped = wrapper(report)
                self.assertEqual(wrapped(None, request).data['generation'], 1)
                self.assertEqual(wrapped(None, request).cache, 'HIT')
                (root/'config/rcs08_oura_exclusion_windows.csv').write_text('other')
                self.assertNotEqual(before, identity())
                self.assertEqual(wrapped(None, request).data['generation'], 2)
                self.assertEqual(len(set(identities)), 2)
                self.assertTrue(all(item.startswith('unchanged-input:') for item in identities))
                self.assertIsNone(context['_calculation_revision'].get())


if __name__ == '__main__':
    unittest.main()
