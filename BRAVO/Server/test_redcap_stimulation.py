"""Synthetic evidence/units/cache contracts; no private source data required."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from modules import RedcapStimulation as stim


def stamp(day=1, hour=12):
    return dt.datetime(2026, 8, day, hour, tzinfo=dt.timezone.utc).isoformat()


def channel(side='Left', adaptive=False):
    return {'HemisphereLocation': 'HemisphereLocationDef.' + side,
            'ElectrodeState': [
                {'Electrode': 'ElectrodeDef.Case', 'ElectrodeStateResult': 'ElectrodeStateDef.Positive'},
                {'Electrode': 'ElectrodeDef.SenSight_2a', 'ElectrodeStateResult': 'ElectrodeStateDef.Negative',
                 'ElectrodeAmplitudeInMilliAmps': 1.0, 'ElectrodeFractionOf64': -21}],
            'PulseWidthInMicroSecond': 90, 'RateInHertz': 55, 'SuspendAmplitudeInMilliAmps': 3,
            'BrainSensingStatus': 'SensingStatusDef.ENABLED', 'Channel': 'SensingElectrodeConfigDef.ONE_AND_THREE',
            'SensingSetup': {'FrequencyInHertz': 23.44, 'AveragingDurationInMilliSeconds': 30000},
            'AdaptiveTherapyStatus': 'ADBSStatusDef.' + ('RUNNING' if adaptive else 'NOT_CONFIGURED'),
            'Mode': 'AdaptiveModeDef.DUAL_THRESHOLD_DIRECT', 'LowerLfpThreshold': 1, 'UpperLfpThreshold': 167,
            'LowerLimitInMilliAmps': 2, 'UpperLimitInMilliAmps': 3,
            'TransitionUpInMilliSeconds': 4000, 'TransitionDownInMilliSeconds': 5000,
            'AdaptiveTherapy': {'LowerThresholdOnsetInMilliSeconds': 20000,
                                'UpperThresholdOnsetInMilliSeconds': 30000,
                                'DetectionBlankingDurationInMilliSeconds': 31000,
                                'AdaptiveStartupDelayInMilliSeconds': 0}}


def group(adaptive=False):
    return {'GroupId': 'GroupIdDef.GROUP_D', 'ActiveGroup': True,
            'ProgramSettings': {'RateInHertz': 55, 'SensingChannel': [channel(adaptive=adaptive), channel('Right', adaptive)]},
            'GroupSettings': {'Cycling': {'Enabled': False}, 'SoftStartStop': {'Enabled': True, 'DurationInSeconds': 8},
                              'HighPassFilterInHertz': 1, 'SensingBlankingDurationInMicroseconds': 1640}}


def report(day=1, adaptive=False):
    g = group(adaptive)
    return {'SessionDate': stamp(day), 'SessionEndDate': stamp(day, 13),
            'Groups': {'Initial': [copy.deepcopy(g)], 'Final': [g]},
            'Stimulation': {'InitialStimStatus': 'TherapyStatusDef.ON', 'FinalStimStatus': 'TherapyStatusDef.ON'},
            'DeviceInformation': {'Final': {}},
            'LeadConfiguration': {phase: [
                {'Hemisphere': 'HemisphereLocationDef.Left', 'LeadLocation': 'LeadLocationDef.Gpi', 'Model': 'LeadModelDef.LEAD_B33015'},
                {'Hemisphere': 'HemisphereLocationDef.Right', 'LeadLocation': 'LeadLocationDef.Vim', 'Model': 'LeadModelDef.LEAD_B33015'}]
                for phase in ['Initial', 'Final']}}


def fields(values):
    return {item['label']: item['value'] for item in values}


class Rows(list):
    def order_by(self, *args):
        return self


class SettingsTests(unittest.TestCase):
    def test_scalar_formatting_and_invalid_values(self):
        for value in [None, True, False, float('nan'), float('inf'), '2', [], {}]:
            self.assertEqual(stim.quantity(value, 'mA'), 'Not recorded')
        self.assertEqual(stim.quantity(0, 'ms'), '0 ms')
        self.assertEqual(stim.mapping(None), {})
        self.assertEqual(stim.rows([1, {}]), [{}])
        self.assertEqual(stim.rows({}), [])
        self.assertEqual(stim.state(None), 'Not recorded')
        self.assertEqual(stim.contact(None, 'left'), 'Not recorded')
        self.assertEqual(stim.contact('ElectrodeDef.Custom', 'left'), 'Custom')
        self.assertEqual(stim.sense_contacts('unknown', 'left'), 'Unknown')

    def test_timestamp_requires_explicit_timezone_and_sensible_epoch(self):
        for value in [None, '', [], 'bad', '2026-08-01', '1960-01-01T00:00:00Z']:
            self.assertIsNone(stim.timestamp(value))
        self.assertEqual(stim.timestamp('2026-08-01T05:00:00-07:00'), stim.timestamp(stamp()))

    def test_side_group_scope_and_units_are_source_exact(self):
        payload = report(adaptive=True)
        c = payload['Groups']['Final'][0]['ProgramSettings']['SensingChannel'][1]
        c['GangedToHemisphere'] = 'HemisphereLocationDef.Left'
        result = stim.extract(payload, reviewed=True)['events'][-1]
        settings = result['settings']
        shared, left, right = [fields(settings[k]) for k in ('group', 'left', 'right')]
        self.assertEqual(shared['High-pass filter'], '1 Hz')
        self.assertEqual(shared['Sensing blanking'], '1640 µs')
        self.assertEqual(shared['Cycling'], 'Off')
        self.assertEqual(shared['SoftStart/Stop'], 'On · 8 s')
        self.assertEqual(left['Tablet target'], 'GPi')
        self.assertEqual(right['Tablet target'], 'VIM')
        self.assertEqual(left['Stimulation contacts'], 'Case+, 2a−')
        self.assertEqual(right['Stimulation contacts'], 'Case+, 10a−')
        self.assertEqual(right['Sensing contacts'], '1–3')
        self.assertEqual(right['Sensing source hemisphere'], 'Left')
        self.assertEqual(left['Adaptive amplitude range'], '2 mA to 3 mA')
        self.assertEqual(left['Paused amplitude'], '3 mA')
        self.assertEqual(left['Contact fractions'], '2a− 21/64')
        self.assertEqual(left['Biomarker center frequency'], '23.44 Hz')
        self.assertEqual(left['Averaging duration'], '30 s (30000 ms)')
        self.assertEqual(left['Upper LFP threshold'], '167 LFP Power (LSB)')
        self.assertEqual(left['Transition up'], '4 s (4000 ms)')
        self.assertEqual(left['Transition down'], '5 s (5000 ms)')
        self.assertEqual(left['Lower onset duration'], '20 s (20000 ms)')
        self.assertEqual(left['Upper onset duration'], '30 s (30000 ms)')
        self.assertEqual(left['Detection blanking duration'], '31 s (31000 ms)')
        self.assertEqual(left['Adaptive startup delay'], '0 ms')
        self.assertNotIn('High-pass filter', left)
        self.assertNotIn('Sensing blanking', left)
        self.assertIn('exact setting-change time is not known', result['evidence'])
        self.assertEqual(result['time'], stim.timestamp(stamp(hour=13)))

    def test_amplitude_does_not_sum_segment_currents_or_use_session_average(self):
        c = channel()
        c.pop('SuspendAmplitudeInMilliAmps')
        result = fields(stim.side_settings(c, 'left', 55, 'GPi'))
        self.assertEqual(result['Amplitude'], 'Not recorded')
        c['ElectrodeState'][-1].pop('ElectrodeFractionOf64')
        self.assertEqual(fields(stim.side_settings(c, 'left', 55, 'GPi'))['Amplitude'], '1 mA')
        c['ElectrodeState'].append(copy.deepcopy(c['ElectrodeState'][-1]))
        self.assertEqual(fields(stim.side_settings(c, 'left', 55, 'GPi'))['Amplitude'], 'Not recorded')
        c['AmplitudeInMilliAmps'] = 2.1
        self.assertEqual(fields(stim.side_settings(c, 'left', 55, 'GPi'))['Amplitude'], '2.1 mA')
        c['AdaptiveTherapyStatus'] = 'ADBSStatusDef.SUSPENDED'
        self.assertEqual(fields(stim.side_settings(c, 'left', 55, 'GPi'))['Fixed / paused amplitude'], '2.1 mA')
        self.assertEqual(fields(stim.side_settings(c, 'left', 55, 'GPi'))['Adaptive amplitude range'], '2 mA to 3 mA')
        c['AdaptiveTherapyStatus'] = 'ADBSStatusDef.RUNNING'
        self.assertNotIn('Amplitude', fields(stim.side_settings(c, 'left', 55, 'GPi')))

    def test_contralateral_sensing_uses_controller_not_local_pair_or_thresholds(self):
        p = report(adaptive=True)
        left, right = p['Groups']['Final'][0]['ProgramSettings']['SensingChannel']
        right['GangedToHemisphere'] = 'HemisphereLocationDef.Left'
        right['Channel'] = 'SensingElectrodeConfigDef.ZERO_AND_TWO'
        right['SensingSetup']['FrequencyInHertz'] = 5
        right['LowerLfpThreshold'] = 999
        result = fields(stim.extract(p)['events'][-1]['settings']['right'])
        self.assertEqual(result['Sensing contacts'], '1–3')
        self.assertEqual(result['Biomarker center frequency'], '23.44 Hz')
        self.assertEqual(result['Lower LFP threshold'], '1 LFP Power (LSB)')
        missing = fields(stim.side_settings(right, 'right', 55, 'VIM'))
        self.assertEqual(missing['Sensing contacts'], 'Not recorded')
        self.assertEqual(missing['Lower LFP threshold'], 'Not recorded')

    def test_missing_channel_and_legacy_multiple_programs(self):
        payload = report()
        g = payload['Groups']['Final'][0]
        g['ProgramSettings'] = {'RateInHertz': 80, 'LeftHemisphere': {'Programs': [
            {'Enabled': False}, {'AmplitudeInMilliAmps': 1, 'ElectrodeState': [{}]}, {'AmplitudeInMilliAmps': 2}]}}
        settings, _ = stim.settings_for(g, {}, 'Final')
        self.assertEqual(fields(settings['left'])['Program 1 · Frequency'], '80 Hz')
        self.assertEqual(fields(settings['left'])['Program 2 · Amplitude'], '2 mA')
        self.assertEqual(fields(settings['left'])['Program 1 · Tablet target'], 'Not recorded')
        self.assertEqual(len(settings['right']), 1)
        c = channel(); c.pop('AdaptiveTherapyStatus'); c.pop('LowerLfpThreshold'); c.pop('UpperLfpThreshold')
        self.assertNotIn('Lower LFP threshold', fields(stim.side_settings(c, 'left', 1, 'GPi')))

    def test_cycling_duration_variants_and_unknowns(self):
        for key in ('OnDurationInSeconds', 'OnTimeInSeconds', 'CyclingOnDurationInSeconds', 'OnDurationSeconds'):
            self.assertEqual(stim.duration_seconds({key: 5}, 'On'), 5)
        self.assertEqual(stim.duration_seconds({'OnDurationInMilliSeconds': 500}, 'On'), 0.5)
        self.assertIsNone(stim.duration_seconds({'OnDurationInMilliSeconds': 'bad'}, 'On'))
        self.assertIsNone(stim.duration_seconds({}, 'On'))
        g = group(); g['GroupSettings']['Cycling'] = {'Enabled': True, 'OnDurationInSeconds': 5, 'OffDurationInSeconds': 10}
        g['GroupSettings']['SoftStartStop'] = {'Enabled': False}
        shared = fields(stim.settings_for(g, {}, 'Final')[0]['group'])
        self.assertEqual(shared['Cycling'], 'On · on 5 s / off 10 s')
        self.assertEqual(shared['SoftStart/Stop'], 'Off')
        shared = fields(stim.settings_for({}, {}, 'Final')[0]['group'])
        self.assertEqual(shared['Cycling'], 'Not recorded')
        self.assertEqual(stim.group_label({}), 'Group not recorded')

    def test_programmer_boundaries_no_other_phase_or_history_fallback(self):
        p = report(); p.pop('SessionDate')
        self.assertEqual([e['phase'] for e in stim.extract(p)['events']], ['Final'])
        p = report(); p['SessionEndDate'] = stamp(hour=11)
        self.assertEqual(stim.extract(p)['events'], [])
        p['SessionEndDate'] = stamp(2)
        self.assertEqual(stim.extract(p)['events'], [])
        p = report(); p['Groups']['Initial'][0]['ActiveGroup'] = False
        p['GroupHistory'] = [{'SessionDate': stamp(1), 'Groups': [group()]}]
        self.assertEqual([e['phase'] for e in stim.extract(p)['events']], ['Final'])
        p['Groups']['Final'].append(group())
        self.assertEqual(stim.extract(p)['events'], [])

    def test_reviewed_source_policy_rejects_bench_and_wrong_leads(self):
        self.assertEqual(stim.extract(None)['excluded'], 'Malformed report')
        p = report(); p['DeviceInformation']['Final']['DeviceName'] = 'Benchtop'
        self.assertIn('Benchtop', stim.extract(p, True)['excluded'])
        p = report(); p['LeadConfiguration']['Final'][1]['LeadLocation'] = 'LeadLocationDef.Stn'
        self.assertIn('configuration', stim.extract(p, True)['excluded'])

    def test_logged_changes_do_not_borrow_future_snapshot(self):
        p = report(day=3)
        p['DiagnosticData'] = {'EventLogs': [
            {'DateTime': stamp(1), 'ParameterTrendId': 1, 'NewGroupId': 'GroupIdDef.GROUP_A'},
            {'DateTime': stamp(1, 13), 'ParameterTrendId': 2, 'TherapyStatus': 'TherapyChangeStatusDef.OFF'},
            {'DateTime': stamp(1, 14), 'ParameterTrendId': 3, 'AdbsStatus': 'TherapyChangeStatusDef.ON'},
            {'DateTime': stamp(1, 15), 'ParameterTrendId': 4, 'NewGroupId': 'GroupIdDef.GROUP_A', 'OldGroupId': 'GroupIdDef.GROUP_A'},
            {'DateTime': stamp(1, 16), 'ParameterTrendId': 5, 'NewGroupId': 'GroupIdDef.GROUP_UNKNOWN'},
            {'DateTime': 'bad', 'ParameterTrendId': 5}, {'DateTime': stamp(1)}, {}]}
        events = stim.extract(p)['events']
        self.assertEqual(len(events), 5)
        self.assertEqual([e['kind'] for e in events[-3:]], ['group_change', 'stimulation_status', 'adaptive_status'])
        self.assertEqual(events[-3]['settings'], stim.unavailable())
        self.assertIn('device clock', events[-3]['evidence'])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'report-cache'
        self.environment = patch.dict(stim.os.environ, {'DATASERVER_PATH': self.tmp.name})
        self.environment.start()
        self.participant = NS(uid='p', name='RCS08')
        self.source = NS(uid='s', hashed='a', pointer='synthetic', metadata={})
        self.directory = patch.object(stim.ReportCache, 'directory', return_value=self.root)
        self.loader = patch.object(stim.DataCurator, 'loadCacheFile', return_value=json.dumps(report()).encode())
        self.sources = patch.object(stim.models.SourceFile, 'find_all', return_value=Rows([self.source]))
        self.directory.start(); self.load = self.loader.start(); self.sources.start()

    def tearDown(self):
        self.directory.stop(); self.loader.stop(); self.sources.stop(); self.environment.stop(); self.tmp.cleanup()

    def test_read_only_cache_never_populates_and_reports_missing_corrupt_or_stale_context(self):
        self.assertEqual(stim.source_context(self.source, self.participant, True, 'policy', cached_only=True), (None, False))
        self.assertFalse(self.root.exists())
        self.load.assert_not_called()
        self.directory.stop()
        try:
            expected = stim.source_context(self.source, self.participant, True, 'policy')[0]
            self.load.reset_mock()
            self.assertEqual(stim.source_context(self.source, self.participant, True, 'policy', cached_only=True), (expected, True))
            self.assertEqual(stim.source_context(self.source, self.participant, True, 'new-policy', cached_only=True), (None, False))
            path = next(self.root.rglob('*.json'))
            for invalid in ('invalid', '[]', '{"events":[]}'):
                path.write_text(invalid)
                self.assertEqual(stim.source_context(self.source, self.participant, True, 'policy', cached_only=True), (None, False))
                self.assertEqual(path.read_text(), invalid)
            self.load.assert_not_called()
        finally:
            self.directory.start()

    def test_source_cache_survives_restarts_and_source_change_invalidates(self):
        first = stim.source_context(self.source, self.participant, True, 'policy')
        second = stim.source_context(self.source, self.participant, True, 'policy')
        self.assertFalse(first[1]); self.assertTrue(second[1]); self.assertEqual(first[0], second[0])
        self.assertEqual(self.load.call_count, 1)
        self.source.hashed = 'b'
        self.assertFalse(stim.source_context(self.source, self.participant, True, 'policy')[1])
        self.assertFalse(stim.source_context(self.source, self.participant, True, 'policy2')[1])
        self.assertEqual(list(self.root.rglob('*.tmp')), [])

    def test_cache_corruption_rebuilt_and_read_errors_not_saved_as_empty(self):
        stim.source_context(self.source, self.participant, True, 'policy')
        path = next(self.root.rglob('*.json'))
        for invalid in ('invalid', '[]', '{"events":[]}'):
            path.write_text(invalid)
            self.assertFalse(stim.source_context(self.source, self.participant, True, 'policy')[1])
        path.unlink()
        self.load.side_effect = OSError('unavailable')
        with self.assertRaises(OSError):
            stim.source_context(self.source, self.participant, True, 'policy')
        self.assertEqual(list(self.root.rglob('*.json')), [])

    def test_metadata_exclusion_preserved_without_reading_raw(self):
        self.source.metadata = {'AnalysisExclusion': 'Reviewed exclusion'}
        result = stim.build_context(self.participant, stim.timestamp(stamp(4)))
        self.assertEqual(result['transitions'], [])
        self.assertEqual(result['provenance']['excluded_source_count'], 1)
        self.load.assert_not_called()

    def test_deduplicated_logged_changes_sources_and_changed_snapshots(self):
        p = report()
        p['Groups']['Final'][0]['ProgramSettings']['SensingChannel'][0]['SuspendAmplitudeInMilliAmps'] = 4
        p['DiagnosticData'] = {'EventLogs': [{'DateTime': stamp(2), 'ParameterTrendId': 1, 'TherapyStatus': 'TherapyChangeStatusDef.ON'}]}
        self.load.return_value = json.dumps(p).encode()
        s2 = copy.copy(self.source); s2.uid = 's2'
        with patch.object(stim.models.SourceFile, 'find_all', return_value=Rows([self.source, s2])):
            result = stim.build_context(self.participant, stim.timestamp(stamp(4)))
            self.assertEqual(len(result['transitions']), 3)
            self.assertTrue(all(e['source_ids'] == ['s', 's2'] for e in result['transitions']))
            self.assertEqual(result['provenance']['source_count'], 2)
            self.assertEqual(stim.build_context(self.participant)['provenance']['cached_source_count'], 2)
        json.dumps(result, allow_nan=False)

    def test_unchanged_observations_collapsed_future_and_preimplant_filtered(self):
        p = report()
        p['DiagnosticData'] = {'EventLogs': [
            {'DateTime': '2025-01-01T12:00:00Z', 'ParameterTrendId': 1, 'TherapyStatus': 'TherapyChangeStatusDef.ON'},
            {'DateTime': '2099-01-01T12:00:00Z', 'ParameterTrendId': 1, 'TherapyStatus': 'TherapyChangeStatusDef.ON'}]}
        self.load.return_value = json.dumps(p).encode()
        result = stim.build_context(self.participant, stim.timestamp(stamp(4)))
        self.assertEqual(len(result['transitions']), 1)
        self.assertEqual(result['transitions'][0]['phase'], 'Initial')
        with patch.object(stim.RCS08DataPolicy, 'applies_to', return_value=False):
            result = stim.build_context(self.participant, stim.timestamp(stamp(4)))
        self.assertEqual(len(result['transitions']), 2)

    def test_snapshot_after_log_is_not_suppressed_as_unchanged(self):
        p = report()
        p['DiagnosticData'] = {'EventLogs': [{'DateTime': '2026-08-01T12:30:00Z', 'ParameterTrendId': 1,
                                             'TherapyStatus': 'TherapyChangeStatusDef.OFF'}]}
        self.load.return_value = json.dumps(p).encode()
        result = stim.build_context(self.participant, stim.timestamp(stamp(4)))
        self.assertEqual([e['kind'] for e in result['transitions']], ['settings_observed', 'stimulation_status', 'settings_observed'])

    def test_adaptive_snapshot_current_change_is_not_a_programming_transition(self):
        p = report(adaptive=True)
        p['Groups']['Final'][0]['ProgramSettings']['SensingChannel'][0]['ElectrodeState'][1]['ElectrodeAmplitudeInMilliAmps'] = 2
        self.load.return_value = json.dumps(p).encode()
        result = stim.build_context(self.participant, stim.timestamp(stamp(4)))
        self.assertEqual(len(result['transitions']), 1)
