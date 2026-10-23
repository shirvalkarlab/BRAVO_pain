"""Automatic descriptive program comparisons from stored, verified source boundaries.

This presentation join never recomputes outcomes, reads providers or carries a
program across calendar days. Source reports must be read by the canonical
DataCurator loader. Initial/Final root timestamps are programmer/tablet times.
A boundary association does not establish uninterrupted stimulation delivery.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
import statistics
from zoneinfo import ZoneInfo

POLICY_VERSION = 'source-boundary-program-comparisons-v1'
PACIFIC = ZoneInfo('America/Los_Angeles')
MIN_SURVEYS = 5
SIDES = ('left', 'right')
ADAPTIVE = ('Mode', 'LowerLfpThreshold', 'UpperLfpThreshold', 'LowerLimitInMilliAmps',
            'UpperLimitInMilliAmps', 'LowerCaptureAmplitudeInMilliAmps', 'UpperCaptureAmplitudeInMilliAmps',
            'TransitionUpInMilliSeconds', 'TransitionDownInMilliSeconds', 'GangedToHemisphere')
TIMING = ('UpperThresholdOnsetInMilliSeconds', 'LowerThresholdOnsetInMilliSeconds',
          'DetectionBlankingDurationInMilliSeconds', 'AdaptiveStartupDelayInMilliSeconds')
TOKENS = {'ZERO':'0', 'ONE':'1', 'TWO':'2', 'THREE':'3', 'CASE':'C'}


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def leaf(value):
    return value.rsplit('.', 1)[-1] if isinstance(value, str) else value


def _number(value, label):
    value = finite(value)
    if value is None or value < 0:
        raise ValueError('unknown_' + label)
    return value


def _contacts(states, side):
    result = []
    for state in states or []:
        polarity = leaf(state.get('ElectrodeStateResult'))
        if polarity == 'None':
            continue
        if polarity not in ('Negative', 'Positive'):
            raise ValueError('unknown_contact_polarity')
        raw = leaf(state.get('Electrode'))
        if not isinstance(raw, str) or not raw:
            raise ValueError('unknown_contacts')
        token = raw.replace('SenSight_', '').replace('Sensight_', '')
        token = TOKENS.get(token.upper(), token)
        if token != 'C' and re.fullmatch(r'[0-3][abc]?', token) is None:
            raise ValueError('unknown_contacts')
        if side == 'right' and token[:1].isdigit():
            token = str(int(token[0]) + 8) + token[1:]
        result.append({'contact': token, 'polarity': polarity,
                       'fraction': finite(state.get('ElectrodeFractionOf64')),
                       'amplitude': finite(state.get('ElectrodeAmplitudeInMilliAmps'))})
    if not any(c['polarity'] == 'Negative' for c in result) or not any(c['polarity'] == 'Positive' for c in result):
        raise ValueError('unknown_contacts')
    return sorted(result, key=lambda row: (row['contact'], row['polarity']))


def _side_settings(group, side, sensing_only=False):
    ps = group.get('ProgramSettings') or {}
    all_channels = ps.get('SensingChannel', [])
    if any(str(leaf(c.get('HemisphereLocation'))).lower() not in SIDES for c in all_channels):
        raise ValueError('unknown_sensing_hemisphere')
    channels = [c for c in all_channels if str(leaf(c.get('HemisphereLocation'))).lower() == side]
    if len(channels) > 1:
        raise ValueError('ambiguous_side_program')
    if channels:
        channel = channels[0]
        status = leaf(channel.get('AdaptiveTherapyStatus'))
        origin = None
        if sensing_only and status == 'RUNNING':
            raise ValueError('conflicting_mode_evidence')
        if sensing_only and status in (None, 'DISABLED'):
            origin = 'Device report: Sensing Only (JSON adaptive state '+('absent' if status is None else 'DISABLED')+')'
            status = 'NOT_CONFIGURED' if status is None else status
        if status not in ('RUNNING', 'SUSPENDED', 'NOT_CONFIGURED') and not (status == 'DISABLED' and sensing_only):
            raise ValueError('unknown_adaptive_status')
        amp = _number(channel.get('SuspendAmplitudeInMilliAmps'), 'amplitude')
        adaptive = status == 'RUNNING'
        lower = _number(channel.get('LowerLimitInMilliAmps'), 'adaptive_limits') if adaptive else finite(channel.get('LowerLimitInMilliAmps'))
        upper = _number(channel.get('UpperLimitInMilliAmps'), 'adaptive_limits') if adaptive else finite(channel.get('UpperLimitInMilliAmps'))
        if adaptive and lower > upper:
            raise ValueError('invalid_adaptive_limits')
        setup = channel.get('SensingSetup') or {}
        if adaptive and upper > 0:
            if leaf(channel.get('Mode')) not in ('SINGLE_THRESHOLD_DIRECT','DUAL_THRESHOLD_DIRECT'):
                raise ValueError('unknown_adaptive_mode')
            low_threshold = _number(channel.get('LowerLfpThreshold'), 'adaptive_thresholds')
            high_threshold = _number(channel.get('UpperLfpThreshold'), 'adaptive_thresholds')
            if low_threshold > high_threshold:
                raise ValueError('invalid_adaptive_thresholds')
            signal = (setup.get('ChannelSignalResult') or {}).get('Channel')
            if (not isinstance(channel.get('Channel'), str) or not channel['Channel']
                    or not isinstance(signal, str) or not signal or _number(setup.get('FrequencyInHertz'),'sensing_frequency') <= 0):
                raise ValueError('unknown_sensing_identity')
        return {'schema':'sensing', 'adaptive_evidence':origin, 'recorded_inactive_mode':leaf(channel.get('Mode')) if origin else None, 'adaptive_status':status, 'adaptive_running':adaptive,
                'programs':[{'amplitude':amp, 'pulse_width':_number(channel.get('PulseWidthInMicroSecond'), 'pulse_width'),
                             'rate':_number(channel.get('RateInHertz', ps.get('RateInHertz')), 'rate'),
                             'contacts':_contacts(channel.get('ElectrodeState'), side)}],
                'adaptive':{key:channel.get(key) for key in ADAPTIVE} if adaptive else {},
                'sensing':({'status':channel.get('BrainSensingStatus'), 'channel':channel.get('Channel'),
                           'frequency':finite(setup.get('FrequencyInHertz')), 'averaging_ms':finite(setup.get('AveragingDurationInMilliSeconds')),
                           'signal_channel':(setup.get('ChannelSignalResult') or {}).get('Channel')} if adaptive else {}),
                'timing':{key:(channel.get('AdaptiveTherapy') or {}).get(key) for key in TIMING} if adaptive else {},
                'active':upper > 0 if adaptive else amp > 0}
    legacy = ps.get(side.title() + 'Hemisphere') or {}
    programs = []
    for program in legacy.get('Programs', []):
        if 'Enabled' in program and not isinstance(program['Enabled'], bool):
            raise ValueError('unknown_program_enabled')
        if program.get('Enabled') is False:
            continue
        programs.append({'program_id':leaf(program.get('ProgramId')),
                         'patient_lower_limit':finite(program.get('LowerLimitInMilliAmps')),
                         'patient_upper_limit':finite(program.get('UpperLimitInMilliAmps')),
                         'amplitude':_number(program.get('AmplitudeInMilliAmps'), 'amplitude'),
                         'pulse_width':_number(program.get('PulseWidthInMicroSecond'), 'pulse_width'),
                         'rate':_number(program.get('RateInHertz', ps.get('RateInHertz')), 'rate'),
                         'contacts':_contacts(program.get('ElectrodeState'), side)})
    return {'schema':'fixed_program', 'programs':programs, 'adaptive_running':False,
            'active':any(p['amplitude'] > 0 for p in programs)}


def _display(identity):
    rows = [{'label':'Group', 'value':identity['group']}, {'label':'Stimulation mode', 'value':'Closed loop' if identity['mode']=='closed_loop' else 'Open loop'}]
    rows.append({'label':'Amplitude control','value':str(leaf(identity['amplitude_control']))})
    group = identity['group_settings']
    soft = group.get('SoftStartStop') or {}
    group_fields = [('Soft start/stop enabled',soft.get('Enabled')),('Soft start/stop duration sec',soft.get('DurationInSeconds')),
                    ('Sensing high-pass filter Hz',group.get('HighPassFilterInHertz')),
                    ('Sensing blanking duration us',group.get('SensingBlankingDurationInMicroseconds'))]
    rows.extend({'label':name,'value':str(value)} for name,value in group_fields if value is not None)
    cycle = identity['cycling']
    rows.append({'label':'Cycle','value':'On' if cycle['enabled'] else 'Off'})
    if cycle['enabled']:
        rows.extend([{'label':'cycle on sec','value':str(cycle['on_ms']/1000)}, {'label':'cycle off sec','value':str(cycle['off_ms']/1000)}])
    for side in SIDES:
        settings = identity[side]
        for index, program in enumerate(settings['programs']):
            prefix = side.title() + (' program ' + str(index+1) if len(settings['programs']) > 1 else '')
            contacts = ' '.join(c['contact'] + ('-' if c['polarity']=='Negative' else '+') for c in program['contacts'])
            rows.extend({'label':prefix+' '+name, 'value':str(value)} for name,value in
                        (('contacts',contacts), ('rate hz',program['rate']), ('pulse width us',program['pulse_width']), ('amplitude mA',program['amplitude'])))
            for label,key in (('patient adjustment lower limit mA','patient_lower_limit'),('patient adjustment upper limit mA','patient_upper_limit')):
                if program.get(key) is not None:
                    rows.append({'label':prefix+' '+label,'value':str(program[key])})
        if settings['schema'] == 'sensing':
            source = settings['adaptive']; sense = settings['sensing']
            rows.append({'label':side.title()+' adaptive status','value':'Sensing only (device report)' if settings.get('adaptive_evidence') else settings['adaptive_status']})
            if settings.get('adaptive_evidence'):
                rows.append({'label':side.title()+' adaptive evidence','value':settings['adaptive_evidence']})
                if settings.get('recorded_inactive_mode'):
                    rows.append({'label':side.title()+' configured controller mode (inactive)','value':settings['recorded_inactive_mode']})
            fields = [('adaptive mode',leaf(source.get('Mode'))), ('lower limit mA',source.get('LowerLimitInMilliAmps')),
                      ('upper limit mA',source.get('UpperLimitInMilliAmps')), ('lower lfp threshold (LSB)',source.get('LowerLfpThreshold')),
                      ('upper lfp threshold (LSB)',source.get('UpperLfpThreshold')), ('ganged to',leaf(source.get('GangedToHemisphere'))),
                      ('sensing channel',leaf(sense.get('channel'))), ('sensing frequency hz',sense.get('frequency')),
                      ('capture lower amplitude mA',source.get('LowerCaptureAmplitudeInMilliAmps')),
                      ('capture upper amplitude mA',source.get('UpperCaptureAmplitudeInMilliAmps')),
                      ('transition up ms',source.get('TransitionUpInMilliSeconds')),
                      ('transition down ms',source.get('TransitionDownInMilliSeconds')),
                      ('sensing signal channel',leaf(sense.get('signal_channel'))),('sensing averaging ms',sense.get('averaging_ms'))]
            fields.extend((key, value) for key,value in settings['timing'].items())
            rows.extend({'label':side.title()+' '+name, 'value':str(value)} for name,value in fields if value is not None)
    return rows


def _functional(value):
    """Canonical functional identity excludes observational origin and numeric type.

    JSON 10 and 10.0 encode the same setting. Explicit booleans remain distinct;
    source enum prefixes do not change their recorded enum member.
    """
    if isinstance(value, dict):
        return {key:_functional(item) for key,item in value.items() if key not in ('adaptive_evidence','recorded_inactive_mode')}
    if isinstance(value, list):
        return [_functional(item) for item in value]
    if isinstance(value, (int,float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        numeric = finite(value)
        if numeric is not None:
            return numeric
        return leaf(value) if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*Def\.[A-Za-z0-9_]+', value) else value
    return value


def phase_condition(report, phase, sensing_only_sides=()):
    """Only explicit source state; missing adaptive status never becomes open loop."""
    status = leaf((report.get('Stimulation') or {}).get(phase+'StimStatus'))
    if status == 'OFF':
        return {'id':'OFF','label':'No active current','mode':'no_active_current','settings':[], '_signature':'OFF'}, None
    if status != 'ON':
        return None, 'unknown_stimulation_status'
    try:
        active = [g for g in (report.get('Groups') or {}).get(phase, []) if g.get('ActiveGroup') is True]
        if len(active) != 1:
            raise ValueError('unknown_active_group')
        group = active[0]
        left, right = (_side_settings(group, side, side in sensing_only_sides) for side in SIDES)
        if not left['programs'] and not right['programs']:
            raise ValueError('unknown_programs')
        cycling = (group.get('GroupSettings') or {}).get('Cycling') or {}
        enabled = cycling.get('Enabled')
        if not isinstance(enabled, bool):
            raise ValueError('unknown_cycling')
        mode = 'closed_loop' if any(s['active'] and s['adaptive_running'] for s in (left,right)) else 'open_loop'
        if not left['active'] and not right['active']:
            return {'id':'OFF','label':'No active current','mode':'no_active_current','settings':[], '_signature':'OFF'}, None
        if not isinstance(group.get('GroupId'), str) or not group['GroupId']:
            raise ValueError('unknown_group_id')
        identity = {'group':leaf(group.get('GroupId')), 'mode':mode, 'left':left, 'right':right,
                    'amplitude_control':(group.get('ProgramSettings') or {}).get('AmplitudeControl'),
                    'cycling':{'enabled':enabled, 'on_ms':_number(cycling.get('OnDurationInMilliSeconds'),'cycling') if enabled else None,
                               'off_ms':_number(cycling.get('OffDurationInMilliSeconds'),'cycling') if enabled else None},
                    'group_settings':{key:(group.get('GroupSettings') or {}).get(key) for key in ('SoftStartStop','HighPassFilterInHertz','SensingBlankingDurationInMicroseconds')}}
        signature = json.dumps(_functional(identity), sort_keys=True, separators=(',', ':'), allow_nan=False)
        uid = hashlib.sha256(signature.encode()).hexdigest()[:20]
        return {'id':uid, 'label':('CL' if mode=='closed_loop' else 'OL')+' · '+str(identity['group'])+' · '+uid[:6],
                'mode':mode,'settings':_display(identity),'_signature':signature}, None
    except (TypeError, ValueError, AttributeError) as exc:
        return None, str(exc) if str(exc).startswith(('unknown_','invalid_','ambiguous_','conflicting_')) else 'invalid_source_settings'


def _mode_evidence(source, uid, hashed):
    """Only independently reviewed, exact-source-bound PDF statements supplement JSON.

    The optional private context binder supplies explicit Sensing Only evidence;
    missing JSON fields by themselves never establish an open-loop mode.
    """
    result = {'Initial':set(), 'Final':set()}
    raw_hash = source.get('raw_sha256')
    for item in source.get('mode_evidence', []):
        pdf_hash = item.get('pdf_sha256', '')
        valid = (item.get('reviewed') is True and item.get('source_id') == uid
                 and item.get('source_hash') == hashed and isinstance(raw_hash, str)
                 and len(raw_hash) == 64 and item.get('raw_sha256') == raw_hash
                 and isinstance(pdf_hash, str) and len(pdf_hash) == 64
                 and all(c in '0123456789abcdef' for c in raw_hash + pdf_hash)
                 and item.get('phase') in result and item.get('side') in SIDES
                 and item.get('mode') == 'SENSING_ONLY')
        if valid:
            result[item['phase']].add(item['side'])
    return result


def prepare_source(source):
    """Compact per-file facts for the shared store; never retain spectra or patient text."""
    if source.get('prepared') == POLICY_VERSION:
        return deepcopy(source)
    uid = str(source.get('id', source.get('source_id', '')))
    hashed = str(source.get('hash', source.get('source_hash', '')))
    report = source.get('report')
    if not uid or not hashed or not isinstance(report, dict):
        return {'prepared':POLICY_VERSION,'id':uid,'hash':hashed,'start':None,'end':None,'start_valid':False,'end_valid':False,
                'initial':None,'final':None,'initial_error':'unreadable_source','final_error':'unreadable_source'}
    start, end = epoch(report.get('SessionDate')), epoch(report.get('SessionEndDate'))
    valid_pair = start is not None and end is not None and start <= end and end-start < 8*3600
    start_valid = start is not None and (end is None or valid_pair)
    end_valid = end is not None and (start is None or valid_pair)
    evidence = _mode_evidence(source, uid, hashed)
    initial, ie = phase_condition(report, 'Initial', evidence['Initial'])
    final, fe = phase_condition(report, 'Final', evidence['Final'])
    return {'prepared':POLICY_VERSION,'id':uid,'hash':hashed,'start':start,'end':end,'start_valid':start_valid,'end_valid':end_valid,
            'initial':initial,'final':final,'initial_error':ie,'final_error':fe}


def prepare_sources(sources):
    return sorted((prepare_source(source) for source in sources), key=lambda s:(s['id'],s['hash']))


def _candidate(source, when, day):
    start, end = source['start'], source['end']
    sv, ev = source['start_valid'], source['end_valid']
    if day not in {datetime.fromtimestamp(t, PACIFIC).date().isoformat() for t,valid in ((start,sv),(end,ev)) if valid}:
        return None
    if sv and when < start:
        return start-when, 'initial', source['initial'], source['initial_error'], 'future'
    if ev and when > end:
        return when-end, 'final', source['final'], source['final_error'], 'past'
    if sv and ev:
        same = source['initial'] is not None and source['final'] is not None and source['initial']['_signature'] == source['final']['_signature']
        error = source['initial_error'] or source['final_error'] or 'changed_during_session'
        return 0, 'unchanged_initial_final' if same else None, source['final'] if same else None, None if same else error, 'cover'
    return abs(when-(start if sv else end)), None, None, 'missing_required_boundary', 'past' if sv else 'future'


def when_boundary(source, candidate):
    return source['end'] if candidate[1] == 'final' or not source['start_valid'] else source['start']


def _resolve(candidates):
    """Nearest same-day past Final and future Initial must agree when both exist.

    In-session observations also constrain the join. An unknown nearest boundary
    remains a barrier; a more distant known configuration cannot replace it.
    """
    covers = [(source,candidate) for source,candidate in candidates if candidate[4] == 'cover']
    if covers:
        first = max(source['start'] for source,_ in covers)
        last = min(source['end'] for source,_ in covers)
        candidates = [(source,candidate) for source,candidate in candidates
                      if candidate[4] == 'cover' or (candidate[4] == 'past' and when_boundary(source,candidate) >= first)
                      or (candidate[4] == 'future' and when_boundary(source,candidate) <= last)]
    selected = []
    for direction in ('past', 'future', 'cover'):
        subset = [(source, candidate) for source, candidate in candidates if candidate[4] == direction]
        if subset:
            distance = 0 if direction == 'cover' else min(candidate[0] for _,candidate in subset)
            selected.extend((source,candidate) for source,candidate in subset if candidate[0] == distance)
    source_ids = sorted({source['id'] for source,_ in selected})
    invalid = [candidate[3] for _,candidate in selected if candidate[2] is None]
    if invalid:
        priority = ('changed_during_session','missing_required_boundary')
        reason = next((reason for reason in priority if reason in invalid), sorted(invalid)[0])
        return None, source_ids, None, reason
    signatures = {candidate[2]['_signature'] for _,candidate in selected}
    if len(signatures) != 1:
        return None, source_ids, None, 'conflicting_source_boundaries'
    boundary_names = {candidate[1] for _,candidate in selected}
    boundary = next(iter(boundary_names)) if len(boundary_names) == 1 else 'reconciled_initial_final'
    return deepcopy(selected[0][1][2]), source_ids, boundary, None


def _historical(survey, items):
    accepted = [item for item in items if item.get('verified') is True and item.get('record') == survey['id']
                and item.get('time') == survey['time'] and item.get('values') == survey['values']
                and item.get('source_ids') and isinstance(item.get('condition'), dict)]
    signatures = {json.dumps(item['condition'], sort_keys=True) for item in accepted}
    return accepted[0] if len(signatures) == 1 else None


def build_comparisons(surveys, metrics, sources, testing_days, *, calendar_verified,
                      preserved_testing_days=(), historical_assignments=(), period_start=None):
    """Keep native metric values; rank finite n>=5 medians with explicit direction."""
    definitions = []
    for metric in metrics:
        if metric.get('direction') not in ('lower','higher'):
            raise ValueError('Explicit metric direction required')
        definitions.append({key:deepcopy(metric[key]) for key in ('key','label','range','direction')})
    days = set()
    try:
        days = {date.fromisoformat(day).isoformat() for day in [*testing_days,*preserved_testing_days]}
    except (TypeError, ValueError):
        calendar_verified = False
    prepared = prepare_sources(sources)
    source_bounds = [t for source in prepared for t,valid in ((source['start'],source['start_valid']),(source['end'],source['end_valid'])) if valid]
    duplicate_ids = {uid for uid,n in Counter(str(s.get('id',s.get('row_id',''))) for s in surveys).items() if n > 1}
    groups = {m['key']:defaultdict(list) for m in definitions}
    provenance = {m['key']:Counter(total_surveys=len(surveys)) for m in definitions}
    reasons = {m['key']:Counter() for m in definitions}
    conditions, condition_sources, audit = {}, defaultdict(set), []
    source_times, assigned_times = [], []
    metric_times = {m['key']:[] for m in definitions}
    for original in surveys:
        survey = {'id':str(original.get('id',original.get('row_id',''))), 'time':finite(original.get('time')), 'values':original.get('values',{})}
        when = survey['time']; condition = None; source_ids = []; boundary = None
        if when is not None:
            source_times.append(when)
        if calendar_verified is not True:
            reason = 'calendar_unverified'
        elif not survey['id'] or when is None or survey['id'] in duplicate_ids:
            reason = 'duplicate_survey_id' if survey['id'] in duplicate_ids else 'invalid_survey_time'
        elif period_start is not None and when < period_start:
            reason = 'before_period'
        elif datetime.fromtimestamp(when, PACIFIC).date().isoformat() in days:
            reason = 'testing_day'
        else:
            day = datetime.fromtimestamp(when,PACIFIC).date().isoformat()
            candidates = [(source,_candidate(source,when,day)) for source in prepared]
            candidates = [(source,candidate) for source,candidate in candidates if candidate is not None]
            if not candidates:
                prior = _historical(survey,historical_assignments)
                condition = deepcopy(prior['condition']) if prior else None
                source_ids = list(prior['source_ids']) if prior else []
                boundary = 'reviewed_historical' if prior else None
                reason = None if prior else 'no_same_day_source'
            else:
                condition, source_ids, boundary, reason = _resolve(candidates)
        if condition is not None:
            public = {k:v for k,v in condition.items() if not k.startswith('_')}
            if condition['id'] in conditions:
                existing = conditions[condition['id']]['settings']
                public['settings'] = existing + [row for row in public['settings'] if row not in existing]
            conditions[condition['id']] = public
            condition_sources[condition['id']].update(source_ids)
            assigned_times.append(when)
        audit.append({'record':survey['id'],'time':when,'condition_id':condition['id'] if condition else None,
                      'mode':condition['mode'] if condition else None,'reason':reason,'source_ids':source_ids,'boundary':boundary})
        for metric in definitions:
            key = metric['key']; values = provenance[key]; value = finite(survey['values'].get(key))
            if value is not None and when is not None:
                metric_times[key].append(when)
            if value is None:
                values['missing_value'] += 1
            elif reason in ('calendar_unverified','invalid_survey_time','duplicate_survey_id'):
                values['invalid'] += 1; reasons[key][reason] += 1
            elif reason in ('testing_day', 'before_period'):
                values['excluded_testing' if reason == 'testing_day' else 'excluded_period'] += 1; reasons[key][reason] += 1
            else:
                values['eligible'] += 1
                if condition is None:
                    values['unassigned'] += 1; reasons[key][reason] += 1
                else:
                    values['assigned'] += 1
                    values[condition['mode'] if condition['mode'] != 'no_active_current' else 'off'] += 1
                    groups[key][condition['id']].append({'record':survey['id'],'time':when,'value':value})
    output = []
    for metric in definitions:
        entries, baseline = [], None
        for uid,points in groups[metric['key']].items():
            item = {**deepcopy(conditions[uid]), 'count':len(points), 'median':statistics.median(p['value'] for p in points),
                    'points':sorted(points,key=lambda p:(p['time'],p['record'])), 'start':min(p['time'] for p in points), 'end':max(p['time'] for p in points),
                    'source_ids':sorted(condition_sources[uid])}
            if item['mode'] == 'no_active_current':
                baseline = item
            else:
                entries.append(item)
        entries.sort(key=lambda item:((1 if metric['direction']=='lower' else -1)*item['median'],item['id']))
        counts = {key:provenance[metric['key']][key] for key in ('total_surveys','missing_value','invalid','eligible','assigned','unassigned','excluded_testing','excluded_period','open_loop','closed_loop','off')}
        all_points = [point for entry in entries + ([baseline] if baseline else []) for point in entry['points']]
        counts.update(reasons=dict(reasons[metric['key']]), latest_survey=max(metric_times[metric['key']],default=None),latest_assigned=max((p['time'] for p in all_points),default=None))
        output.append({**metric,'conditions':entries,'baseline':baseline,'top':{mode:[item['id'] for item in entries if item['mode']==mode and item['count']>=MIN_SURVEYS][:3] for mode in ('open_loop','closed_loop')},'provenance':counts})
    calendar = {'status':'stored_verified' if calendar_verified is True else 'unavailable','testing_days':sorted(days),
                'first_day':min(days,default=None),'last_day':max(days,default=None),'excluded_scope':'whole_pacific_day'}
    counts = Counter(row['reason'] or 'assigned' for row in audit)
    return {'available':any(m['conditions'] or m['baseline'] for m in output),
            'message':('Automatic descriptive comparisons from stored same-Pacific-day programmer boundaries; no continuous-delivery or upstream-freshness claim.' if calendar_verified is True else 'Verified testing calendar unavailable; all program comparisons are withheld.'),
            'metrics':output,'audit':audit,'provenance':{'policy_version':POLICY_VERSION,'mode':'automatic_stored_sources','calendar_verified':calendar_verified is True,
                'period_start':period_start,'calendar':calendar,'testing_days':sorted(days),'source_min':min(source_bounds,default=None),'source_max':max(source_bounds,default=None),
                'latest_settings_observation':max(source_bounds,default=None),'source_min_survey':min(source_times,default=None),'source_max_survey':max(source_times,default=None),
                'latest_survey':max(source_times,default=None),'latest_assigned':max(assigned_times,default=None),'counts':dict(counts),'sources':len(prepared)}}
