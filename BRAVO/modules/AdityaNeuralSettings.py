"""Source-bound display context for native trends; never alter scientific samples.

Reports must come through DataCurator.loadPerceptJSON so all history/event dates
use the canonical first-carrier tablet clock. Source snapshots establish recorded
configuration, not continuous stimulation delivery or individual threshold crossings.
"""
from collections import defaultdict
from datetime import datetime
import re
import math

from modules.AdityaPresentation import finite

VERSION = 'source-settings-v1'
SIDES = ('left', 'right')
SENSING_CONTACTS = {'ZERO_AND_THREE', 'ONE_AND_THREE', 'ZERO_AND_TWO', 'ZERO_AND_ONE', 'TWO_AND_THREE', 'ONE_AND_TWO'}
MODE = {'AdaptiveModeDef.DUAL_THRESHOLD_DIRECT': 'Dual-threshold adaptive',
        'AdaptiveModeDef.DUAL_THRESHOLD_INVERSE': 'Dual-threshold inverse adaptive',
        'AdaptiveModeDef.SINGLE_THRESHOLD': 'Single-threshold adaptive'}


def epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _side(value):
    return {'HemisphereLocationDef.Left': 'left', 'HemisphereLocationDef.Right': 'right'}.get(value)


def _contacts(states):
    """Keep source electrode codes; presentation may humanize known device enums."""
    return ' '.join(re.sub(r'^ElectrodeDef\.Sen[Ss]ight_', '', str(s.get('Electrode', ''))).replace('ElectrodeDef.Case', 'C') + ('−' if s.get('ElectrodeStateResult') == 'ElectrodeStateDef.Negative' else '+')
                    for s in states if s.get('ElectrodeStateResult') in ('ElectrodeStateDef.Negative', 'ElectrodeStateDef.Positive'))


def _configuration(group):
    settings = {'group': [{'label': 'Group', 'value': re.sub(r'^GroupIdDef\.GROUP_([A-D])$', r'Group \1', group.get('GroupId', ''))}], 'left': [], 'right': []}
    channels = group.get('ProgramSettings', {}).get('SensingChannel', [])
    descriptors = []
    for channel in channels:
        side = _side(channel.get('HemisphereLocation'))
        if side is None:
            continue
        setup = channel.get('SensingSetup', {})
        signal = setup.get('ChannelSignalResult', {}).get('Channel', '')
        source = _side(channel.get('GangedToHemisphere')) or side
        # ChannelSignalResult explicitly identifies the sensing lead, including ganged controls.
        if signal.endswith('_LEFT'):
            source = 'left'
        elif signal.endswith('_RIGHT'):
            source = 'right'
        # GroupHistory often omits the signal-check PSD block but retains the
        # explicit bipolar Channel and gang fields. Those are source settings too.
        contact_enum = str(channel.get('Channel', '')).rsplit('.', 1)[-1]
        if not signal and contact_enum in SENSING_CONTACTS:
            signal = contact_enum.replace('_AND_', '_') + '_' + source.upper()
        mode = channel.get('Mode')
        status = channel.get('AdaptiveTherapyStatus')
        configured = status in ('ADBSStatusDef.RUNNING', 'ADBSStatusDef.SUSPENDED')
        sensing_only = status == 'ADBSStatusDef.NOT_CONFIGURED'
        state_unverified = not configured and not sensing_only
        has_configuration = configured or mode in MODE
        mode_label = MODE.get(mode, mode or ('Sensing only' if sensing_only else 'Mode not recorded'))
        thresholds_recorded = has_configuration and any(finite(channel.get(field)) is not None for field in ('LowerLfpThreshold', 'UpperLfpThreshold'))
        descriptors.append({'side': side, 'source': source, 'contacts': signal.rsplit('.', 1)[-1],
                            'hz': finite(setup.get('FrequencyInHertz')), 'mode': mode_label,
                            'adaptive': configured, 'state_unverified': state_unverified, 'thresholds_recorded': thresholds_recorded, 'configuration_recorded': has_configuration, 'mapping_verified': configured and (channel.get('GangedToHemisphere') is None or _side(channel.get('GangedToHemisphere')) == source)})
        rows = settings[side]
        def add(label, value):
            if value is not None and value != '':
                rows.append({'label': label, 'value': str(value)})
        def number(label, field, unit):
            value = finite(channel.get(field, group.get('ProgramSettings', {}).get(field)))
            if value is not None:
                add(label, f'{value:g} {unit}'.strip())
        add('Stimulation contacts (lead-local source)', _contacts(channel.get('ElectrodeState', [])))
        number('Frequency', 'RateInHertz', 'Hz')
        number('Pulse width', 'PulseWidthInMicroSecond', 'µs')
        number('Paused amplitude (configured)', 'SuspendAmplitudeInMilliAmps', 'mA')
        number('Adaptive minimum (configured)', 'LowerLimitInMilliAmps', 'mA')
        number('Adaptive maximum (configured)', 'UpperLimitInMilliAmps', 'mA')
        add('Sensing source hemisphere', source)
        if channel.get('GangedToHemisphere') is not None:
            add('Recorded ganged-to hemisphere', _side(channel['GangedToHemisphere']) or channel['GangedToHemisphere'])
        add('Sensing contacts', signal.rsplit('.', 1)[-1])
        hz = finite(setup.get('FrequencyInHertz'))
        if hz is not None:
            add('Sensing center frequency', f'{hz:g} Hz')
        add('Control mode (configured)', mode_label)
        add('Adaptive state at observation', {'ADBSStatusDef.RUNNING':'Adapting', 'ADBSStatusDef.NOT_CONFIGURED':'Not configured', 'ADBSStatusDef.SUSPENDED':'Suspended'}.get(channel.get('AdaptiveTherapyStatus'), channel.get('AdaptiveTherapyStatus')))
        if has_configuration:
            number('Lower threshold (configured)', 'LowerLfpThreshold', 'LSB')
            number('Upper threshold (configured)', 'UpperLfpThreshold', 'LSB')
            number('Transition up', 'TransitionUpInMilliSeconds', 'ms')
            number('Transition down', 'TransitionDownInMilliSeconds', 'ms')
        averaging = finite(setup.get('AveragingDurationInMilliSeconds'))
        if averaging is not None:
            add('Sensing averaging duration', f'{averaging:g} ms')
    cycle = group.get('GroupSettings', {}).get('Cycling', {}).get('Enabled')
    if isinstance(cycle, bool):
        settings['group'].append({'label': 'Cycling', 'value': 'On' if cycle else 'Off'})
    return settings, descriptors


def source_context(report, segment, source_id):
    """Recover matching active configurations from the exact source, without carry-forward."""
    low, high = segment['start'], segment['end']
    expected = segment.get('sensing_contacts')
    hz = finite(segment.get('center_frequency_hz'))
    raw = [(epoch(h.get('SessionDate')), 'Group history', h.get('Groups', [])) for h in report.get('GroupHistory', [])]
    raw += [(epoch(report.get('SessionDate')), 'Initial settings', report.get('Groups', {}).get('Initial', [])),
            (epoch(report.get('SessionEndDate')), 'Final settings', report.get('Groups', {}).get('Final', []))]
    observations = []
    any_matches = False
    for time, kind, groups in raw:
        if time is None:
            continue
        for group in groups:
            if group.get('ActiveGroup') is not True:
                continue
            settings, descriptors = _configuration(group)
            matches = [d for d in descriptors if d['contacts'] == expected and d['hz'] is not None and hz is not None and round(d['hz'], 1) == round(hz, 1)]
            any_matches = any_matches or bool(matches)
            observations.append({'id': f'{source_id}:{time}:{kind}:{group.get("GroupId", "")}', 'time': time,
                'source_id': source_id, 'kind': kind, 'active_group': group.get('GroupId'), 'settings': settings,
                'evidence': 'Original device report, canonical tablet time; configured values, not per-sample delivered stimulation.',
                '_descriptors': matches, '_matches': bool(matches)})
    if not observations:
        return {'status': 'unavailable', 'source_ids': [source_id], 'observations': [],
                'message': 'The original recording source was inspected, but its active settings snapshots do not match this sensing channel and frequency.'}
    observations.sort(key=lambda o: (o['time'], o['kind']))
    before = [o for o in observations if o['time'] <= low]
    after = [o for o in observations if o['time'] >= high]
    inside = [o for o in observations if low < o['time'] < high]
    selected = ([o for o in before if o['time'] == before[-1]['time']] if before else []) + inside + ([o for o in after if o['time'] == after[0]['time']] if after else [])
    # History omits fields such as adaptive min/max that Initial/Final record.
    # Keep the complete source snapshot visible at its own date, and never turn
    # an omitted history field into a fictitious zero or an apparent conflict.
    complete = max((o for o in observations if o['_matches'] or not any_matches), key=lambda o: (sum(len(rows) for rows in o['settings'].values()), -abs(o['time'] - high)))
    if complete not in selected:
        selected.append(complete)
    recorded = defaultdict(set)
    for observation in selected:
        for scope, rows in observation['settings'].items():
            for row in rows:
                recorded[(scope, row['label'])].add(row['value'])
    status = 'source_linked' if all(o['_matches'] for o in selected) and all(len(values) == 1 for values in recorded.values()) else 'conflict'
    events = report.get('DiagnosticData', {}).get('EventLogs', [])
    transitions = [e for e in events if (t := epoch(e.get('DateTime'))) is not None and low <= t < high
                   and any(k in e for k in ('NewGroupId', 'TherapyStatus', 'AdbsStatus'))]
    prior = [e for e in events if 'AdbsStatus' in e and (t := epoch(e.get('DateTime'))) is not None and t < low]
    prior_status = None
    if prior:
        last = max(epoch(e['DateTime']) for e in prior)
        latest = [e for e in prior if epoch(e['DateTime']) == last]
        values = sorted({str(e['AdbsStatus']) for e in latest})
        prior_status = {'time': last, 'values': values, 'conflict': len(values) > 1,
                        'hemisphere_recorded': all('Hemisphere' in e or 'HemisphereLocation' in e for e in latest)}
    bounded = bool(before and after)
    message = ('Dated active-group settings observations bracket this interval. ' if bounded else
               'The source records this configuration at the observation times below; it does not bracket the full interval. ')
    message += ('The source contains therapy/group/adaptive status changes within this interval. ' if transitions else
                'No therapy/group/adaptive status changes are recorded within this interval. ')
    message += 'Status logs and settings snapshots do not prove uninterrupted adaptive delivery at every ten-minute sample; plotted current retains its actual recorded values.'
    if prior_status and prior_status['conflict']:
        message += (' Latest prior adaptive-status entries at ' + str(latest[0]['DateTime'])
                    + ' disagree (' + '/'.join(value.rsplit('.', 1)[-1] for value in values) + ')'
                    + ('.' if prior_status['hemisphere_recorded'] else ' and do not identify the hemisphere.')
                    + ' These entries cannot establish a unique continuous adaptive-delivery state.')
    if status == 'conflict':
        message = 'The source settings observations differ or do not all match the plotted sensing label; inspect each dated configuration. ' + message
    if not any_matches:
        frequency = f'{hz:g} Hz' if hz is not None else 'an unrecorded center frequency'
        message = (f'The plotted sensing channel {expected} at {frequency} does not match the active settings in its original source. '
                   'The recovered source configurations are shown below at their own observation times; they are not assigned to this trace. ' + message)
    descriptors = complete['_descriptors']
    controls = sorted({d['source'].title() + ' sensing → ' + d['side'].title() + ' stimulation' for d in descriptors if d['mapping_verified']})
    modes = sorted({d['mode'] for d in descriptors})
    if any(d['state_unverified'] for d in descriptors):
        message += ' The adaptive-status field is missing or unrecognized at a source observation; recorded mode and thresholds do not establish its delivery state.'
    result = {'status': status, 'source_ids': [source_id], 'observations': selected,
              'message': message, 'mapping_description': ('; '.join(controls) + ' (source configuration)') if controls and not any(d['state_unverified'] for d in descriptors) else 'Adaptive control state is unverified; source configuration is recorded' if any(d['state_unverified'] for d in descriptors) else 'Adaptive controller relationship could not be reconciled' if any(d['adaptive'] for d in descriptors) else 'Sensing only; no adaptive control configured',
              'mode_description': ' / '.join(modes) + ' · source configuration',
              'thresholds_recorded': any(d['thresholds_recorded'] for d in descriptors),
              'state_unverified': any(d['state_unverified'] for d in descriptors),
              'control_configured': bool(controls), 'mapping_verified': all(d['mapping_verified'] for d in descriptors if d['configuration_recorded']) and not any(d['state_unverified'] for d in descriptors),
              'settings': complete['settings'],
              'chronology': {'bracketed': bounded, 'status_changes_in_interval': len(transitions),
                             'continuous_delivery_verified': False, 'latest_prior_adaptive_status': prior_status}}
    for observation in selected:
        observation.pop('_descriptors')
        observation.pop('_matches')
    return result


def _compatible(contexts):
    recorded = defaultdict(set)
    for context in contexts:
        for scope, rows in context.get('settings', {}).items():
            for row in rows:
                recorded[(scope, row['label'])].add(row['value'])
    return all(len(values) == 1 for values in recorded.values())


def link_settings(result, recordings, load_report, *, native_series=None, pair_keys=None):
    """Join only through contributing Recording.source; deduplicate raw reads per request."""
    contributors = defaultdict(list)
    for recording in recordings:
        uid = recording.get('SourceId')
        if not uid:
            continue
        names = recording.get('ChannelNames', [])
        side = 'left' if names and str(names[0]).upper().startswith('LEFT') else 'right' if names and str(names[0]).upper().startswith('RIGHT') else None
        native = native_series([recording], []) if native_series is not None else None
        if native is not None:
            canonical = {(channel, finite(time)): finite(hz) for channel, series in native.items()
                         for time, hz in zip(series['t'], series['center_hz'])}
            if pair_keys is not None:
                times = list(recording.get('Time', []))
                keys = pair_keys(recording, times, (side or '').upper(), str(names[0]) if names else '')
                # Follow home_timeline's canonical fallback exactly: a retained
                # amplitude-only/unknown-band point still has an original source.
                entries = [(key, canonical.get((key, finite(time))), finite(time)) for key, time in zip(keys, times)]
            else:
                entries = [(channel, hz, time) for (channel, time), hz in canonical.items()]
        else:
            entries = [(None, None, finite(value)) for value in recording.get('Time', [])]
        for channel, hz, time in entries:
            if time is not None:
                contributors[(side, channel, hz, time)].append((str(uid), str(recording.get('RecordingId', ''))))
    reports = {}
    for key in ('windows', 'observation_windows'):
        for window in result.get(key, []):
            for panel in window.get('panels', []):
                for segment in panel.get('segments', []):
                    carried = defaultdict(list)
                    record_ids = set()
                    covered_times = set()
                    for point in segment['points']:
                        channel = segment.get('source_channel', segment.get('sensing_contacts')) if native_series is not None else None
                        hz = finite(segment.get('center_frequency_hz')) if native_series is not None else None
                        origins = contributors.get((panel['side'], channel, hz, point['time']), [])
                        if origins:
                            covered_times.add(point['time'])
                        for source_id, row_id in set(origins):
                            if point['time'] not in carried[source_id]:
                                carried[source_id].append(point['time'])
                            record_ids.add(row_id)
                    if not carried:
                        continue
                    contexts = []
                    coverage = []
                    for source_id, times in sorted(carried.items()):
                        if source_id not in reports:
                            try:
                                reports[source_id] = load_report(source_id)
                                if not isinstance(reports[source_id], dict):
                                    reports[source_id] = None
                            except Exception:
                                # A source failure must not suppress valid neural data.
                                reports[source_id] = None
                        bounded = dict(segment, start=min(times), end=math.nextafter(max(times), math.inf))
                        coverage.append({'source_id': source_id, 'start': bounded['start'], 'end': bounded['end'], 'samples': len(times)})
                        if reports[source_id] is None:
                            context = {'status': 'unavailable', 'source_ids': [source_id], 'observations': [],
                                       'message': 'The original recording source could not be read; neural samples remain available. Source settings require a successful source read.'}
                        else:
                            try:
                                context = source_context(reports[source_id], bounded, source_id)
                            except (KeyError, TypeError, ValueError, AttributeError):
                                context = {'status': 'unavailable', 'source_ids': [source_id], 'observations': [],
                                           'message': 'The original source report was read but its settings structure could not be verified; neural samples remain available.'}
                        contexts.append(context)
                    context = dict(contexts[0])
                    fully_carried = len(covered_times) == len(segment['points'])
                    linked = fully_carried and all(c['status'] == 'source_linked' for c in contexts) and _compatible(contexts)
                    context['status'] = 'source_linked' if linked else 'unavailable' if all(c['status'] == 'unavailable' for c in contexts) else 'conflict'
                    context['source_ids'] = sorted(carried)
                    context['recording_ids'] = sorted(record_ids)
                    context['source_sample_coverage'] = coverage
                    context['observations'] = [o for c in contexts for o in c['observations']]
                    context['message'] = ' '.join(dict.fromkeys(c['message'] for c in contexts))
                    if not fully_carried:
                        context['message'] += ' Original source identity is missing for some samples in this segment.'
                    if context['status'] == 'conflict':
                        context['message'] = 'Contributing source configurations differ or cannot all be verified; inspect the dated records. ' + context['message']
                    segment['settings_context'] = context
                    if linked:
                        segment['settings'] = context['settings']
                        segment['mode'] = context['mode_description']
                        segment['mapping_status'] = 'source_recorded' if context['control_configured'] and context['mapping_verified'] else 'unknown' if context['thresholds_recorded'] or context['state_unverified'] else 'not_configured'
                        segment['threshold_status'] = 'source_recorded' if context['thresholds_recorded'] else 'unknown' if context['state_unverified'] else 'not_configured'
                        segment['control_mapping'] = context['mapping_description']
                        segment['evidence'] += ' Original recording-source settings are linked below; configured values do not replace measured current.'
    return result
