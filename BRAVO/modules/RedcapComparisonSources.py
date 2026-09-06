"""Notebook-equivalent grouping of reviewed stimulation and medication inputs.

Adapted from percept_analysis plots.add_functional_stim_settings and updater
merge_medications. Unknown source assignments fail closed instead of becoming OFF.
"""
import datetime as dt
import hashlib
import json
from zoneinfo import ZoneInfo

from modules.RedcapTimeline import finite

ZONE = ZoneInfo('America/Los_Angeles')
MEDICATION_DRUG_CLASS_GROUPS = {
    "anticonvulsant": "Anticonvulsants / neuropathic agents",
    "gabapentinoid": "Anticonvulsants / neuropathic agents",
    "dissociative_anesthetic": "NMDA antagonist / dissociative anesthetic",
    "opioid_analgesic": "Opioid analgesics",
    "opioid_combination_analgesic": "Opioid analgesics",
    "opioid_antagonist": "Opioid antagonist",
    "ndri": "Antidepressants",
    "ssri": "Antidepressants",
    "tca": "Antidepressants",
    "mood_stabilizer": "Mood stabilizer",
    "benzodiazepine": "Benzodiazepine",
    "glucocorticoid": "Glucocorticoid anti-inflammatory",
    "osmotic_laxative": "Gastrointestinal supportive agents",
    "stimulant_laxative": "Gastrointestinal supportive agents",
    "stool_softener": "Gastrointestinal supportive agents",
}


MEDICATION_DRUG_CLASS_ORDER = [
    "Anticonvulsants / neuropathic agents",
    "NMDA antagonist / dissociative anesthetic",
    "Opioid analgesics",
    "Opioid antagonist",
    "Antidepressants",
    "Mood stabilizer",
    "Benzodiazepine",
    "Glucocorticoid anti-inflammatory",
    "Gastrointestinal supportive agents",
]

SIDE_FIELDS = ('contacts', 'contact_amplitudes_mA', 'contact_fractions_of_64', 'program_amplitudes_mA',
               'amplitude_mA', 'pulse_width_us', 'rate_hz', 'lower_limit_mA', 'upper_limit_mA')
ADAPTIVE_FIELDS = ('sensing_status', 'sensing_channel', 'sensing_frequency_hz', 'adaptive_status', 'adaptive_mode',
                   'lower_lfp_threshold', 'upper_lfp_threshold', 'lower_capture_amplitude_mA',
                   'upper_capture_amplitude_mA', 'transition_up_ms', 'transition_down_ms',
                   'threshold_onset_lower_ms', 'threshold_onset_upper_ms', 'detection_blanking_ms',
                   'adaptive_startup_delay_ms', 'averaging_duration_ms', 'ganged_to')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def flag(value, *, blank=False):
    if value is None or value == '':
        return blank
    text = str(value).strip().lower()
    if text not in ('true', 'false', '1', '0'):
        raise ValueError('Invalid Boolean source field')
    return text in ('true', '1')


def atom(value):
    if value is None or str(value).strip() == '':
        return 'NA'
    if isinstance(value, bool):
        return '1' if value else '0'
    number = finite(value)
    return f'{number:.8g}' if number is not None else ' '.join(str(value).split())


def functional(row):
    """Delivered equivalence ignores display group names and inactive sides."""
    if (not flag(row['stim_match_resolved']) or not flag(row['stim_json_match_same_day'])
            or row['stim_json_boundary_used'] not in ('initial', 'final', 'unchanged_initial_final')):
        raise ValueError('Unresolved or non-same-day stimulation assignment')
    status = str(row['stim_status']).upper()
    if status not in ('ON', 'OFF'):
        raise ValueError('Unknown stimulation status')
    active, running = {}, {}
    for side in ('left', 'right'):
        running[side] = str(row.get(f'stim_{side}_adaptive_status', '')).upper() == 'RUNNING'
        amplitudes = [finite(row.get(f'stim_{side}_{field}')) for field in
                      ('amplitude_mA', 'runtime_average_amplitude_mA', 'electrode_amplitude_max_mA')]
        amplitude = next((v for v in amplitudes if v is not None), None)
        ceiling = max([finite(row.get(f'stim_{side}_{field}')) or 0 for field in
                       ('upper_limit_mA', 'upper_capture_amplitude_mA')])
        if status == 'ON' and amplitude is None and not (running[side] and ceiling > 0):
            if row.get(f'stim_{side}_programmed') in (False, 'False', 'false', '0', 0):
                amplitude = 0
            else:
                raise ValueError('Unknown delivered current')
        timing = [finite(row.get(f'stim_{side}_{field}')) for field in ('pulse_width_us', 'rate_hz')]
        active[side] = status == 'ON' and ((amplitude or 0) > 0 or (running[side] and ceiling > 0)) and all(v is None or v > 0 for v in timing)
    mode = 'no_active_current' if not any(active.values()) else 'closed_loop' if any(running.values()) else 'open_loop'
    laterality = 'bilateral' if all(active.values()) else 'left' if active['left'] else 'right' if active['right'] else 'none'
    if mode == 'no_active_current':
        return {'id': 'OFF', 'label': 'No active current', 'mode': mode, 'settings': []}
    pieces = [mode, laterality, 'amplitude_control=' + atom(row.get('stim_amplitude_control'))]
    settings = [
        {'label': 'Stimulation mode', 'value': {'closed_loop':'Closed loop', 'open_loop':'Open loop'}[mode]},
        {'label': 'Active stimulation sides', 'value': laterality.capitalize()},
        {'label': 'Amplitude control', 'value': atom(row.get('stim_amplitude_control'))},
    ]
    for side in ('left', 'right'):
        if not active[side]:
            pieces.append(f'{side}=inactive')
            continue
        for field in SIDE_FIELDS:
            value = atom(row.get(f'stim_{side}_{field}'))
            pieces.append(f'{side}.{field}={value}')
            settings.append({'label': side.capitalize() + ' ' + field.replace('_', ' '), 'value': value})
    for prefix, fields in (('cycle', ('on_sec', 'off_sec')), ('soft_start_stop', ('sec',))):
        enabled = flag(row.get(f'stim_{prefix}_enabled'))
        pieces.append(f'{prefix}_enabled={int(enabled)}')
        settings.append({'label': prefix.replace('_', ' ').capitalize(), 'value': 'On' if enabled else 'Off'})
        if enabled:
            for field in fields:
                key = f'{prefix}_{field}'; value = atom(row.get('stim_' + key))
                pieces.append(f'{key}={value}'); settings.append({'label': key.replace('_', ' '), 'value': value})
    if mode == 'closed_loop':
        for key, label in (('stim_high_pass_filter_hz', 'High-pass filter (Hz)'),
                           ('stim_sensing_blanking_duration_us', 'Sensing blanking duration (µs)')):
            value = atom(row.get(key))
            pieces.append(f'{key}={value}')
            settings.append({'label': label, 'value': value})
        for side in ('left', 'right'):
            for field in ADAPTIVE_FIELDS:
                value = atom(row.get(f'stim_{side}_{field}'))
                pieces.append(f'{side}.{field}={value}')
                settings.append({'label': side.capitalize() + ' ' + field.replace('_', ' ') + (' (LSB)' if 'lfp_threshold' in field else ''), 'value': value})
    identity = digest(pieces)[:20]
    prefix = ('CL' if mode == 'closed_loop' else 'OL') + '-' + laterality[0].upper()
    return {'id': identity, 'label': prefix + ' · ' + identity[:6], 'mode': mode, 'settings': settings}


def day_epoch(value):
    return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), ZONE).timestamp()


def medications(rows, first_stage1):
    """Half-open date intervals; absent start requires pre_trial, absent end ongoing."""
    episodes, unavailable = [], 0
    for row in rows:
        flags = {key: flag(row[key]) for key in ('analysis', 'pre_trial', 'ongoing', 'prn')}
        generic = row['generic_name'].strip()
        if not generic:
            raise ValueError('Medication generic name is missing')
        start = day_epoch(row['start_date']) if row['start_date'] else first_stage1 if flags['pre_trial'] else None
        end = day_epoch(row['end_date']) if row['end_date'] else None
        if start is None or (end is None and not flags['ongoing']):
            unavailable += 1
        if end is not None and start is not None and end <= start:
            raise ValueError('Medication interval ends before it starts')
        route = row['route'].strip().lower() or 'oral'
        timing = row['timing'].strip().lower()
        timing = {'am':'08:00','morning':'08:00','afternoon':'16:00','pm':'19:00','evening':'19:00',
                  'morning_evening':'08:00;19:00','morning_afternoon_evening':'08:00;16:00;19:00'}.get(timing, timing)
        status = 'prn_available' if flags['prn'] else 'scheduled'
        label = ' | '.join([generic, row['dose'].strip(), row['frequency'].strip(), route])
        if flags['prn']:
            label += ' | PRN available'
        # Timing is retained in condition identity because the notebook summary includes it.
        identity = digest([label, timing])[:20]
        drug_class = MEDICATION_DRUG_CLASS_GROUPS.get(row.get('pharmacologic_class'), row.get('pharmacologic_class') or 'Unspecified')
        episodes.append({'id': digest(row)[:20], 'condition_id': identity, 'label': label, 'name': generic,
                         'generic': generic, 'drug_class': drug_class, 'drug_class_order': MEDICATION_DRUG_CLASS_ORDER.index(drug_class) if drug_class in MEDICATION_DRUG_CLASS_ORDER else len(MEDICATION_DRUG_CLASS_ORDER),
                         'analysis': flags['analysis'], 'primary': flags['analysis'], 'supportive': not flags['analysis'],
                         'start': start, 'end': end, 'ongoing': end is None and flags['ongoing'],
                         'pre_trial': not row['start_date'] and flags['pre_trial'], 'prn': flags['prn'],
                         'status': status, 'dose': row['dose'], 'frequency': row['frequency'], 'route': route,
                         'timing': timing, 'note': row.get('note', '')})
    return episodes, unavailable
