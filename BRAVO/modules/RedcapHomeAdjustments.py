"""Apply explicitly reviewed clinical notes without rewriting device exports."""
import copy
import datetime as dt
import hashlib
import json
import re
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('America/Los_Angeles')
UNITS = {'Lower LFP threshold': 'LFP Power (LSB)', 'Upper LFP threshold': 'LFP Power (LSB)',
         'Amplitude': 'mA', 'Fixed / paused amplitude': 'mA'}


def value(settings, side, label):
    return next((row['value'] for row in settings[side] if row['label'] == label), None)


def update(settings, side, field, replacement):
    for scope in ('left', 'right'):
        controlled = field.endswith('LFP threshold') and value(settings, scope, 'Sensing source hemisphere') == side.capitalize()
        if scope == side or controlled:
            for row in settings[scope]:
                if row['label'] == field:
                    row['value'] = replacement


def apply(context, adjustments, now):
    result = copy.deepcopy(context)
    events = result['home_transitions']
    if not isinstance(adjustments, list):
        raise ValueError('Reviewed home adjustments must be a list')
    accepted, unresolved, reviewed = [], [], []
    for item in adjustments:
        try:
            for key in ('date', 'time_local', 'group', 'side', 'field', 'previous_value', 'value', 'source_url', 'note'):
                if not isinstance(item[key], str):
                    raise ValueError('Expected reviewed text fields')
            if not item['note'].strip() or not re.fullmatch(r'Group [A-D]', item['group']):
                raise ValueError('Missing reviewed note or invalid group')
            day = dt.date.fromisoformat(item['date'])
            clock = dt.time.fromisoformat(item['time_local']) if item['time_local'] else dt.time()
            if clock.tzinfo is not None:
                raise ValueError('Expected Pacific wall time')
            stamp = dt.datetime.combine(day, clock, ZONE).timestamp()
            field, side = item['field'], item['side']
            unit = UNITS[field]
            if side not in ('left', 'right') or not item['source_url'].startswith('https://'):
                raise ValueError('Invalid side or missing source')
            for key in ('previous_value', 'value'):
                if not re.fullmatch(r'\d+(?:\.\d+)? ' + re.escape(unit), item[key]):
                    raise ValueError('Invalid reviewed value or units')
        except (KeyError, ValueError, TypeError):
            unresolved.append({'reason': 'Malformed reviewed home adjustment'})
            continue
        reviewed.append((stamp, item))
    events.sort(key=lambda entry: (entry['time'], entry['id']))
    for stamp, item in sorted(reviewed, key=lambda entry: entry[0]):
        side, field = item['side'], item['field']
        if stamp > now:
            continue
        if any(gap['start'] <= stamp and (gap['end'] is None or stamp < gap['end'])
               for gap in result.get('home_unknown_intervals', [])):
            unresolved.append({'date': item['date'], 'reason': 'Preceding home program is unknown at the reviewed adjustment'})
            continue
        previous = next((event for event in reversed(events) if event['time'] < stamp), None)
        if (previous is None or value(previous['settings'], 'group', 'Group') != item['group']
                or value(previous['settings'], side, field) != item['previous_value']):
            unresolved.append({'date': item['date'], 'reason': 'Reviewed adjustment does not match the preceding home program'})
            continue
        event = copy.deepcopy(previous)
        update(event['settings'], side, field, item['value'])
        event.update(time=stamp, time_precision='second' if item['time_local'] else 'day',
                     kind='reviewed_home_adjustment', phase='Reviewed clinical note',
                     source_url=item['source_url'],
                     id=hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()[:20],
                     evidence=('Reviewed home-program adjustment. ' + item['note'] +
                               (' Exact time not recorded.' if not item['time_local'] else ' Time reported in Pacific time.')))
        event['home_timing'] = {'selection': 'reviewed_clinical_note', 'activation_time_known': bool(item['time_local'])}
        # A later export repeating the pre-adjustment value is a source conflict,
        # not evidence to silently erase a documented change. Keep both visible.
        for later in events:
            if later['time'] < stamp:
                continue
            if value(later['settings'], 'group', 'Group') != item['group']:
                break
            found = value(later['settings'], side, field)
            if found != item['previous_value']:
                break
            update(later['settings'], side, field, f"{item['value']} (reviewed note); export: {found}")
            later['evidence'] += ' Source conflict: export repeats the pre-adjustment value; see reviewed clinical note.'
            unresolved.append({'date': item['date'], 'reason': 'Later export conflicts with reviewed home adjustment', 'source_url': item['source_url']})
        events.append(event)
        events.sort(key=lambda entry: (entry['time'], entry['id']))
        accepted.append({'date': item['date'], 'source_url': item['source_url'], 'time_precision': event['time_precision']})
    result['home_provenance']['selected_count'] = len(events)
    result['home_provenance']['reviewed_adjustments'] = accepted
    result['home_provenance']['unresolved_adjustments'] = unresolved
    return result
