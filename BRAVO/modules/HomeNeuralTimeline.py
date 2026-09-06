"""Read-only, unfiltered native Percept Timeline observations for home visits.

LFP and amplitude are device-recorded ten-minute averages (Medtronic FY25
white paper pp9-10), not instantaneous controller states or a transmission rate.
"""
import datetime as dt
import hashlib
import json
import math
import numbers
from collections import defaultdict
from zoneinfo import ZoneInfo
from pathlib import Path

from Server import models
from modules import Database, DataCurator, RedcapStimulation, RedcapHomePrograms, RCS08DataPolicy
from modules.RedcapHomeAdjustments import apply as apply_adjustments

VERSION = 'home-neural-timeline-1'
ZONE = ZoneInfo('America/Los_Angeles')
SIDES = ('left', 'right')


def finite(value):
    return float(value) if isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value) else None


def midnight(day):
    return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(), ZONE).timestamp()


def windows(days, now, window=None, start_date=None, end_date=None):
    """Default visit windows or 28 inclusive Pacific calendar dates.

    Date arithmetic deliberately precedes timezone conversion: subtracting a
    fixed number of seconds would shift midnight across daylight saving time.
    As with visit windows, the end is exclusive and no future data is included.
    """
    if window == 'custom':
        if not isinstance(start_date, str) or not isinstance(end_date, str):
            raise ValueError('Custom dates must use YYYY-MM-DD')
        first, last = dt.date.fromisoformat(start_date), dt.date.fromisoformat(end_date)
        today = dt.datetime.fromtimestamp(now, ZONE).date()
        if first.isoformat() != start_date or last.isoformat() != end_date or not first <= last <= today:
            raise ValueError('Invalid custom calendar range')
        return [{'id': 'custom', 'start': midnight(start_date),
                 'end': min(now, midnight((last + dt.timedelta(days=1)).isoformat())),
                 'start_date': start_date, 'end_date': end_date,
                 'label': f'Custom range · {start_date} to {end_date}'}]
    if start_date is not None or end_date is not None:
        raise ValueError('Dates require a custom window')
    if window == 'past28':
        end_day = dt.datetime.fromtimestamp(now, ZONE).date()
        start_day = end_day - dt.timedelta(days=27)
        return [{'id': 'past28', 'start': midnight(start_day.isoformat()), 'end': now,
                 'start_date': start_day.isoformat(), 'end_date': end_day.isoformat(),
                 'label': f'Past 28 days · {start_day.isoformat()} to {end_day.isoformat()}'}]
    if window is not None:
        raise ValueError('Unsupported home Timeline window')
    past = sorted(day for day in days if midnight(day) <= now)
    result = []
    for index, name in enumerate(('current', 'previous')):
        if len(past) <= index:
            continue
        else:
            day = past[-1-index]
            end = now if index == 0 else midnight(past[-1])
            result.append({'id': name, 'visit_date': day, 'start': midnight(day), 'end': end,
                           'label': name.capitalize() + ' stimulation visit · ' + day})
    return result


def field(settings, side, label):
    return next((row['value'] for row in settings.get(side, []) if row.get('label') == label), None)


def numeric_field(settings, side, label, unit=' LFP Power (LSB)'):
    value = field(settings, side, label)
    if not isinstance(value, str) or not value.endswith(unit):
        return None
    try:
        return finite(float(value[:-len(unit)]))
    except ValueError:
        return None


def controller_metadata(group):
    """Keep the original mapping evidence; absent ganging is ipsilateral only
    when an actual sensing channel with a local contact pair is present.
    """
    channels = RedcapStimulation.rows(RedcapStimulation.mapping(group.get('ProgramSettings')).get('SensingChannel'))
    result = {}
    for side in SIDES:
        selected = [channel for channel in channels if RedcapStimulation.leaf(channel.get('HemisphereLocation')).lower() == side]
        if len(selected) != 1:
            result[side] = {'sensing_side': None, 'mapping_status': 'unknown'}
            continue
        channel = selected[0]
        ganged = RedcapStimulation.leaf(channel.get('GangedToHemisphere')).lower()
        source = ganged if ganged in SIDES else side
        valid = 'GangedToHemisphere' not in channel or ganged in SIDES
        candidates = [item for item in channels if RedcapStimulation.leaf(item.get('HemisphereLocation')).lower() == source]
        signal = candidates[0] if len(candidates) == 1 else {}
        has_pair = RedcapStimulation.sense_contacts(signal.get('Channel'), source) != RedcapStimulation.UNKNOWN
        result[side] = {'sensing_side': source if valid and has_pair else None,
                        'mapping_status': ('contralateral' if source != side else 'ipsilateral') if valid and has_pair else 'unknown',
                        'threshold_mode': RedcapStimulation.leaf(channel.get('Mode')),
                        'sensing_status': RedcapStimulation.leaf(signal.get('BrainSensingStatus')),
                        'adaptive_state': RedcapStimulation.leaf(channel.get('AdaptiveTherapyStatus'))}
    return result


def snapshots(payload, source_id):
    result = RedcapStimulation.extract(payload)
    for event in result['events']:
        event['source_ids'] = [source_id]
        event['id'] = hashlib.sha256(json.dumps([source_id, event], sort_keys=True).encode()).hexdigest()[:20]
        if event['kind'] == 'settings_observed':
            group = next(group for group in payload['Groups'][event['phase']] if group.get('ActiveGroup') is True)
            event['controllers'] = controller_metadata(group)
    return result['events']


def observations(records, days, start, end):
    """Keep raw finite values; identical duplicate values collapse, conflicts
    become explicit nulls. Exclude any ten-minute bin possibly touching clinic.
    The export does not establish whether its stamp is the start or end, so a
    conservative +/- ten-minute exclusion is used around each clinic date.
    """
    samples = defaultdict(lambda: defaultdict(set))
    provenance = {'excluded_clinic_rows': 0, 'invalid_rows': 0, 'conflicting_values': 0}
    excluded = [(midnight(day)-600, midnight((dt.date.fromisoformat(day)+dt.timedelta(days=1)).isoformat())+600) for day in days]
    for device, recording in records:
        names = recording.get('ChannelNames', [])
        for index, raw_time in enumerate(recording.get('Time', [])):
            stamp = finite(raw_time)
            if stamp is None:
                provenance['invalid_rows'] += 1
                continue
            if stamp < start or stamp >= end:
                continue
            if any(lo <= stamp <= hi for lo, hi in excluded):
                provenance['excluded_clinic_rows'] += 1
                continue
            row = recording.get('Data', [])[index]
            for column, name in enumerate(names):
                # Native saved format is samples x channels, hemisphere names
                # are structural IDs. Never infer side from custom anatomy names.
                channel = next((side for side in SIDES if name == side.capitalize()+'Hemisphere LFP' or name == side.capitalize()+'Hemisphere Amplitude'), None)
                if channel is None:
                    continue
                kind = 'power' if name.endswith(' LFP') else 'amplitude'
                value = finite(row[column])
                samples[(device, stamp)][(channel, kind)].add(value)
    normalized = defaultdict(dict)
    for (device, stamp), channels in samples.items():
        normalized[device][stamp] = {}
        for key, values in channels.items():
            values = values - {None} if any(value is not None for value in values) else {None}
            conflict = len(values) > 1
            provenance['conflicting_values'] += int(conflict)
            normalized[device][stamp][key] = {'value': None if conflict else next(iter(values)), 'conflict': conflict}
    return normalized, provenance


def metadata(event, side):
    settings = event.get('settings', {}) if event else {}
    controller = event.get('controllers', {}).get(side, {}) if event else {}
    source_side = controller.get('sensing_side')
    state = controller.get('adaptive_state', '')
    threshold_mode = controller.get('threshold_mode', '')
    if state == 'RUNNING':
        mode = 'Closed loop · ' + ('single threshold' if 'SINGLE' in threshold_mode else 'dual threshold' if 'DUAL' in threshold_mode else 'threshold mode unknown')
    elif controller.get('sensing_status') == 'ENABLED':
        mode = 'Sensing only' + (' · adaptive paused' if state == 'SUSPENDED' else '')
    else:
        mode = 'Stimulation / sensing state not recorded'
    thresholds = []
    lower, upper = (numeric_field(settings, side, label) for label in ('Lower LFP threshold', 'Upper LFP threshold'))
    if source_side is not None and state == 'RUNNING':
        if 'SINGLE' in threshold_mode:
            # These exported fields describe thresholds, not necessarily the
            # capture pair. Do not apply the capture formula to unequal values.
            if lower is not None and lower == upper:
                thresholds = [{'label': 'Single LFP threshold', 'value': lower}]
        elif 'DUAL' in threshold_mode:
            thresholds = [{'label': label, 'value': value} for label, value in
                          [('Lower LFP threshold', lower), ('Upper LFP threshold', upper)] if value is not None]
    threshold_status = ('Threshold configuration/control state not recorded' if not state else
                        'Active configured threshold guide' if thresholds else
                        'Stored thresholds do not control stimulation in this sensing-only or paused observation' if state != 'RUNNING' else
                        'Controlling sensing source is not resolved' if source_side is None else
                        'Single-threshold export values differ; final controlling threshold is not resolved' if 'SINGLE' in threshold_mode else
                        'Active threshold mode or values are not recorded')
    frequency = numeric_field(settings, side, 'Biomarker center frequency', ' Hz')
    band = f'{frequency:g} Hz center · approximately 5 Hz selected band (Medtronic nominal)' if frequency is not None else 'Power-band center frequency not recorded'
    return {'threshold_status': threshold_status, 'mode': mode, 'adaptive_state': state or 'Not recorded', 'sensing_side': source_side,
            'mapping_status': controller.get('mapping_status', 'unknown'),
            'sensing_contacts': field(settings, side, 'Sensing contacts') or 'Not recorded',
            'center_frequency_hz': frequency, 'power_band_label': band,
            'thresholds': thresholds, 'threshold_mode': threshold_mode,
            'settings': settings, 'evidence': event.get('evidence', '') if event else 'No contemporaneous home settings observation',
            'settings_observed_at': event.get('time') if event else None}


def home_observations(events, days, source_hash):
    """Retain eligible confirmations as well as changed home configurations.

    A repeated Final can restore context after a logged interruption. Comparing
    controller metadata also prevents arbitrary source ordering from deciding
    an otherwise identical snapshot's sensing route.
    """
    context = RedcapHomePrograms.select(events, days, source_hash)
    by_day = defaultdict(list)
    for event in events:
        if event['kind'] == 'settings_observed' and event.get('phase') in ('Initial', 'Final'):
            by_day[dt.datetime.fromtimestamp(event['time'], ZONE).date().isoformat()].append(event)
    eligible, conflicts = [], []
    for day, observations in sorted(by_day.items()):
        if day in days:
            observations = [event for event in observations if event['phase'] == 'Final']
            if not observations:
                continue
            latest = max(event['time'] for event in observations)
            observations = [event for event in observations if event['time'] == latest]
        by_time = defaultdict(list)
        for event in observations:
            by_time[event['time']].append(event)
        for stamp, same in sorted(by_time.items()):
            merged = RedcapHomePrograms.merge_same_time(same)
            mapping_keys = {json.dumps(event.get('controllers', {}), sort_keys=True) for event in same}
            if merged is None or len(mapping_keys) != 1:
                conflicts.append(stamp)
                continue
            merged['settings'] = RedcapHomePrograms.program_settings(merged['settings'])
            merged['evidence'] += (' Latest unambiguous Final on the reviewed visit date; earlier clinic snapshots omitted.'
                                   if day in days else ' Home configuration observed between reviewed visits.')
            eligible.append(merged)
    context['home_transitions'] = eligible
    context['home_unknown_intervals'] += [{'start': stamp, 'end': next((event['time'] for event in eligible if event['time'] > stamp), None)} for stamp in conflicts]
    return context


def build_report(records, events_by_device, days, source_hash, now, adjustments=(), window=None, start_date=None, end_date=None):
    view_windows = windows(days, now, window, start_date, end_date)
    starts = [window['start'] for window in view_windows if window['start'] is not None]
    data, audit = observations(records, days, min(starts) if starts else now,
                               max(item['end'] for item in view_windows) if view_windows else now)
    devices = sorted(set(data) | set(events_by_device))
    contexts = {}
    for device in devices:
        events = events_by_device.get(device, [])
        context = home_observations(events, days, source_hash)
        context = apply_adjustments(context, list(adjustments), now)
        selected = context['home_transitions']
        # A later reviewed visit with no export breaks earlier setting evidence,
        # including visits newer than the last source snapshot.
        final_days = {dt.datetime.fromtimestamp(event['time'], ZONE).date().isoformat() for event in events if event.get('phase') == 'Final'}
        invalid = [midnight(day) for day in days if day not in final_days]
        invalid += [event['time'] for event in events if event['kind'] != 'settings_observed']
        invalid += [gap['start'] for gap in context['home_unknown_intervals']]
        contexts[device] = (selected, invalid)
    count = 0
    for window in view_windows:
        window['panels'] = []
        for side in SIDES:
            panel = {'side': side, 'segments': []}
            for device in devices:
                events, invalid = contexts[device]
                boundaries = sorted({window['start'], window['end']} | {event['time'] for event in events if window['start'] < event['time'] < window['end']} | {stamp for stamp in invalid if window['start'] < stamp < window['end']})
                for lo, hi in zip(boundaries, boundaries[1:]):
                    previous = [event for event in events if event['time'] <= lo]
                    event = previous[-1] if previous else None
                    if event and any(event['time'] < stamp <= lo for stamp in invalid):
                        event = None
                    info = metadata(event, side)
                    points = []
                    for stamp, row in sorted(data.get(device, {}).items()):
                        if not lo <= stamp < hi:
                            continue
                        power = row.get((info['sensing_side'], 'power'), {})
                        amplitude = row.get((side, 'amplitude'), {})
                        if not power and not amplitude:
                            continue
                        points.append({'time': stamp, 'power': power.get('value'), 'amplitude': amplitude.get('value'),
                                       'power_conflict': power.get('conflict', False), 'amplitude_conflict': amplitude.get('conflict', False)})
                    panel['segments'].append({'id': f'{window["id"]}:{device}:{side}:{lo}', 'device_id': device,
                                               'start': lo, 'end': hi, **info, 'points': points})
                    count += len(points)
            window['panels'].append(panel)
    return {'version': VERSION, 'status': 'ready', 'timezone': str(ZONE), 'generated_at': now,
            'visit_days': sorted(day for day in days if midnight(day) <= now),
            'units': {'power': 'LFP Power (LSB)', 'amplitude': 'mA'}, 'windows': view_windows,
            'provenance': {**audit, 'point_count': count, 'testing_days_sha256': source_hash,
                'testing_day_count': len(days), 'aggregation_seconds': 600,
                'source': 'Native DiagnosticData.LFPTrendLogs; device-stored ten-minute average power and amplitude',
                'processing': 'No outlier replacement, smoothing, resampling or inferred threshold crossings',
                'clinic_exclusion': 'Entire reviewed testing dates plus ten minutes on each boundary; bin stamp alignment is not documented',
                'mapping': 'Each panel is a stimulation side; biomarker follows the explicitly resolved sensing source in the same device/group',
                'settings_timing': 'Observed home snapshots, not proven exact activation times; no future settings backfill',
                'reference': 'Medtronic FY25 white paper pp9-10,14,17'}}


def read(participant, now, window=None, start_date=None, end_date=None):
    days, source_hash = RedcapHomePrograms.calendar(participant)
    view_windows = windows(days, now, window, start_date, end_date)
    reviewed = RCS08DataPolicy.applies_to(participant)
    events, accepted_sources = defaultdict(list), {}
    policy_hash = hashlib.sha256(Path(RCS08DataPolicy.__file__).read_bytes()).hexdigest()
    sources = models.SourceFile.find_all(owner=participant, type='MedtronicJSON').order_by()
    for source in sources:
        device = source.metadata.get('Device')
        if not device:
            continue
        extracted, _ = RedcapStimulation.source_context(source, participant, reviewed, policy_hash)
        if extracted['excluded']:
            continue
        accepted_sources[source.uid] = source
        for original in extracted['events']:
            if original['time'] > now:
                continue
            event = dict(original, source_ids=[source.uid])
            event['id'] = hashlib.sha256(json.dumps([source.uid, event], sort_keys=True).encode()).hexdigest()[:20]
            events[device].append(event)
    # The compact settings cache is sufficient to select the home observations.
    # Read only the selected exports overlapping the requested windows for original
    # controller fields. This avoids decrypting every large streaming export on
    # every page visit while retaining the exact source of each mapping.
    starts = [item['start'] for item in view_windows]
    start = min(starts) if starts else now
    raw = {}
    for device, observed in events.items():
        selected = home_observations(observed, days, source_hash)['home_transitions']
        relevant = [event for index, event in enumerate(selected) if index == len(selected)-1 or selected[index+1]['time'] >= start]
        for chosen in relevant:
            for uid in chosen['source_ids']:
                if uid not in raw:
                    raw[uid] = json.loads(DataCurator.loadCacheFile(accepted_sources[uid]))
                for event in observed:
                    if event['source_ids'] != [uid] or event['kind'] != 'settings_observed':
                        continue
                    active = [group for group in raw[uid].get('Groups', {}).get(event['phase'], []) if group.get('ActiveGroup') is True]
                    if len(active) == 1:
                        event['controllers'] = controller_metadata(active[0])
    records = []
    for recording in models.Recording.find_all(source__owner=participant, type='MedtronicChronicBrainSense'):
        if recording.source.uid in accepted_sources:
            records.append((recording.source.metadata['Device'], Database.loadSourceFile(recording.pointer, recording.hashed)))
    daily = models.ScaleForms.find(institute=participant.institute, name='RCS08 Daily PRO (REDCap)', record_type='REDCap API Sync')
    adjustments = daily.record[0]['processing'].get('timeline_home_adjustments', [])
    return build_report(records, events, days, source_hash, now, adjustments,
                        window=window, start_date=start_date, end_date=end_date)
