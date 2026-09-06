"""Home program selection excludes clinic experiments without losing home changes."""
import copy
import datetime as dt
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from modules import RedcapHomePrograms as home


def event(day, phase='Final', hour=13, group='A', amp='3 mA', uid='s', **extra):
    stamp = dt.datetime.fromisoformat(f'2026-08-{day:02}T{hour:02}:00:00-07:00').timestamp()
    return {'id': f'{day}-{hour}-{phase}-{uid}', 'time': stamp, 'phase': phase, 'kind': 'settings_observed',
            'source_ids': [uid], 'settings': {
                'group': [{'label': 'Group', 'value': 'Group ' + group},
                          {'label': 'Mode at observation', 'value': 'Open loop / fixed stimulation'},
                          {'label': 'Stimulation status', 'value': 'On'}],
                'left': [{'label': 'Amplitude', 'value': amp},
                         {'label': 'Exported contact amplitudes (snapshot)', 'value': '1 mA'},
                         {'label': 'Upper LFP threshold', 'value': '30 LFP Power (LSB)'}],
                'right': []}, 'evidence': 'raw snapshot', **extra}


def choose(events, days=('2026-08-06', '2026-08-18')):
    return home.select(events, set(days), 'a' * 64)


class HomeSelectionTests(unittest.TestCase):
    def test_visit_only_final_last_session_not_interim_final_or_initial(self):
        initial = event(6, 'Initial', 8, 'C')
        interim = event(6, 'Final', 9, 'D')
        final = event(6, 'Final', 13, 'A')
        later_initial = event(6, 'Initial', 14, 'B')
        result = choose([initial, interim, final, later_initial])
        self.assertEqual(len(result['home_transitions']), 1)
        selected = result['home_transitions'][0]
        self.assertEqual(selected['time'], final['time'])
        self.assertEqual(selected['label'], 'Group A · Open loop')
        self.assertEqual(selected['scope'], 'home_program')
        self.assertEqual(selected['kind'], 'settings_observed')
        self.assertEqual(selected['home_timing']['selection'], 'post_visit_final')
        self.assertFalse(selected['home_timing']['activation_time_known'])
        self.assertIn('not a proven departure', selected['evidence'])
        self.assertEqual(result['home_provenance']['suppressed_observation_count'], 3)
        self.assertEqual(initial['evidence'], 'raw snapshot')

    def test_home_amplitude_threshold_changes_and_unchanged_download_suppression(self):
        start = event(6, amp='4 mA')
        lower = event(12, 'Initial', amp='3.5 mA')
        same = event(12, 'Final', hour=14, amp='3.5 mA')
        cycling = event(18, group='B', amp='3.5 mA')
        download = event(20, group='B', amp='3.5 mA')
        backup = event(23, 'Initial', group='A', amp='3.5 mA')
        threshold = event(24, group='A', amp='3.5 mA')
        threshold['settings']['left'][-1]['value'] = '167 LFP Power (LSB)'
        result = choose([start, lower, same, cycling, download, backup, threshold])['home_transitions']
        self.assertEqual([e['time'] for e in result], [start['time'], lower['time'], cycling['time'], backup['time'], threshold['time']])
        self.assertEqual(result[1]['phase'], 'Initial')
        self.assertEqual(result[1]['home_timing']['previous_configuration_last_observed'], start['time'])
        self.assertEqual(result[3]['home_timing']['previous_configuration_last_observed'], download['time'])
        self.assertIn('First observed', result[1]['evidence'])
        self.assertIn('previous configuration was last observed', result[1]['evidence'])

    def test_logs_status_and_dynamic_currents_do_not_manufacture_home_changes(self):
        first, second = event(7), event(8)
        second['settings']['group'][-1]['value'] = 'Off'
        second['settings']['left'][1]['value'] = '2 mA'
        log = event(7, hour=14, kind='stimulation_status')
        result = choose([first, log, second])['home_transitions']
        self.assertEqual(len(result), 1)
        self.assertFalse(any(f['label'] == 'Stimulation status' for f in result[0]['settings']['group']))
        self.assertFalse(any('Exported contact' in f['label'] for f in result[0]['settings']['left']))
        self.assertEqual(home.fingerprint(first['settings']), home.fingerprint(second['settings']))

    def test_same_time_same_configuration_merges_sources_and_prefers_final(self):
        first, second = event(7, 'Initial', uid='b'), event(7, 'Final', uid='a')
        result = choose([first, second])['home_transitions']
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['source_ids'], ['a', 'b'])
        self.assertEqual(result[0]['phase'], 'Final')

    def test_conflicting_latest_visit_does_not_choose_a_source_or_earlier_final(self):
        previous = event(5)
        earlier = event(6, hour=10)
        latest_a = event(6, hour=13, group='A', uid='a')
        latest_b = event(6, hour=13, group='B', uid='b')
        subsequent = event(7)
        result = choose([previous, earlier, latest_a, latest_b, subsequent])
        self.assertEqual(len(result['home_transitions']), 2)
        self.assertEqual(result['home_provenance']['ambiguous_observations'][0]['day'], '2026-08-06')
        self.assertIsNone(result['home_transitions'][-1]['home_timing']['previous_configuration_last_observed'])

    def test_conflicting_between_visit_clock_is_not_arbitrarily_ordered(self):
        result = choose([event(7, uid='a'), event(7, uid='b', group='B')])
        self.assertEqual(result['home_transitions'], [])
        self.assertEqual(len(result['home_provenance']['ambiguous_observations']), 1)

    def test_testing_day_without_final_is_flagged_and_cannot_use_initial(self):
        result = choose([event(5), event(6, 'Initial'), event(7)])
        self.assertEqual(len(result['home_transitions']), 2)
        self.assertEqual(result['home_provenance']['testing_days_without_final'], ['2026-08-06'])
        self.assertIsNone(result['home_transitions'][-1]['home_timing']['previous_configuration_last_observed'])
        interval = result['home_unknown_intervals'][0]
        self.assertEqual(interval['start'], event(6, hour=0)['time'])
        self.assertEqual(interval['end'], event(7)['time'])

    def test_entire_missing_visit_day_blocks_carry_until_next_confirmation(self):
        result = choose([event(5), event(7)])
        self.assertEqual(result['home_provenance']['testing_days_without_final'], ['2026-08-06'])
        self.assertEqual(result['home_unknown_intervals'][0]['start'], event(6, hour=0)['time'])
        self.assertEqual(result['home_unknown_intervals'][0]['end'], event(7)['time'])
        # Same configuration after the unknown interval must be re-established.
        self.assertEqual(len(result['home_transitions']), 2)

    def test_unknown_interval_stays_open_without_following_observation(self):
        first = event(7)
        conflict_a, conflict_b = event(8, uid='a'), event(8, group='B', uid='b')
        result = choose([first, conflict_a, conflict_b])
        self.assertEqual(result['home_unknown_intervals'], [{
            'start': conflict_a['time'], 'end': None,
            'reason': 'Conflicting program settings at the same observation time.'}])

    def test_consecutive_unknown_dates_form_one_interval_and_later_gap_is_separate(self):
        observations = [event(5), event(7, 'Initial'), event(8), event(9, 'Initial'), event(10)]
        result = choose(observations, ['2026-08-06', '2026-08-07', '2026-08-09'])
        intervals = result['home_unknown_intervals']
        self.assertEqual([(g['start'], g['end']) for g in intervals], [
            (event(6, hour=0)['time'], event(8)['time']),
            (event(9, hour=0)['time'], event(10)['time'])])

    def test_calendar_outside_observation_horizon_does_not_fabricate_gaps(self):
        result = choose([event(7)], ['2026-08-06', '2026-08-18'])
        self.assertEqual(result['home_unknown_intervals'], [])
        self.assertEqual(result['home_provenance']['testing_days_without_final'], [])
        self.assertEqual(result['home_provenance']['testing_days'], ['2026-08-06', '2026-08-18'])
        self.assertEqual(choose([], ['2026-08-06'])['home_unknown_intervals'], [])

    def test_unchanged_program_visit_remains_in_full_reviewed_calendar(self):
        result = choose([event(6), event(18)], ['2026-08-25', '2026-08-18', '2026-08-06'])
        self.assertEqual(len(result['home_transitions']), 1)
        self.assertEqual(result['home_provenance']['testing_days'],
                         ['2026-08-06', '2026-08-18', '2026-08-25'])
        self.assertEqual(result['home_provenance']['testing_day_count'], 3)
        self.assertEqual(result['home_provenance']['testing_days_without_final'], [])

    def test_empty_unrecognized_phases_and_group_mode_fallback(self):
        self.assertEqual(choose([])['home_transitions'], [])
        self.assertEqual(choose([event(7, phase='Unknown')])['home_transitions'], [])
        unknown = event(7); unknown['settings']['group'] = []
        result = choose([unknown])['home_transitions'][0]
        self.assertEqual(result['label'], 'Group not recorded · Mode not recorded')
        self.assertIn('exact activation time is not recorded', result['evidence'])
        self.assertIsNone(result['home_timing']['previous_configuration_last_observed'])

    def test_adaptive_state_change_is_retained(self):
        first, second = event(7), event(8)
        first['settings']['group'][1]['value'] = 'Closed loop'
        result = choose([first, second])['home_transitions']
        self.assertEqual([e['label'] for e in result], ['Group A · Closed loop', 'Group A · Open loop'])


class HomeCalendarTests(unittest.TestCase):
    def form(self, days=None, source_hash='a' * 64):
        return NS(record=[{'processing': {'timeline_testing_days': ['2026-08-06'] if days is None else days,
                                         'timeline_testing_days_sha256': source_hash}}])

    def test_valid_stored_calendar_used_and_version_in_provenance(self):
        with patch.object(home.models.ScaleForms, 'find', return_value=self.form(['2026-08-18', '2026-08-06'])):
            result = home.build_home_context(NS(institute='i'), [event(6)])
        self.assertEqual(len(result['home_transitions']), 1)
        self.assertEqual(result['home_provenance']['version'], home.VERSION)
        self.assertEqual(result['home_provenance']['testing_days_sha256'], 'a' * 64)
        self.assertEqual(result['home_provenance']['testing_days'], ['2026-08-06', '2026-08-18'])

    def test_missing_or_invalid_calendar_never_treats_clinic_as_home(self):
        forms = [None, NS(record=[]), NS(record=[None]), NS(record=[{'processing': None}]),
                 self.form([]), self.form('2026-08-06'), self.form(source_hash='bad'),
                 self.form(['2026-08-06', '2026-08-06']), self.form(['2026-02-30']),
                 self.form([None]), self.form(['20260806'])]
        for form in forms:
            with self.subTest(form=form), patch.object(home.models.ScaleForms, 'find', return_value=form):
                result = home.build_home_context(NS(), [event(6)])
                self.assertEqual(result['home_transitions'], [])
                self.assertEqual(result['home_provenance']['status'], 'not_ready')
                self.assertNotIn('testing_days', result['home_provenance'])
