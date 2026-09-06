"""Synthetic timeline contracts: source equivalence, QC, clocks and permissions."""
import copy
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from rest_framework.test import APIRequestFactory, force_authenticate
from modules import RedcapTimeline as timeline
from modules import RCS08HistoricalSurveys as history
from Server.APIs import RedcapTimeline as api

STAGES = 'stage,start_date,end_date\nstage_0,2025-05-27,2025-06-06\nstage_1,2025-07-16,2025-07-29\nstage_2,2025-07-30,\n'


def stamp(value):
    return dt.datetime.fromisoformat(value).timestamp()


class Rows(list):
    def order_by(self, *args):
        return self


def fixture(name, values=None, date=None):
    source, mapping, hash_key = timeline.FORMS[name]
    keys = list(mapping)
    questions = [{'type': 'score', 'variableName': key} for key in keys]
    questions += [{'type': 'text', 'variableName': 'timestamp'}]
    audit = {hash_key: 'a'*64, 'timeline_schema': timeline.VERSION}
    if name == 'RCS08 Daily PRO (REDCap)':
        phases, digest = timeline.phase_table()
        audit.update(timeline_phases=phases, timeline_stage_sha256=digest)
    form = NS(name=name, uid=name, record=[{'questions': questions, 'processing': audit}])
    values = values or {}
    record = NS(name='repeat:2', date=stamp(date or '2025-06-01T12:00:00-07:00'),
                record=[[values.get(key, 0) for key in keys] + ['time']])
    return form, record


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'rcs08_study_stages.csv'
        self.path.write_text(STAGES)
        self.env = patch.dict('os.environ', {'RCS08_PROCESSING_RULES': self.tmp.name})
        self.env.start()
        self.participant = NS(name='RCS08', institute='test')
        self.forms = {}
        self.records = {}
        self.form_patch = patch.object(timeline.models.ScaleForms, 'find', side_effect=lambda **kw: self.forms.get(kw['name']))
        self.record_patch = patch.object(timeline.models.ScaleRecord, 'find_all', side_effect=lambda **kw: Rows(self.records[kw['source'].name]))
        self.form_patch.start(); self.record_patch.start()
        self.add('RCS08 Daily PRO (REDCap)')
        self.records['RCS08 Daily PRO (REDCap)'] = []

    def tearDown(self):
        self.form_patch.stop(); self.record_patch.stop(); self.env.stop(); self.tmp.cleanup()

    def add(self, name, values=None, date=None):
        form, record = fixture(name, values, date)
        self.forms[name] = form; self.records[name] = [record]
        return form, record

    def report(self, **kw):
        return timeline.build_report(self.participant, now=stamp('2026-09-03T12:00:00-07:00'), **kw)

    def test_all27_metrics_exact_join_sources_sort_and_stages(self):
        for name in timeline.FORMS:
            self.add(name)
        # Combined-region and depression values are deliberately never in the mapping.
        self.assertNotIn('left_leg_low_back_vas_intensity', str(timeline.FORMS))
        self.assertNotIn('depression_vas_short', str(timeline.FORMS))
        report = self.report()
        self.assertEqual(len(report['metrics']), 27)
        counts = {m['key']: len(m['points']) for m in report['metrics']}
        self.assertEqual(counts['vas_intensity'], 5)
        self.assertEqual(counts['mood_vas'], 2)
        self.assertEqual(counts['left_leg_vas_intensity'], 1)
        self.assertEqual(counts['mpq_standard_0_45'], 3)
        self.assertEqual(counts['mpq_throbbing'], 3)
        self.assertEqual(counts['firey'], 2)
        self.assertEqual(report['metrics'][0]['points'][0]['value'], 0)
        self.assertEqual(report['provenance']['missing_sources'], [])
        self.assertEqual(report['provenance']['stage_sha256'], hashlib.sha256(STAGES.encode()).hexdigest())
        self.assertEqual(report['phases'][-1]['end'], None)
        json.dumps(report, allow_nan=False)

    def test_numeric_invalid_missing_and_future_rows(self):
        name = 'RCS08 Daily PRO (REDCap)'
        form, record = self.add(name, {'mood': None, 'nrs': '', 'vas': 'bad', 'left_leg_vas': 101,
                                      'back_vas': -1, 'relief': float('nan'), 'mpq_aff': True, 'mpq_sen': '33'})
        future = copy.deepcopy(record); future.date = stamp('2027-01-01T00:00:00+00:00')
        self.records[name].append(future)
        report = self.report()
        metrics = {m['key']: m['points'] for m in report['metrics']}
        self.assertEqual(metrics['mood_vas'], [])
        self.assertEqual(metrics['mpq_sens'][0]['value'], 33)
        self.assertEqual(report['provenance']['omitted'], {'future_records': 1, 'missing_values': 2, 'invalid_values': 5, 'outside_stages': 0})
        self.assertEqual(len(report['provenance']['missing_sources']), 5)

    def test_phase_exact_local_boundaries_pretrial_and_end(self):
        name = 'RCS08 Stage 0 - Mini VAS'
        _, record = self.add(name)
        dates = ['2025-05-26T23:59:59-07:00','2025-05-27T00:00:00-07:00',
                 '2025-06-07T00:00:00-07:00','2025-07-16T00:00:00-07:00','2025-07-30T00:00:00-07:00']
        self.records[name] = [NS(name=str(i), date=stamp(date), record=record.record) for i, date in enumerate(dates)]
        report = self.report()
        points = next(m['points'] for m in report['metrics'] if m['key']=='vas_intensity')
        self.assertEqual([p['phase'] for p in points], [p[0] for p in timeline.PHASE_STYLES])
        self.assertEqual(report['phases'][0]['start'], stamp(dates[0]))
        self.path.write_text(STAGES.replace('2025-07-30,', '2025-07-30,2025-07-30'))
        self.add('RCS08 Daily PRO (REDCap)')
        self.records['RCS08 Daily PRO (REDCap)'] = []
        self.records[name].append(NS(name='outside', date=stamp('2025-07-31T00:00:00-07:00'), record=record.record))
        self.assertEqual(self.report()['provenance']['omitted']['outside_stages'], 1)
        self.assertNotIn('ongoing', self.report()['phases'][-1]['label'])

    def test_empty_scores_no_raw_fallback_and_unsupported(self):
        name = 'RCS08 Stage 0 - Mini VAS'
        self.add(name, {'pain_vas_mini': None, 'pain_relief_mini': None})
        report = self.report()
        self.assertTrue(all(not metric['points'] for metric in report['metrics']))
        self.assertEqual(report['phases'][0]['start'], report['phases'][1]['start'])
        self.forms.clear()
        with self.assertRaises(timeline.TimelineNotReady): self.report()
        with patch('modules.RCS08DataPolicy.applies_to', return_value=False):
            with self.assertRaises(timeline.TimelineNotReady): self.report()

    def test_bad_stage_schema_and_order(self):
        for data in [STAGES.replace('stage_0,','missing,'), STAGES + 'stage_0,2025-01-01,2025-01-02\n',
                     STAGES.replace('2025-07-29', '2025-07-28'), STAGES.replace('2025-06-06', '2025-07-20'),
                     STAGES.replace('2025-07-30,', '2025-07-30,2025-07-28')]:
            self.path.write_text(data)
            with self.assertRaises(timeline.TimelineNotReady): timeline.phase_table(self.path)
        self.path.write_text(STAGES.replace('2025-05-27','not-a-date'))
        with self.assertRaises(ValueError): timeline.phase_table()

    def test_missing_old_or_malformed_mapping_fail_closed(self):
        name = 'RCS08 Daily PRO (REDCap)'
        for record in [None, [], [None], [{'processing':None,'questions':[]}], [{'processing':{}, 'questions':[]}],
                       [{'processing':{'timeline_schema':timeline.VERSION,'reviewed_sha256':'bad'},'questions':[]}]]:
            form, _ = self.add(name); form.record = record
            with self.assertRaises(timeline.TimelineNotReady): self.report()
        for duplicate in [False, True]:
            form, _ = self.add(name)
            if duplicate: form.record[0]['questions'].append(form.record[0]['questions'][0])
            else: form.record[0]['questions'].pop(0)
            with self.assertRaises(timeline.TimelineNotReady): self.report()

    def test_bad_record_shape_and_date_fail_closed(self):
        name = 'RCS08 Daily PRO (REDCap)'
        for payload in [None, [], [[]], [None]]:
            _, record = self.add(name); record.record = payload
            with self.assertRaises(timeline.TimelineNotReady): self.report()
        _, record = self.add(name); record.date = 'bad'
        with self.assertRaises(timeline.TimelineNotReady): self.report()

    def test_stored_phase_invalid_and_empty_publication(self):
        form = self.forms['RCS08 Daily PRO (REDCap)']
        baseline = copy.deepcopy(form.record[0]['processing'])
        variants = [None, [], [{'key':'wrong'}]*5]
        for phases in variants:
            form.record[0]['processing'] = dict(baseline, timeline_phases=phases)
            with self.assertRaises(timeline.TimelineNotReady): self.report()
        for i, field, value in [(1,'start',None),(1,'end',None),(1,'start',0),(2,'start',1e20)]:
            phases = copy.deepcopy(baseline['timeline_phases']); phases[i][field] = value
            form.record[0]['processing'] = dict(baseline, timeline_phases=phases)
            with self.assertRaises(timeline.TimelineNotReady): self.report()
        form.record[0]['processing'] = baseline
        with patch.object(timeline.models.ScaleForms,'find',side_effect=[form]+[None]*6):
            with self.assertRaises(timeline.TimelineNotReady): self.report()

    def test_default_now_and_finite(self):
        self.add('RCS08 Stage 0 - Mini VAS')
        self.assertEqual(len(timeline.build_report(self.participant)['metrics']),27)
        for value in [None, True, 'bad', float('nan'), float('inf'), {}]: self.assertIsNone(timeline.finite(value))
        self.assertEqual(timeline.finite('0'), 0)


class HistoricalScoringTests(unittest.TestCase):
    def test_stage0_partial_and_absent_blocks_exact_notebook_rule(self):
        row = {'throbbing_stage0':'2', 'shooting_stage0':'', 'tiring_exhausting_stage0':'1'}
        self.assertEqual(history.historical_value(row, 'Stage 0', 'mpq_sens'),2)
        self.assertEqual(history.historical_value(row, 'Stage 0', 'mpq_aff'),1)
        self.assertEqual(history.historical_value(row, 'Stage 0', 'mpq_standard_0_45'),3)
        self.assertIsNone(history.historical_value({}, 'Stage 0', 'mpq_standard_0_45'))
        self.assertEqual(history.historical_value(row, 'Stage 0', 'mpq_throbbing'),2)
        self.assertEqual(history.historical_value({'firey_stage0':'3'}, 'Stage 0', 'firey'),3)
        self.assertEqual(history.historical_value({'mpq_throbbing':'1'}, 'Fluctuation', 'mpq_throbbing'),1)
        self.assertEqual(history.source_columns('Stage 0', 'pain_vas_long'), ['pain_vas_long'])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = NS(is_authenticated=True,configuration={})
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'rcs08_study_stages.csv'; self.path.write_text(STAGES)
        patch.dict('os.environ', {'DATASERVER_PATH': self.tmp.name+'/', 'RCS08_PROCESSING_RULES':self.tmp.name}).start()
        self.permission = patch('modules.Database.checkAccessPermission', return_value={'View':True}).start()
        self.person = patch.object(api.models.Participant,'find',return_value=NS(name='RCS08',institute='synthetic')).start()
        patch('modules.Database.retrieveProcessingSettings', return_value=({},None)).start()
        self.build = patch.object(api, 'build_report', return_value={'metrics':[],'phases':[]}).start()
        self.daily_form = patch.object(api.models.ScaleForms,'find',return_value=NS(record=[{'processing':{'timeline_home_adjustments':[]}}])).start()
        self.visits = patch('modules.RedcapVisitContext.read',return_value={'available':False}).start()
        self.stimulation = patch('modules.RedcapStimulation.build_context',return_value={'available':False}).start()
        self.adjustments = patch('modules.RedcapHomeAdjustments.apply',return_value={'available':False}).start()

    def tearDown(self):
        patch.stopall(); self.tmp.cleanup()

    def request(self, body, auth=True):
        request = self.factory.post('/api/queryRedcapTimeline',body,format='json')
        if auth: force_authenticate(request,user=self.user)
        return api.QueryRedcapTimeline.as_view()(request)

    def test_auth_validation_permission_and_policy(self):
        self.assertIn(self.request({'ParticipantId':'p'},False).status_code,[401,403])
        for body in [[],{}, {'ParticipantId':None},{'ParticipantId':''},{'ParticipantId':1},
                     {'ParticipantId':'x'*129},{'ParticipantId':'p','raw':True}]:
            self.assertEqual(self.request(body).status_code,400)
        self.permission.return_value = None
        self.assertEqual(self.request({'ParticipantId':'p'}).status_code,403)
        self.permission.return_value = {'View':True}; self.person.return_value=None
        self.assertEqual(self.request({'ParticipantId':'p'}).status_code,403)
        self.person.return_value=NS(name='RCS08',institute='synthetic')
        with patch.object(api,'applies_to',return_value=False):
            self.assertEqual(self.request({'ParticipantId':'p'}).status_code,404)
        self.build.assert_not_called()
        self.visits.assert_not_called()
        self.stimulation.assert_not_called()
        self.adjustments.assert_not_called()

    def test_cache_rev_permission_before_hit_and_error(self):
        response = self.request({'ParticipantId':'p'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Cache-Control'],'no-store')
        self.assertEqual(self.visits.call_count,1)
        self.assertEqual(self.stimulation.call_count,1)
        self.assertEqual(self.adjustments.call_count,1)
        self.assertEqual(self.adjustments.call_args.args[:2], ({"available":False}, []))
        self.assertEqual(self.request({'ParticipantId':'p'})['X-BRAVO-Report-Cache'],'HIT')
        self.assertEqual(self.build.call_count,1)
        self.permission.return_value=None
        self.assertEqual(self.request({'ParticipantId':'p'}).status_code,403)
        self.permission.return_value={'View':True}
        from modules.ReportCache import invalidate
        invalidate()
        self.request({'ParticipantId':'p'})
        self.assertEqual(self.build.call_count,2)
        self.build.side_effect=ValueError('unready')
        self.assertEqual(self.request({'ParticipantId':'other'}).status_code,503)
        self.build.side_effect=OSError('unready')
        self.assertEqual(self.request({'ParticipantId':'another'}).status_code,503)

    def test_malformed_adjustment_processing_returns_service_unavailable(self):
        malformed = [None, NS(record=None), NS(record=[]), NS(record=[None]),
                     NS(record=[{}]), NS(record=[{'processing':None}]), NS(record=[{'processing':[]}])]
        for index, daily in enumerate(malformed):
            self.daily_form.return_value = daily
            self.assertEqual(self.request({'ParticipantId':f'malformed-{index}'}).status_code,503)
        self.adjustments.assert_not_called()

    def test_comparison_code_identity_changes_cache_identity(self):
        from modules import RedcapComparisons
        original = api.QueryRedcapTimeline().cache_version
        with patch.object(RedcapComparisons, 'code_identity', return_value='changed'):
            self.assertNotEqual(original, api.QueryRedcapTimeline().cache_version)

    def test_home_program_schema_changes_cache_identity(self):
        from modules import RedcapHomePrograms
        original = api.QueryRedcapTimeline().cache_version
        with patch.object(RedcapHomePrograms, 'VERSION', 'changed-home-program-schema'):
            self.assertNotEqual(original, api.QueryRedcapTimeline().cache_version)

    def test_bad_optional_comparison_does_not_break_timeline(self):
        self.daily_form.return_value.record[0]['comparison_context'] = 'damaged'
        response = self.request({'ParticipantId':'bad-comparison'})
        self.assertEqual(response.status_code, 200)
        import gzip
        body = json.loads(gzip.decompress(response.content) if response.get('Content-Encoding') == 'gzip' else response.content)
        self.assertFalse(body['comparisons']['stimulation']['available'])

    def test_cache_calendar_rollover(self):
        original = api.dt.datetime
        with patch.object(api.dt,'datetime') as clock:
            clock.now.return_value=original(2026,9,3)
            first=api.QueryRedcapTimeline().cache_version
            clock.now.return_value=original(2026,9,4)
            second=api.QueryRedcapTimeline().cache_version
        self.assertNotEqual(first,second)
