"""Focused synthetic tests of the existing BRAVO analysis/survey entry points."""
import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from Server.test_analysis_input_consistency import function

ROOT = Path(__file__).resolve().parents[1]


class ReviewRequiredError(ValueError):
    pass


def response(status=200, data=None):
    return NS(status_code=status, data=data)


class SurveyEntryGuards(unittest.TestCase):
    def test_managed_definition_update_is_rejected_but_manual_form_can_update(self):
        form = NS(record_type='REDCap API Sync', institute=NS(has_permission=lambda *args: True), update_version=Mock())
        context = {'models': NS(ScaleForms=NS(find=lambda **kw: form)), 'json': json,
                   'Response': response, 'get_or_none': lambda f: f, 'sanitize_input': lambda *args, **kw: True}
        post = function(ROOT/'Server/APIs/EventAnnotationHandler.py', 'post', context, 'SetSurveyForms')
        request = NS(user=NS(), data={'RequestType': 'Update', 'FormLink': 'synthetic', 'FormContent': []})
        self.assertEqual(post(None, request).status_code, 400)
        form.update_version.assert_not_called()
        form.record_type = 'Survey'
        form.get_info = lambda: {}
        self.assertEqual(post(None, request).status_code, 200)
        form.update_version.assert_called_once_with([])

    def test_reviewed_participant_legacy_link_fails_before_network_while_other_participant_keeps_behavior(self):
        requester = Mock()
        requester.post.return_value.json.return_value = [{'time': '2025-01-02T12:00:00+00:00'}]
        context = {'requests': requester, 'datetime': datetime, 'ReviewRequiredError': ReviewRequiredError}
        function(ROOT/'modules/SurveyForms/RedcapForm.py', 'require_approved_link', context)
        load = function(ROOT/'modules/SurveyForms/RedcapForm.py', 'queryRedcapFormRecords', context)
        form = NS(record_type='Redcap Linked Survey', record={'RedcapURL': 'unused', 'RedcapToken': 'synthetic',
                  'FieldMapping': [{'questions': [{'type': 'redcapForm', 'text': 'Time', 'value': 'time'}]}]})
        with patch.dict(sys.modules, {'modules.RCS08DataPolicy': NS(applies_to=lambda participant: participant.uid == 'reviewed')}):
            with self.assertRaises(ReviewRequiredError):
                load(NS(uid='reviewed'), form, 'id')
            requester.post.assert_not_called()
            self.assertEqual(len(load(NS(uid='unrelated'), form, 'id')), 1)
            requester.post.assert_called_once()

    def test_table_returns_explicit_review_needed_response(self):
        form = NS(record_type='Redcap Linked Survey')
        person = NS(uid='reviewed')
        models = NS(ScaleForms=NS(find=lambda **kw: form), Participant=NS(find=lambda **kw: person),
                    ParticipantLinkRel=NS(find=lambda **kw: NS(link_code='synthetic')))
        context = {'models': models, 'Database': NS(checkAccessPermission=lambda *a, **kw: True),
                   'get_or_none': lambda f: f, 'sanitize_input': lambda *a, **kw: True, 'Response': response,
                   'RedcapForm': NS(ReviewRequiredError=ReviewRequiredError,
                                   queryRedcapFormRecords=Mock(side_effect=ReviewRequiredError('review this link')))}
        post = function(ROOT/'Server/APIs/EventAnnotationHandler.py', 'post', context, 'QueryParticipantSurveyRecords')
        result = post(None, NS(user=NS(configuration={}), data={'RequestType': 'RequestRecords', 'ParticipantId': 'reviewed', 'FormId': 'form'}))
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data['status'], 'review_required')

    def test_timeline_retains_managed_scores_and_explicit_legacy_warning_without_raw_values(self):
        legacy = NS(uid='legacy', name='Unreviewed link', record_type='Redcap Linked Survey')
        managed = NS(uid='managed', name='Reviewed daily', record_type='REDCap API Sync',
                     record=[{'questions': [{'type': 'score', 'text': 'NRS', 'show': True}]}])
        models = NS(Participant=NS(find=lambda **kw: NS(uid='reviewed')), DBSDevice=NS(find_all=lambda **kw: []),
                    SourceFile=NS(include=lambda **kw: False), Recording=NS(include=lambda **kw: False),
                    ParticipantLinkRel=NS(find_all=lambda **kw: [NS(record=legacy, link_code='synthetic'), NS(record=managed)]),
                    ScaleRecord=NS(find_all=lambda **kw: [NS(get_info=lambda: {'Date': 100, 'Result': [[0]]})]))
        context = {'models': models, 'eligible_source_files': lambda participant: [],
                   'Event': NS(queryDBSEvents=lambda *a, **kw: [], queryAnnotations=lambda *a: []),
                   'uniqueListOfDicts': lambda values, keys: values,
                   'RedcapForm': NS(ReviewRequiredError=ReviewRequiredError,
                                   queryRedcapFormRecords=Mock(side_effect=ReviewRequiredError('review needed')))}
        function(ROOT/'modules/DataAnalysis.py', 'storedSurveyTimeline', context)
        timeline = function(ROOT/'modules/DataAnalysis.py', 'queryChronicTimeline', context)
        data, annotations = timeline('reviewed', {})
        self.assertEqual(data[0]['Status'], 'review_required')
        self.assertEqual(data[0]['ChannelNames'], [])
        self.assertEqual(data[0]['Data'], [])
        self.assertEqual(data[1]['Data'], [[0]])
        self.assertEqual(annotations, [])


class SourceAndResultGuards(unittest.TestCase):
    def test_explicit_empty_eligible_sources_do_not_fall_back_to_excluded_event_sources(self):
        source_lookup = Mock(return_value=['excluded-source'])
        event_lookup = Mock(return_value=[])
        models = NS(Participant=NS(find=lambda **kw: NS(uid='synthetic')),
                    SourceFile=NS(find_all=source_lookup), DBSEvent=NS(find_all=event_lookup))
        query = function(ROOT/'modules/Event.py', 'queryDBSEvents', {'models': models})
        self.assertEqual(query('synthetic', source_files=[]), [])
        source_lookup.assert_not_called()
        self.assertEqual(event_lookup.call_args.kwargs['source__in'], [])
        eligible = Mock(return_value=['eligible-source'])
        with patch.dict(sys.modules, {'modules.AnalysisData': NS(eligible_source_files=eligible)}):
            self.assertEqual(query('synthetic'), [])
        eligible.assert_called_once()
        source_lookup.assert_not_called()
        self.assertEqual(event_lookup.call_args.kwargs['source__in'], ['eligible-source'])

    def test_direct_recording_analysis_rejects_excluded_source(self):
        recording = NS(source=NS(metadata={'AnalysisExclusion': 'benchtop'}))
        context = {'models': NS(Recording=NS(find=lambda **kw: recording))}
        get = function(ROOT/'modules/DataAnalysis.py', '_analysis_recording', context)
        with self.assertRaisesRegex(ValueError, 'excluded'):
            get('excluded')
        recording.source.metadata = {}
        self.assertIs(get('eligible'), recording)

    def test_neural_inventory_uses_only_eligible_sources(self):
        class Sources(list):
            def exclude(self, uid__in):
                return Sources(s for s in self if s.uid not in uid__in)
        sources = Sources([NS(uid='good', metadata={}), NS(uid='excluded', metadata={'AnalysisExclusion': 'reviewed'})])
        recordings = Mock(return_value=[])
        context = {'models': NS(SourceFile=NS(find_all=lambda **kw: sources),
                               Participant=NS(find=lambda **kw: NS(uid='synthetic')),
                               DBSDevice=NS(find_all=lambda **kw: []), Recording=NS(find_all=recordings))}
        function(ROOT/'modules/AnalysisData.py', 'eligible_source_files', context)
        inventory = function(ROOT/'modules/DataAnalysis.py', 'queryAllRecordings', context)
        inventory('synthetic', 'Timeseries')
        self.assertEqual([s.uid for s in recordings.call_args.kwargs['source__in']], ['good'])
        self.assertEqual(len(sources), 2)

    def setup_freshness(self):
        source = NS(owner=NS(uid='synthetic'), metadata={})
        original = NS(uid='raw', type='MATFile', hashed='hash', source=source)
        root = NS(uid='input', original_id=None, source=source, source_id='source', metadata={
            'InputIdentity': [{'Id': 'raw', 'Hash': 'hash'}], 'PolicyIdentity': {'v': 1}, 'NeuralRevision': 'one'})
        result = NS(uid='output', original_id='input', original=root, source=source, source_id='source')
        cache = NS(revision=lambda name: 'one')
        context = {'models': NS(Recording=NS(find_all=Mock(return_value=[original]))),
                   '_custom_pipeline_policy_identity': lambda participant: {'v': 1}, 'StaleAnalysisError': ValueError}
        check = function(ROOT/'modules/DataAnalysis.py', 'require_current_analysis_output', context)
        return original, root, result, cache, context, check

    def test_saved_custom_output_refuses_changed_raw_hash_deleted_or_excluded_inputs_and_policy(self):
        original, root, result, cache, context, check = self.setup_freshness()
        with patch.dict(sys.modules, {'modules': NS(ReportCache=cache)}):
            check(result)
            original.hashed = 'changed'
            with self.assertRaisesRegex(ValueError, 'rerun'): check(result)
            original.hashed = 'hash'
            original.source.metadata['AnalysisExclusion'] = 'reviewed'
            with self.assertRaises(ValueError): check(result)
            original.source.metadata = {}
            root.metadata['PolicyIdentity'] = {'v': 0}
            with self.assertRaises(ValueError): check(result)
            root.metadata['PolicyIdentity'] = {'v': 1}
            context['models'].Recording.find_all.return_value = []
            with self.assertRaises(ValueError): check(result)

    def test_saved_chronic_output_refuses_neural_sync_revision_and_untracked_legacy_output(self):
        original, root, result, cache, context, check = self.setup_freshness()
        original.type = 'MedtronicChronicNeuralActivity'
        with patch.dict(sys.modules, {'modules': NS(ReportCache=cache)}):
            check(result)
            cache.revision = lambda name: 'after-sync'
            with self.assertRaisesRegex(ValueError, 'rerun'): check(result)
            root.metadata = {}
            with self.assertRaises(ValueError): check(result)

    def test_annotation_dependent_saved_output_refuses_edited_annotations(self):
        original, root, result, cache, context, check = self.setup_freshness()
        root.metadata['AnnotationIdentity'] = 'before'
        context['_custom_annotation_identity'] = lambda participant: 'after'
        with patch.dict(sys.modules, {'modules': NS(ReportCache=cache)}):
            with self.assertRaisesRegex(ValueError, 'rerun'): check(result)

    def test_saved_output_api_returns409_and_keeps_participant_scope(self):
        find = Mock(return_value=NS(metadata={'Nodes': [[{'result': 'result-id'}]]}))
        context = {'models': NS(Analysis=NS(find=find)), 'Database': NS(checkAccessPermission=lambda *a, **kw: True),
                   'get_or_none': lambda f: f, 'sanitize_input': lambda *a, **kw: True, 'Response': response,
                   'DataAnalysis': NS(StaleAnalysisError=ValueError, extractAnalysisOutput=Mock(side_effect=ValueError('Please rerun the analysis.')))}
        post = function(ROOT/'Server/APIs/DataAnalysis.py', 'post', context, 'QueryCustomizedAnalysis')
        result = post(None, NS(user=NS(configuration={}), data={'RequestType': 'AnalysisOutput', 'ParticipantId': 'patient',
                           'AnalysisId': 'analysis', 'ResultId': 'result-id'}))
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data['status'], 'stale')
        self.assertEqual(find.call_args.kwargs['metadata__ParticipantId'], 'patient')


if __name__ == '__main__':
    unittest.main()
