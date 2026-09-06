"""Dependency-isolated execution of production functions against synthetic inputs.

Run with Python unittest; AST extraction avoids importing Django/ML or touching a
database. These exercise the actual function bodies, not a mirrored implementation.
"""
import ast
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def function(path, name, context, class_name=None):
    tree = ast.parse(path.read_text())
    nodes = tree.body
    if class_name:
        nodes = next(n for n in nodes if isinstance(n, ast.ClassDef) and n.name == class_name).body
    node = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    node.decorator_list = []
    context['__file__'] = str(path)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), context)
    return context[name]


class PipelineInputs(unittest.TestCase):
    def setUp(self):
        self.person = NS(uid='patient', name='Example')
        self.source = NS(owner=self.person, metadata={})
        self.original = NS(uid='input', type='MATFile', source=self.source,
                           hashed='hash-one', pointer='old', metadata={})
        self.saved = []
        self.payloads = {}
        def create(**kwargs):
            row = NS(**kwargs, uid='result-' + str(len(self.saved)), pointer=None, hashed=None)
            row.save = lambda: self.saved.append(row)
            return row
        def find(**kwargs):
            return next((r for r in self.saved if r.type == kwargs.get('type') and r.metadata == kwargs.get('metadata')), None)
        self.recordings = Mock(side_effect=create)
        self.recordings.find.side_effect = find
        self.recordings.find_all.side_effect = lambda **kwargs: [self.original] if kwargs.get('source__owner') == self.person else []
        self.database = NS(retrieveProcessingSettings=Mock(return_value=({'filter': 'default'}, {})),
                           loadSourceFile=Mock(return_value={'StartTime': 100, 'Data': [1, 0, None]}),
                           saveSourceFile=Mock(side_effect=self.save_payload))
        self.cache = ModuleType('modules')
        self.cache.ReportCache = NS(VERSION='v1', revision=Mock(return_value='neural-one'))
        self.patched_modules = patch.dict(sys.modules, {'modules': self.cache})
        self.patched_modules.start()
        self.addCleanup(self.patched_modules.stop)
        self.fresh = Mock(return_value=[{'StartTime': 200, 'Data': [7, 0, None]}])
        self.context = dict(models=NS(Participant=NS(find=Mock(return_value=self.person)), Recording=self.recordings,
                                    SourceFile=NS(find=Mock(return_value=self.source)), DBSDevice=NS(find_all=Mock(return_value=[]))),
                            Database=self.database, cachedChronicActivity=self.fresh,
                            ChronicBrainSense=NS(revertChronicActivityFormat=lambda row: copy.deepcopy(row)),
                            pathlib=__import__('pathlib'), hashlib=hashlib, pickle=pickle, os=os, copy=copy,
                            np=NS(isfinite=math.isfinite), DATABASE_PATH='/synthetic/',
                            _custom_pipeline_policy_identity=lambda participant: {'ReportVersion': self.cache.ReportCache.VERSION},
                            _custom_annotation_identity=Mock(return_value='annotations-one'),
                            StaleAnalysisError=ValueError,
                            handleProcessingNode=Mock(side_effect=lambda node, participant, uid: {**node, 'result': uid}))
        self.run_pipeline = function(ROOT/'modules/DataAnalysis.py', 'processCustomizedPipeline', self.context)
        self.analysis = NS(uid='analysis', metadata={'ParticipantId': 'patient', 'Nodes': [[
            {'name': 'Input', 'type': 'TimeDomain', 'data': [{'Id': 'input', 'Alignment': 0}]},
            {'data': {'Type': 'Synthetic processing'}}]]}, save=Mock())

    def save_payload(self, payload, path):
        self.payloads[path] = copy.deepcopy(payload)
        return hashlib.sha256(pickle.dumps(payload)).hexdigest()

    def test_identical_inputs_reuse_but_hash_alignment_policy_and_config_changes_recompute(self):
        self.run_pipeline(self.analysis, {'filter': 'a'})
        self.run_pipeline(self.analysis, {'filter': 'a'})
        self.assertEqual(len(self.saved), 1)
        self.original.hashed = 'hash-two'
        self.run_pipeline(self.analysis, {'filter': 'a'})
        self.assertEqual(len(self.saved), 2)
        self.analysis.metadata['Nodes'][0][0]['data'][0]['Alignment'] = 5
        self.run_pipeline(self.analysis, {'filter': 'a'})
        self.assertEqual(len(self.saved), 3)
        self.assertEqual(self.payloads[self.saved[-1].pointer]['Data'][0]['StartTime'], 105)
        self.cache.ReportCache.VERSION = 'v2'
        self.run_pipeline(self.analysis, {'filter': 'a'})
        self.assertEqual(len(self.saved), 4)
        self.run_pipeline(self.analysis, {'filter': 'b'})
        self.assertEqual(len(self.saved), 5)
        self.assertEqual(self.database.loadSourceFile.return_value['StartTime'], 100)

    def test_chronic_uses_returned_fresh_payload_not_obsolete_file_and_refreshes_when_content_changes(self):
        self.original.type = 'MedtronicChronicNeuralActivity'
        self.run_pipeline(self.analysis, {'filter': 'common'})
        self.fresh.assert_called_once_with(self.person, [], {'filter': 'common'})
        self.database.loadSourceFile.assert_not_called()
        self.assertEqual(self.payloads[self.saved[0].pointer]['Data'][0]['StartTime'], 200)
        self.fresh.return_value = [{'StartTime': 300, 'Data': [8, None]}]
        self.run_pipeline(self.analysis, {'filter': 'common'})
        self.assertEqual(len(self.saved), 2)
        self.assertEqual(self.payloads[self.saved[-1].pointer]['Data'][0]['StartTime'], 300)

    def test_foreign_or_deleted_recording_is_rejected_before_load(self):
        self.recordings.find_all.side_effect = lambda **kwargs: []
        with self.assertRaisesRegex(ValueError, 'belong'):
            self.run_pipeline(self.analysis, {})
        self.database.loadSourceFile.assert_not_called()

    def test_excluded_source_is_rejected_before_load(self):
        self.original.source.metadata['AnalysisExclusion'] = 'reviewed exclusion'
        with self.assertRaisesRegex(ValueError, 'excluded'):
            self.run_pipeline(self.analysis, {})
        self.database.loadSourceFile.assert_not_called()

    def test_nonfinite_alignment_rejected(self):
        self.analysis.metadata['Nodes'][0][0]['data'][0]['Alignment'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite'):
            self.run_pipeline(self.analysis, {})

    def test_chronic_revision_change_during_preparation_does_not_publish_input(self):
        self.original.type = 'MedtronicChronicNeuralActivity'
        self.cache.ReportCache.revision.side_effect = ['before', 'after']
        with self.assertRaisesRegex(ValueError, 'changed during preparation'):
            self.run_pipeline(self.analysis, {})
        self.database.saveSourceFile.assert_not_called()

    def test_default_config_preserves_existing_direct_call(self):
        self.run_pipeline(self.analysis)
        self.database.retrieveProcessingSettings.assert_called_once_with({})
        self.assertEqual(self.saved[0].metadata['ProcessingConfiguration'], {'filter': 'default'})

    def test_annotation_dependent_pipeline_recomputes_when_annotations_change(self):
        self.analysis.metadata['Nodes'][0][1]['data']['Type'] = 'Epoch by Annotations'
        self.run_pipeline(self.analysis, {})
        self.assertEqual(self.saved[0].metadata['AnnotationIdentity'], 'annotations-one')
        self.context['_custom_annotation_identity'].return_value = 'annotations-two'
        self.run_pipeline(self.analysis, {})
        self.assertEqual(len(self.saved), 2)
        self.assertEqual(self.saved[1].metadata['AnnotationIdentity'], 'annotations-two')


class ManagedSurveySubmission(unittest.TestCase):
    def submit(self, record_type):
        form = NS(short_link='form', record_type=record_type)
        rel = NS(record=form, participant=NS(uid='patient'))
        create = Mock()
        context = dict(models=NS(ParticipantLinkRel=NS(find=Mock(return_value=rel)),
                                 ScaleForms=NS(find=Mock(return_value=form)), ScaleRecord=NS(create=create)),
                       get_or_none=lambda func: func, sanitize_input=lambda *a, **k: True, json=json,
                       Response=lambda status, data=None: NS(status_code=status, data=data))
        post = function(ROOT/'Server/APIs/EventAnnotationHandler.py', 'post', context, 'QuerySurveyForms')
        response = post(None, NS(data={'RequestType': 'SubmitForm', 'FormId': 'form', 'Version': 1,
                                       'Date': 100, 'Passcode': 'synthetic', 'FormResults': [[1]]}))
        return response, create

    def test_managed_types_cannot_append_unreviewed_records(self):
        for kind in ('REDCap API Sync', 'Redcap Linked Survey'):
            with self.subTest(kind=kind):
                response, create = self.submit(kind)
                self.assertEqual(response.status_code, 400)
                create.assert_not_called()

    def test_normal_form_submission_is_unchanged(self):
        response, create = self.submit('Survey')
        self.assertEqual(response.status_code, 200)
        create.assert_called_once()


if __name__ == '__main__':
    unittest.main()
