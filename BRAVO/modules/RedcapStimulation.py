"""Read-only stimulation context, preserving observed versus logged evidence.

Field scopes/units: Medtronic Percept FY25 white paper p34; clinician guide
pp38/42. No GroupHistory is used: later reports can rewrite that history.
Only root programmer boundaries date Initial/Final snapshots. Device log times
remain explicitly identified as device-clock observations, without inferred
clock correction or borrowing a later configuration for an earlier event.
"""
import datetime as dt
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from uuid import uuid4

from Server import models
from modules import DataCurator, RCS08DataPolicy, ReportCache

VERSION = 'redcap-stimulation-1'
UNKNOWN = 'Not recorded'
MIN_TIME = dt.datetime(2015, 1, 1, tzinfo=dt.timezone.utc).timestamp()


def mapping(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def leaf(value):
    return str(value).rsplit('.', 1)[-1] if value is not None else ''


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def quantity(value, unit):
    value = number(value)
    if value is not None and unit == 'ms' and value >= 1000:
        return f'{value / 1000:g} s ({value:g} ms)'
    return f'{value:g} {unit}' if value is not None else UNKNOWN


def state(value):
    return leaf(value).replace('_', ' ').capitalize() or UNKNOWN


def timestamp(value):
    try:
        value = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if value.tzinfo is None:
            return None
        stamp = value.timestamp()
        return stamp if MIN_TIME <= stamp else None
    except (ValueError, TypeError, OverflowError):
        return None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def entry(label, value):
    return {'label': label, 'value': value}


def contact(value, side):
    clean = re.sub(r'(?i)^sensight_?', '', leaf(value))
    if clean.lower() == 'case':
        return 'Case'
    match = re.fullmatch(r'([0-3])([abc]?)', clean.lower())
    if match:
        return str(int(match[1]) + (8 if side == 'right' else 0)) + match[2]
    return clean or UNKNOWN


def sense_contacts(value, side):
    words = leaf(value).split('_')
    numbers = {'ZERO': 0, 'ONE': 1, 'TWO': 2, 'THREE': 3}
    selected = [str(numbers[word] + (8 if side == 'right' else 0)) for word in words if word in numbers]
    return '–'.join(selected) if len(selected) == 2 else state(value)


def contacts(channel, side):
    labels, fractions, amplitudes, cathodes = [], [], [], []
    for electrode in rows(channel.get('ElectrodeState')):
        polarity = {'Positive': '+', 'Negative': '−'}.get(leaf(electrode.get('ElectrodeStateResult')))
        if not polarity:
            continue
        label = contact(electrode.get('Electrode'), side) + polarity
        labels.append(label)
        fraction = number(electrode.get('ElectrodeFractionOf64'))
        amplitude = number(electrode.get('ElectrodeAmplitudeInMilliAmps'))
        if fraction is not None:
            fractions.append(f'{label} {abs(fraction):g}/64')
        if amplitude is not None:
            amplitudes.append(f'{label} {amplitude:g} mA')
        if polarity == '−':
            cathodes.append((amplitude, fraction))
    # Multiple cathodes/OptiStim segment currents are not a program amplitude.
    fallback = cathodes[0][0] if len(cathodes) == 1 and cathodes[0][1] is None else None
    return ', '.join(labels) or UNKNOWN, '; '.join(fractions), '; '.join(amplitudes), fallback


def side_settings(channel, side, group_rate, target, controller=None):
    adaptive = mapping(channel.get('AdaptiveTherapy'))
    adaptive_state = leaf(channel.get('AdaptiveTherapyStatus'))
    running = adaptive_state == 'RUNNING'
    configured = adaptive_state not in ('', 'NOT_CONFIGURED')
    leads, fractions, electrode_currents, fallback = contacts(channel, side)
    source_side = leaf(channel.get('GangedToHemisphere')).lower()
    if source_side not in ('left', 'right'):
        source_side = side
    # Resolve the controlling lead explicitly. A local channel field on a
    # ganged program must never be relabeled as the other lead's contact pair.
    signal = mapping(controller) if source_side != side else channel
    sensing = mapping(signal.get('SensingSetup'))
    amp = number(channel.get('AmplitudeInMilliAmps'))
    if amp is None:
        amp = number(channel.get('SuspendAmplitudeInMilliAmps'))
    if amp is None:
        amp = fallback
    out = [entry('Tablet target', target), entry('Stimulation contacts', leads),
           entry('Frequency', quantity(channel.get('RateInHertz', group_rate), 'Hz')),
           entry('Pulse width', quantity(channel.get('PulseWidthInMicroSecond'), 'µs'))]
    if configured:
        lower = quantity(channel.get('LowerLimitInMilliAmps'), 'mA')
        upper = quantity(channel.get('UpperLimitInMilliAmps'), 'mA')
        out.append(entry('Adaptive amplitude range', f'{lower} to {upper}'))
    if not running:
        out.append(entry('Amplitude' if not configured else 'Fixed / paused amplitude', quantity(amp, 'mA')))
    if fractions:
        out.append(entry('Contact fractions', fractions))
    if electrode_currents and not running:
        out.append(entry('Exported contact amplitudes (snapshot)', electrode_currents))
    out += [entry('Sensing', state(channel.get('BrainSensingStatus'))),
            entry('Sensing source hemisphere', source_side.capitalize()),
            entry('Sensing contacts', sense_contacts(signal.get('Channel'), source_side)),
            entry('Biomarker center frequency', quantity(sensing.get('FrequencyInHertz'), 'Hz')),
            entry('Averaging duration', quantity(sensing.get('AveragingDurationInMilliSeconds'), 'ms')),
            entry('Adaptive state', state(channel.get('AdaptiveTherapyStatus')))]
    # Thresholds can be configured for sensing-only therapy too.
    for label, key in [('Lower LFP threshold', 'LowerLfpThreshold'), ('Upper LFP threshold', 'UpperLfpThreshold')]:
        if key in signal or configured:
            out.append(entry(label, quantity(signal.get(key), 'LFP Power (LSB)')))
    if configured:
        out += [entry('Threshold mode', state(channel.get('Mode'))),
                entry('Paused amplitude', quantity(channel.get('SuspendAmplitudeInMilliAmps'), 'mA'))]
        for label, key in [('Transition up', 'TransitionUpInMilliSeconds'), ('Transition down', 'TransitionDownInMilliSeconds')]:
            out.append(entry(label, quantity(channel.get(key), 'ms')))
        for label, key in [('Lower onset duration', 'LowerThresholdOnsetInMilliSeconds'),
                           ('Upper onset duration', 'UpperThresholdOnsetInMilliSeconds'),
                           ('Detection blanking duration', 'DetectionBlankingDurationInMilliSeconds'),
                           ('Adaptive startup delay', 'AdaptiveStartupDelayInMilliSeconds')]:
            out.append(entry(label, quantity(adaptive.get(key), 'ms')))
    return out


def duration_seconds(value, kind):
    for key in (f'{kind}DurationInSeconds', f'{kind}TimeInSeconds', f'Cycling{kind}DurationInSeconds',
                f'{kind}DurationSeconds', f'{kind}DurationInMilliSeconds'):
        if key in value:
            number_value = number(value[key])
            return number_value / 1000 if number_value is not None and 'MilliSeconds' in key else number_value
    return None


def group_label(group):
    key = leaf(group.get('GroupId'))
    return key.replace('GROUP_', 'Group ') if key else 'Group not recorded'


def settings_for(group, payload, phase):
    shared = mapping(group.get('GroupSettings'))
    program = mapping(group.get('ProgramSettings'))
    cycle = mapping(shared.get('Cycling'))
    soft = mapping(shared.get('SoftStartStop'))
    cycling = {True: 'On', False: 'Off'}.get(cycle.get('Enabled'), UNKNOWN)
    if cycle.get('Enabled') is True:
        cycling += f" · on {quantity(duration_seconds(cycle, 'On'), 's')} / off {quantity(duration_seconds(cycle, 'Off'), 's')}"
    soft_start = {True: 'On', False: 'Off'}.get(soft.get('Enabled'), UNKNOWN)
    if soft.get('Enabled') is True:
        soft_start += ' · ' + quantity(soft.get('DurationInSeconds'), 's')
    channels = rows(program.get('SensingChannel'))
    mode = 'Closed loop' if any(leaf(c.get('AdaptiveTherapyStatus')) == 'RUNNING' for c in channels) else 'Open loop / fixed stimulation'
    result = {'group': [entry('Group', group_label(group)), entry('Mode at observation', mode),
                       entry('Stimulation status', state(mapping(payload.get('Stimulation')).get(phase + 'StimStatus'))),
                       entry('Cycling', cycling), entry('High-pass filter', quantity(shared.get('HighPassFilterInHertz'), 'Hz')),
                       entry('Sensing blanking', quantity(shared.get('SensingBlankingDurationInMicroseconds'), 'µs')),
                       entry('SoftStart/Stop', soft_start)], 'left': [], 'right': []}
    # Tablet labels are source-derived; never substitute anatomical research labels.
    leads = rows(mapping(payload.get('LeadConfiguration')).get(phase))
    for side in ('left', 'right'):
        target = next((leaf(lead.get('LeadLocation')) for lead in leads
                       if leaf(lead.get('Hemisphere')).lower() == side), '')
        target = {'Gpi': 'GPi', 'Vim': 'VIM'}.get(target, target) or UNKNOWN
        selected = [c for c in channels if leaf(c.get('HemisphereLocation')).lower() == side]
        if not selected:
            selected = [c for c in rows(mapping(program.get(side.capitalize() + 'Hemisphere')).get('Programs'))
                        if c.get('Enabled') is not False]
        for index, channel in enumerate(selected):
            controlling_side = leaf(channel.get('GangedToHemisphere')).lower()
            controlling_channel = next((c for c in channels
                                       if leaf(c.get('HemisphereLocation')).lower() == controlling_side), None)
            fields = side_settings(channel, side, program.get('RateInHertz'), target, controlling_channel)
            if len(selected) > 1:
                fields = [entry(f'Program {index + 1} · {field["label"]}', field['value']) for field in fields]
            result[side].extend(fields)
        if not selected:
            result[side] = [entry('Settings', 'No side program recorded in this snapshot')]
    return result, mode


def unavailable():
    return {'group': [entry('Settings', 'No contemporaneous settings snapshot at this logged transition')],
            'left': [], 'right': []}


def configuration_fingerprint(settings):
    # Contact currents in an adaptive snapshot can vary without programming.
    # Program amplitude or adaptive limits still participate in this identity.
    return digest({scope: [field for field in values
                           if 'Exported contact amplitudes (snapshot)' not in field['label']]
                   for scope, values in settings.items()})


def extract(payload, reviewed=False):
    """Extract small, timeless per-source evidence; filtering by now happens later."""
    if not isinstance(payload, dict):
        return {'events': [], 'excluded': 'Malformed report'}
    if reviewed:
        reason = RCS08DataPolicy.source_exclusion(payload)
        if reason:
            return {'events': [], 'excluded': reason}
    start, end = timestamp(payload.get('SessionDate')), timestamp(payload.get('SessionEndDate'))
    if start is not None and end is not None and not 0 <= end - start < 8 * 3600:
        start = end = None
    events = []
    for phase, stamp in [('Initial', start), ('Final', end)]:
        if stamp is None:
            continue
        active = [g for g in rows(mapping(payload.get('Groups')).get(phase)) if g.get('ActiveGroup') is True]
        # Missing, ambiguous or inactive snapshots cannot identify a configuration.
        if len(active) != 1:
            continue
        settings, mode = settings_for(active[0], payload, phase)
        events.append({'time': stamp, 'kind': 'settings_observed', 'phase': phase,
                       'label': f'{group_label(active[0])} · {mode} · Settings observed',
                       'settings': settings,
                       'evidence': f'{phase} active-group snapshot at programmer {"SessionDate" if phase == "Initial" else "SessionEndDate"}. '
                                   'Observation time; exact setting-change time is not known.'})
    for event in rows(mapping(payload.get('DiagnosticData')).get('EventLogs')):
        stamp = timestamp(event.get('DateTime'))
        if stamp is None or 'ParameterTrendId' not in event:
            continue
        if leaf(event.get('NewGroupId')) in ('GROUP_A', 'GROUP_B', 'GROUP_C', 'GROUP_D'):
            if event.get('NewGroupId') == event.get('OldGroupId'):
                continue
            kind, label = 'group_change', group_label({'GroupId': event['NewGroupId']}) + ' · Logged group change'
        elif leaf(event.get('TherapyStatus')) in ('ON', 'OFF'):
            kind, label = 'stimulation_status', 'Stimulation ' + leaf(event['TherapyStatus']).lower()
        elif leaf(event.get('AdbsStatus')) in ('ON', 'OFF'):
            kind, label = 'adaptive_status', 'Adaptive therapy ' + leaf(event['AdbsStatus']).lower()
        else:
            continue
        events.append({'time': stamp, 'kind': kind, 'label': label, 'settings': unavailable(),
                       'evidence': 'Diagnostic EventLogs timestamp (device clock, no inferred correction). '
                                   'The log records this change, but does not specify the complete settings at that time.'})
    return {'events': events, 'excluded': None}


def source_context(source, participant, reviewed, policy_hash, *, cached_only=False):
    """Persist compact settings, or read only existing evidence with ``cached_only``.

    A read-only miss returns (None, False); it never scans raw exports or creates
    cache files/directories. Existing timeline callers retain normal population.
    """
    identity = [VERSION, policy_hash, str(participant.uid), source.uid, source.hashed,
                source.pointer, source.metadata, reviewed]
    root = ((Path(os.environ['DATASERVER_PATH']) / 'report-cache') if cached_only
            else ReportCache.directory()) / 'redcap-stimulation'
    if not cached_only:
        root.mkdir(parents=True, exist_ok=True)
    path = root / (digest(identity) + '.json')
    try:
        saved = json.loads(path.read_text())
        if isinstance(saved, dict) and isinstance(saved.get('events'), list) and 'excluded' in saved:
            return saved, True
    except (OSError, ValueError):
        pass
    if cached_only:
        return None, False
    if source.metadata.get('AnalysisExclusion'):
        result = {'events': [], 'excluded': source.metadata['AnalysisExclusion']}
    else:
        # Read errors are not cached as an empty success; let the caller retry.
        result = extract(json.loads(DataCurator.loadCacheFile(source)), reviewed)
    temporary = path.with_suffix('.' + uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(result, allow_nan=False))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return result, False


def build_context(participant, now=None):
    from modules.RedcapHomePrograms import build_home_context
    from modules.RedcapComparisons import home_signature
    now = time.time() if now is None else now
    reviewed = RCS08DataPolicy.applies_to(participant)
    policy_hash = hashlib.sha256(Path(RCS08DataPolicy.__file__).read_bytes()).hexdigest()
    # MySQL filesort copies the large JSON metadata into its bounded sort buffer.
    # Sort this small source inventory in Python instead; settings are cached below.
    sources = sorted(models.SourceFile.find_all(owner=participant, type='MedtronicJSON').order_by(),
                     key=lambda source: source.uid)
    unique, source_count, excluded_count, hits = {}, 0, 0, 0
    comparison_snapshots = []
    for source in sources:
        source_count += 1
        extracted, cached = source_context(source, participant, reviewed, policy_hash)
        hits += int(cached)
        excluded_count += int(bool(extracted['excluded']))
        for event in extracted['events']:
            if event['time'] > now or (reviewed and event['time'] < RCS08DataPolicy.IMPLANT_DAY):
                continue
            if event['kind'] == 'settings_observed':
                comparison_snapshots.append({'source': Path(getattr(source, 'name', '')).name,
                    'phase': event['phase'], 'signature': home_signature(event['settings'])})
            key = digest([event['time'], event['kind'], event['label'], event['settings'], event.get('phase')])
            if key not in unique:
                unique[key] = dict(event, id=key[:20], source_ids=[])
            unique[key]['source_ids'].append(source.uid)
    result, previous = [], None
    for event in sorted(unique.values(), key=lambda e: (e['time'], e.get('phase') == 'Final', e['id'])):
        if event['kind'] == 'settings_observed':
            fingerprint = configuration_fingerprint(event['settings'])
            if fingerprint == previous:
                continue
            previous = fingerprint
        else:
            # A logged transition can invalidate a preceding snapshot even if the
            # next observed configuration happens to match that older snapshot.
            previous = None
        result.append(event)
    return {**build_home_context(participant, list(unique.values())), 'transitions': result,
        '_comparison_snapshots': comparison_snapshots, 'provenance': {
        'version': VERSION, 'source_count': source_count, 'excluded_source_count': excluded_count,
        'cached_source_count': hits, 'transition_count': len(result), 'policy_sha256': policy_hash,
        'settings_clock': 'Validated root clinician-programmer SessionDate / SessionEndDate',
        'logged_transition_clock': 'Diagnostic device event times, without inferred clock correction',
        'settings_assignment': 'Snapshot observations only; no assumed activation time or future configuration backfill',
        'units_reference': 'Medtronic Percept FY25 white paper pp9,16,34; clinician programming guide pp38,42',
    }}
