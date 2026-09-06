"""Availability through the installed module and real disposable Django querysets.

Only stored sensor-file decoding and optional model discovery are boundaries;
participant/source ownership, exclusions, dates, forms and aggregation use real ORM.
"""
from unittest.mock import patch

import numpy as np
from django.test import TestCase

from Server import models
from modules import FeatureAvailability
from modules.RCS08DataPolicy import IMPLANT_DAY
from modules.RCS08Sync import REDCAP_FORM_NAME, REDCAP_RECORD_TYPE


class FeatureAvailabilityRuntimeTests(TestCase):
    def setUp(self):
        institute = models.Institute.objects.create(name='Synthetic validation institute')
        self.participant = models.Participant.objects.create(name='Renamed synthetic participant', institute=institute)
        self.other = models.Participant.objects.create(name='Other synthetic participant', institute=institute)
        models.SourceFile.objects.create(owner=self.participant, type='RCS08SurveyAudit')
        self.source = models.SourceFile.objects.create(owner=self.participant, type='MedtronicJSON')
        self.excluded = models.SourceFile.objects.create(owner=self.participant, type='MedtronicJSON',
            metadata={'AnalysisExclusion': 'Synthetic bench source'})
        self.foreign = models.SourceFile.objects.create(owner=self.other, type='MedtronicJSON')
        self.form = models.ScaleForms.objects.create(institute=institute, name=REDCAP_FORM_NAME,
            record_type=REDCAP_RECORD_TYPE, record=[{'processing': {'reviewed_sha256': 'a' * 64},
                'questions': [{'type': 'score', 'variableName': 'nrs', 'text': 'NRS', 'min': 0, 'max': 10}]}])
        models.ScaleRecord.objects.create(participant=self.participant, source=self.form,
            date=IMPLANT_DAY + 100, name='synthetic-survey', record=[[0]])
        self.model_patch = patch('modules.DataAnalysis.machineLearningAvailability', return_value={'Native beta': True})
        self.model_patch.start()
        self.addCleanup(self.model_patch.stop)

    def test_real_querysets_exclude_bench_foreign_and_preimplant_neural_but_keep_sensor_rows(self):
        for source, date in [(self.source, IMPLANT_DAY), (self.source, IMPLANT_DAY - 1),
                             (self.excluded, IMPLANT_DAY + 1), (self.foreign, IMPLANT_DAY + 1)]:
            models.Recording.objects.create(source=source, type='MedtronicBrainSenseSurvey', date=date)
            models.Therapy.objects.create(source=source, date=date)
            models.DBSEvent.objects.create(source=source, date=date)
        models.Annotation.objects.create(owner=self.participant, type='ChronicCustomEvent', source=None)
        models.Annotation.objects.create(owner=self.participant, type='ChronicCustomEvent', source=self.excluded)
        models.Annotation.objects.create(owner=self.participant, type='ChronicCustomEvent', source=self.foreign)
        for source_type in ('OuraRingAPISource', 'FitbitWebAPISource', 'GoogleHealthSource'):
            models.SourceFile.objects.create(owner=self.participant, type=source_type)
        oura = {'Sleep': [{'StartTime': IMPLANT_DAY - 100, 'Data': [[0]], 'Missing': [[0]]}]}
        with patch('modules.OURA.DataManager.loadOuraRingData', return_value=oura), \
             patch('modules.Fitbit.DataManager.loadFitbitData', side_effect=OSError('synthetic unreadable source')), \
             patch('modules.GoogleHealth.DataQuery.loadGoogleHealthData', return_value={'Daily': [{'Metadata': {'NoData': True}}]}), \
             self.assertLogs('modules.FeatureAvailability', level='ERROR'):
            result = FeatureAvailability.for_participant(self.participant)
        self.assertEqual(result['nerual-activity-snapshot']['count'], 1)
        self.assertEqual(result['therapyHistory']['count'], 1)
        self.assertEqual(result['events']['count'], 2)
        self.assertEqual(result['PainScores']['count'], 1)
        self.assertEqual(result['OuraRingDashboard']['count'], 1)
        self.assertTrue(result['OuraRingDashboard']['available'])
        self.assertEqual(result['FitbitDashboard']['kind'], 'unknown')
        self.assertFalse(result['FitbitDashboard']['available'])
        self.assertEqual(result['GoogleHealthDashboard']['reason'], 'No Google Health data')
        self.assertTrue(result['stimOptimizer']['available'])

    def test_unrelated_participant_has_no_inherited_implant_date_or_sensor_calls(self):
        models.Recording.objects.create(source=self.foreign, type='MedtronicBrainSenseSurvey', date=IMPLANT_DAY - 100)
        with patch('modules.OURA.DataManager.loadOuraRingData') as loader:
            result = FeatureAvailability.for_participant(self.other)
        loader.assert_not_called()
        self.assertEqual(result['nerual-activity-snapshot']['count'], 1)
        self.assertFalse(result['PainScores']['available'])
        self.assertFalse(result['FitbitDashboard']['available'])

    def test_broken_canonical_mapping_is_unknown_provenance_not_no_surveys(self):
        self.form.record = []
        self.form.save()
        with self.assertLogs('modules.FeatureAvailability', level='ERROR'):
            result = FeatureAvailability.for_participant(self.participant)
        self.assertEqual(result['FormRecords']['count'], 1)
        self.assertEqual(result['PainScores']['kind'], 'unknown')
        self.assertIn('provenance', result['PainScores']['reason'])
        self.assertFalse(result['biomarkers']['available'])

    def test_invalid_sensor_containers_and_non_numeric_values_are_not_observations(self):
        self.assertEqual(FeatureAvailability.measurement_record_count(None), 0)
        data = {'not-records': 'string', 'records': [None, 'text',
            {'Data': ['unparseable'], 'Descriptor': {'nested': {'value': object()}}},
            {'Data': [[np.nan]], 'Missing': [[0]], 'Descriptor': {'label': 'sleep'}},
            {'Data': [[0]], 'Missing': [[0]]}]}
        self.assertEqual(FeatureAvailability.measurement_record_count(data), 1)
