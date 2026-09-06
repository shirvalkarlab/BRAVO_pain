"""Mock-boundary tests of actual AnalysisData functions; no Django/database/source data access.

Compile production function bodies to isolate model queries. These do not replace the live
canonical-row comparison or the candidate Django/API integration gate.
"""
import ast
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import Mock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'modules/AnalysisData.py'


def production(context):
    tree = ast.parse(PATH.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    for node in tree.body:
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                continue
            for target in node.targets:
                context[target.id] = value
    context.update(hashlib=hashlib, json=json, Path=Path, pd=pd, re=re, __file__=str(PATH))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PATH), 'exec'), context)
    return NS(**{name: context[name] for name in ('canonical_pros', 'eligible_source_files', 'input_manifest')})


class Query(list):
    """Small queryset boundary fake implementing only filters used by the production adapter."""
    def _matches(self, row, filters):
        for expression, expected in filters.items():
            field, _, op = expression.partition('__')
            value = getattr(row, field, None)
            if op == 'in':
                accepted = value in expected
            elif op == 'isnull':
                accepted = (value is None) == expected
            elif op == 'startswith':
                accepted = str(value).startswith(expected)
            else:
                accepted = value == expected
            if not accepted:
                return False
        return True

    def filter(self, **filters):
        return Query(row for row in self if self._matches(row, filters))

    def exclude(self, **filters):
        return Query(row for row in self if not self._matches(row, filters))

    def order_by(self, *keys):
        return Query(sorted(self, key=lambda row: tuple(getattr(row, k) for k in keys)))

    def values_list(self, *keys):
        return [tuple(getattr(row, key) for key in keys) for row in self]


class CanonicalDataTests(unittest.TestCase):
    def setUp(self):
        self.person = NS(uid='patient', name='RCS08', institute='lab')
        self.processing = {'reviewed_sha256': 'a' * 64, 'pipeline': 'percept_analysis daily survey rules'}
        self.form = NS(uid='form', name='Daily approved', institute='lab', record_type='Managed daily',
                       record=[{'processing': self.processing, 'questions': [
                           {'type': 'score', 'variableName': 'nrs', 'text': 'NRS', 'min': 0, 'max': 10},
                           {'type': 'score', 'variableName': 'vas', 'text': 'VAS', 'min': 0, 'max': 100}]}])
        self.rows = Query([
            NS(uid='row-b', source=self.form, source_id='form', participant=self.person, name='survey-B', date=1752778800.25, record=[[0, None]]),
            NS(uid='row-a', source=self.form, source_id='form', participant=self.person, name='survey-A', date=1752692400.5, record=[[7, 40]]),
        ])
        self.sources = Query([NS(uid='neural', owner=self.person, type='MedtronicJSON', hashed='h1', metadata={}),
                              NS(uid='quarantined', owner=self.person, type='MedtronicJSON', hashed='h2', metadata={'AnalysisExclusion': 'bench'}),
                              NS(uid='cache', owner=self.person, type='CachedResult', hashed='cache1', metadata={})])
        self.recordings = Query([NS(uid='rec', source_id='neural', type='MedtronicBrainSenseTimeDomain', date=1752692400, hashed='r1', metadata={}, adjusted_alignment=0, fs_scaling_factor=1, original=None),
                                 NS(uid='bad', source_id='quarantined', type='MedtronicBrainSenseTimeDomain', date=1752692400, hashed='bad', metadata={}, adjusted_alignment=0, fs_scaling_factor=1, original=None)])
        self.models = NS(SourceFile=NS(find_all=lambda **kw: self.sources.filter(**kw)),
                         ScaleForms=NS(find=Mock(return_value=self.form), objects=Query([self.form])),
                         ScaleRecord=NS(find_all=lambda **kw: self.rows.filter(**kw)),
                         Recording=NS(objects=self.recordings))
        self.api = production({'models': self.models})
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.policy = Path(self.temp.name) / 'policy.py'
        self.policy.write_text('implant = 123')
        self.oura_policy = Path(self.temp.name) / 'oura.csv'
        self.oura_policy.write_text('approved-window')
        modules = ModuleType('modules')
        modules.RCS08DataPolicy = NS(__file__=str(self.policy), applies_to=lambda p: p is not None and p.name == 'RCS08')
        self.revision = 'revision1'
        modules.ReportCache = NS(revision=lambda: self.revision)
        sync = ModuleType('modules.RCS08Sync')
        sync.REDCAP_FORM_NAME = self.form.name
        sync.REDCAP_RECORD_TYPE = self.form.record_type
        oura = ModuleType('modules.OURA.QualityControl')
        oura.VERSION = 'oura1'
        oura.POLICY_PATH = str(self.oura_policy)
        self.patches = patch.dict(sys.modules, {'modules': modules, 'modules.RCS08Sync': sync, 'modules.OURA.QualityControl': oura, 'modules.RCS08DataPolicy': modules.RCS08DataPolicy})
        self.patches.start()
        self.addCleanup(self.patches.stop)

    def test_canonical_identity_utc_and_values_exact(self):
        frame = self.api.canonical_pros(self.person)
        expected = self.rows.order_by('date', 'name')
        self.assertEqual(frame.record_uid.tolist(), [r.uid for r in expected])
        self.assertEqual(frame.source_record.tolist(), [r.name for r in expected])
        self.assertEqual(frame.source_form_uid.tolist(), ['form', 'form'])
        self.assertEqual(frame._pro_time_utc.dt.tz, None)
        self.assertEqual(str(frame.date_time_s1_daily.dt.tz), 'UTC')
        self.assertEqual([stamp.timestamp() for stamp in frame.date_time_s1_daily], [r.date for r in expected])
        self.assertEqual(frame.nrs.tolist(), [7, 0])
        self.assertEqual(frame.vas.iloc[0], 40)
        self.assertTrue(pd.isna(frame.vas.iloc[1]))
        self.assertEqual(frame.attrs['metrics'][0], {'key': 'nrs', 'label': 'NRS', 'range': [0, 10]})
        self.assertEqual(frame.attrs['processing'], self.processing)

    def test_historical_and_other_participant_rows_are_not_daily(self):
        self.rows.append(NS(uid='historical', source=NS(uid='history'), source_id='history', participant=self.person, name='x', date=1, record=[[99, 99]]))
        self.rows.append(NS(uid='foreign', source=self.form, source_id='form', participant=NS(uid='other'), name='x', date=1, record=[[99, 99]]))
        self.assertEqual(len(self.api.canonical_pros(self.person)), 2)
        self.assertTrue(self.api.canonical_pros(NS(name='Other')).empty)

    def test_missing_provenance_and_mapping_refused(self):
        self.form.record = []
        with self.assertRaisesRegex(ValueError, 'mapping'):
            self.api.canonical_pros(self.person)
        self.form.record = [{'questions': []}]
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.api.canonical_pros(self.person)

    def test_invalid_digest_duplicate_and_reserved_fields_refused(self):
        self.processing['reviewed_sha256'] = 'not-reviewed'
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.api.canonical_pros(self.person)
        self.processing['reviewed_sha256'] = 'a' * 64
        for key in ('nrs', 'record_uid', '_pro_time_utc', '', None):
            with self.subTest(key=key):
                self.form.record[0]['questions'][1]['variableName'] = key
                with self.assertRaisesRegex(ValueError, 'identifiers'):
                    self.api.canonical_pros(self.person)

    def test_extra_record_fields_refused(self):
        self.rows[0].record = [[0, None, 17]]
        with self.assertRaisesRegex(ValueError, 'mapping'):
            self.api.canonical_pros(self.person)

    def test_short_record_refused(self):
        self.rows[0].record = [[0]]
        with self.assertRaisesRegex(ValueError, 'mapping'):
            self.api.canonical_pros(self.person)

    def test_source_exclusion_is_enforced(self):
        self.assertEqual([s.uid for s in self.api.eligible_source_files(self.person)], ['neural', 'cache'])
        manifest = self.api.input_manifest(self.person)
        self.assertEqual(manifest['excluded_sources'], ['quarantined'])
        self.assertEqual(manifest['recordings'], 1)
        self.assertEqual(manifest['source_count'], 1)

    def test_manifest_stable_for_same_data_and_ignores_recomputable_cache(self):
        initial = self.api.input_manifest(self.person)['fingerprint']
        self.assertEqual(initial, self.api.input_manifest(self.person)['fingerprint'])
        self.sources[2].hashed = 'new-cache'
        self.assertEqual(initial, self.api.input_manifest(self.person)['fingerprint'])

    def test_frozen_model_content_invalidates_manifest(self):
        model = Path(self.temp.name) / 'Biomarkers/data/psd_lsb_models/RCS08.json'
        model.parent.mkdir(parents=True)
        model.write_text('{"version":1}')
        qc = Path(self.temp.name) / 'OURA/QualityControl.py'
        qc.parent.mkdir()
        qc.write_text('synthetic policy')
        self.api.input_manifest.__globals__['__file__'] = str(Path(self.temp.name) / 'AnalysisData.py')
        first = self.api.input_manifest(self.person)
        model.write_text('{"version":2}')
        second = self.api.input_manifest(self.person)
        self.assertNotEqual(first['model_hashes'], second['model_hashes'])
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])

    def test_unknown_recording_is_not_silently_loaded_as_neural(self):
        service_path = ROOT / 'modules/Biomarkers/bravo_service.py'
        tree = ast.parse(service_path.read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('_load_recordings', '_eligible_recordings', '_aligned_recording_payload', '_recording_alignment')]
        source = NS(uid='source')
        participant = NS(name='Example')
        recordings = Query([
            NS(uid='known', source=source, pointer='known-file', type='MedtronicBrainSenseTimeDomain', hashed='known', metadata={}),
            NS(uid='unknown', source=source, pointer='unknown-file', type='UnrecognizedSignal', hashed='unknown', metadata={}),
        ])
        loader = Mock(side_effect=lambda pointer, hashed: {'StartTime': 100, 'Data': [[0]]})
        context = dict(models=NS(Participant=NS(find=lambda **kw: participant), Recording=NS(find_all=lambda **kw: recordings.filter(**kw))),
                       _eligible_sources=lambda person: Query([source]), Database=NS(loadSourceFile=loader),
                       ThreadPoolExecutor=ThreadPoolExecutor, _loader_threads=lambda: 1, _log=Mock(), np=__import__('numpy'), CHRONIC_TYPES=['MedtronicChronicBrainSense'])
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(service_path), 'exec'), context)
        result = context['_load_recordings']('patient', ['MedtronicBrainSenseTimeDomain', 'MedtronicIndefiniteStream'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['RecordingType'], 'MedtronicBrainSenseTimeDomain')
        loader.assert_called_once_with('known-file', 'known')

    def test_source_record_alignment_scaling_processing_and_policy_changes_invalidate(self):
        mutations = [lambda: setattr(self.sources[0], 'hashed', 'h-new'),
                     lambda: setattr(self.recordings[0], 'hashed', 'r-new'),
                     lambda: setattr(self.recordings[0], 'adjusted_alignment', 2),
                     lambda: setattr(self.recordings[0], 'fs_scaling_factor', 1.01),
                     lambda: self.recordings[0].metadata.update({'kind': 'changed'}),
                     lambda: self.processing.update({'reviewed_sha256': 'b' * 64}),
                     lambda: self.rows[0].record[0].__setitem__(0, 1),
                     lambda: setattr(self.rows[0], 'date', self.rows[0].date + 1),
                     lambda: self.policy.write_text('implant = 456'),
                     lambda: self.oura_policy.write_text('changed-window')]
        previous = self.api.input_manifest(self.person)['fingerprint']
        for mutation in mutations:
            mutation()
            current = self.api.input_manifest(self.person)['fingerprint']
            self.assertNotEqual(previous, current)
            previous = current


if __name__ == '__main__':
    unittest.main()
