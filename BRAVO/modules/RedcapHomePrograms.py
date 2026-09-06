"""Select observed take-home programs without promoting interim clinic tests.

The reviewed visit calendar is published with the normal daily REDCap sync.
On a visit date only the last unambiguous Final snapshot is eligible. Between
visits, changed observations are retained with explicitly uncertain activation
times. This is an observation-based selection rule, not proof of departure.
"""
import copy
import datetime as dt
import hashlib
import json
import re
from collections import defaultdict
from zoneinfo import ZoneInfo

from Server import models

VERSION = 'redcap-home-programs-3'
ZONE = ZoneInfo('America/Los_Angeles')


def calendar(participant):
    form = models.ScaleForms.find(institute=getattr(participant, 'institute', None),
                                  name='RCS08 Daily PRO (REDCap)', record_type='REDCap API Sync')
    record = getattr(form, 'record', None)
    audit = record[0].get('processing', {}) if isinstance(record, list) and record and isinstance(record[0], dict) else {}
    if not isinstance(audit, dict):
        audit = {}
    days, source_hash = audit.get('timeline_testing_days'), audit.get('timeline_testing_days_sha256')
    if not isinstance(days, list) or not days or not re.fullmatch('[0-9a-f]{64}', str(source_hash)):
        raise ValueError('Reviewed testing calendar needs an updated daily data sync')
    try:
        normalized = {dt.date.fromisoformat(day).isoformat() for day in days}
        if len(normalized) != len(days) or normalized != set(days):
            raise ValueError('Duplicated or noncanonical testing dates')
    except (ValueError, TypeError) as error:
        raise ValueError('Stored reviewed testing calendar is invalid') from error
    return normalized, source_hash


def program_settings(settings):
    """Ignore transient on/off and sampled segment current, retain programming."""
    return {scope: [copy.deepcopy(field) for field in fields
                    if field['label'] != 'Stimulation status'
                    and 'Exported contact amplitudes (snapshot)' not in field['label']]
            for scope, fields in settings.items()}


def fingerprint(settings):
    return hashlib.sha256(json.dumps(program_settings(settings), sort_keys=True).encode()).hexdigest()


def merge_same_time(events):
    """A conflicting same-time observation must not win by arbitrary file order."""
    if len({fingerprint(event['settings']) for event in events}) != 1:
        return None
    result = copy.deepcopy(sorted(events, key=lambda e: (e.get('phase') != 'Final', e['id']))[0])
    result['source_ids'] = sorted({uid for event in events for uid in event['source_ids']})
    return result


def open_gap(intervals, start, reason):
    """Keep one continuous unknown interval until another usable observation."""
    if not intervals or intervals[-1]['end'] is not None:
        intervals.append({'start': start, 'end': None, 'reason': reason})


def select(events, testing_days, source_hash):
    by_day = defaultdict(list)
    for event in events:
        if event['kind'] == 'settings_observed' and event.get('phase') in ('Initial', 'Final'):
            day = dt.datetime.fromtimestamp(event['time'], ZONE).date().isoformat()
            by_day[day].append(event)
    # Missing whole visit days must not silently carry forward the earlier
    # program. Stay within actual observation coverage, not future calendar days.
    if by_day:
        first_day, last_day = min(by_day), max(by_day)
        for day in testing_days:
            if first_day <= day <= last_day:
                by_day.setdefault(day, [])
    selected, ambiguous, unavailable, unknown = [], [], [], []
    previous, last_confirmed = None, None
    ignored = 0
    for day, observations in sorted(by_day.items()):
        candidates = []
        if day in testing_days:
            finals = [event for event in observations if event['phase'] == 'Final']
            if not finals:
                unavailable.append(day)
                ignored += len(observations)
                start = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(), ZONE).timestamp()
                open_gap(unknown, start, f'No usable final program snapshot for the reviewed testing date {day}; '
                         'the day boundary is conservative, not an exact change time.')
                previous = last_confirmed = None
                continue
            latest = max(event['time'] for event in finals)
            same_time = [event for event in finals if event['time'] == latest]
            ignored += len(observations) - len(same_time)
            candidates.append((latest, merge_same_time(same_time)))
        else:
            by_time = defaultdict(list)
            for event in observations:
                by_time[event['time']].append(event)
            candidates = [(stamp, merge_same_time(same_time)) for stamp, same_time in sorted(by_time.items())]
        for observed_time, event in candidates:
            if event is None:
                ambiguous.append({'day': day, 'time': observed_time, 'reason': 'Conflicting settings at the same latest observation time'})
                open_gap(unknown, observed_time, 'Conflicting program settings at the same observation time.')
                previous = last_confirmed = None
                continue
            if unknown and unknown[-1]['end'] is None:
                unknown[-1]['end'] = observed_time
            identity = fingerprint(event['settings'])
            if identity == previous:
                ignored += 1
                last_confirmed = event['time']
                continue
            event['scope'] = 'home_program'
            event['settings'] = program_settings(event['settings'])
            shared = {field['label']: field['value'] for field in event['settings']['group']}
            mode = shared.get('Mode at observation', 'Mode not recorded')
            if mode == 'Open loop / fixed stimulation':
                mode = 'Open loop'
            event['label'] = shared.get('Group', 'Group not recorded') + ' · ' + mode
            event['home_timing'] = {
                'observation_time': event['time'], 'previous_configuration_last_observed': last_confirmed,
                'activation_time_known': False,
                'selection': 'post_visit_final' if day in testing_days else 'between_visit_first_observation',
            }
            if day in testing_days:
                event['evidence'] = ('Post-visit program observed in the last available, unambiguous Final snapshot on this reviewed testing date. '
                                     'Earlier clinic-test snapshots are omitted. This is the observation time, not a proven departure or exact activation time.')
            else:
                event['evidence'] = ('First observed changed program between reviewed testing visits. '
                                     'The program was already present at this snapshot; the exact activation time is not recorded.')
                if last_confirmed is not None:
                    earlier = dt.datetime.fromtimestamp(last_confirmed, ZONE).strftime('%d %b %Y %H:%M %Z')
                    event['evidence'] += f' The previous configuration was last observed on {earlier}.'
            event['id'] = hashlib.sha256((VERSION + ':' + event['id']).encode()).hexdigest()[:20]
            selected.append(event)
            previous, last_confirmed = identity, event['time']
    return {'home_transitions': selected, 'home_unknown_intervals': unknown, 'home_provenance': {
        'version': VERSION, 'status': 'ready', 'testing_days_sha256': source_hash,
        # Publish the reviewed calendar itself: identical take-home programs may
        # suppress a transition, but must never erase a stimulation visit.
        'testing_days': sorted(testing_days),
        'testing_day_count': len(testing_days), 'selected_count': len(selected),
        'suppressed_observation_count': ignored, 'ambiguous_observations': ambiguous,
        'testing_days_without_final': unavailable,
        'unknown_interval_count': len(unknown),
        'gap_scope': 'Reviewed testing dates within available snapshot-day coverage; no claim about unobserved dates outside that horizon',
        'selection': 'Last unambiguous Final on reviewed testing days; first changed observation between visits',
        'timing': 'Observed configurations; exact activation times are not inferred from device clocks',
    }}


def build_home_context(participant, events):
    try:
        days, source_hash = calendar(participant)
    except ValueError as error:
        return {'home_transitions': [], 'home_unknown_intervals': [], 'home_provenance': {
            'version': VERSION, 'status': 'not_ready', 'reason': str(error), 'selected_count': 0}}
    return select(events, days, source_hash)
