"""Source-hashed notebook assignments joined to the existing canonical PRO scores.

Publication occurs during ordinary sync. Reads never load host CSVs, fetch APIs,
re-score surveys or introduce values from a second data stream.
"""
import base64
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import zlib

from modules.RedcapTimeline import METRICS, finite
from modules.RedcapComparisonSources import functional, medications, flag, day_epoch, ZONE

VERSION = 'redcap-comparisons-1'


def code_identity():
    return hashlib.sha256(b''.join(path.read_bytes() for path in
        (Path(__file__), Path(__file__).with_name('RedcapComparisonSources.py')))).hexdigest()


def unavailable(message):
    return {'available': False, 'message': message, 'metrics': [], 'episodes': [], 'provenance': {}}


def record_identity(row):
    repeat = finite(row['repeat_instance'])
    if repeat is None or repeat != int(repeat):
        raise ValueError('Invalid survey repeat identity')
    return ':'.join([str(row['source_event']), str(row['source_instrument']), str(int(repeat))])


def timestamp(value):
    from modules.RCS08Sync import _redcap_timestamp
    return _redcap_timestamp(str(value))[0]


def source_csv(path):
    raw = path.read_bytes()
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed source CSV row')
    return rows, hashlib.sha256(raw).hexdigest()


def canonical_rows(canonical):
    return [row for row in canonical.loc[canonical.include_in_analysis].to_dict('records')
            if row['study_stage'] in ('stage_1', 'stage_2', 'stage_3')]


def finalized_reference(directory=None):
    """Reviewed reference only: never relabel a group or assign a survey by letter.

    The private rule preserves the sheet citation and the exact source program
    used for functional equivalence. It has no effect on rankings or QC.
    """
    root = Path(directory or os.environ.get('RCS08_PROCESSING_RULES', '/run/secrets/rcs08_processing'))
    try:
        raw = (root / 'finalized_open_loop.json').read_bytes()
        rule = json.loads(raw)
        source = rule['source']
        if (rule['version'] != 1 or not isinstance(source, dict)
                or not all(isinstance(source.get(key), str) and source[key].strip()
                           for key in ('title', 'url', 'range', 'verified_at'))
                or not source['url'].startswith('https://docs.google.com/spreadsheets/d/')):
            raise ValueError('Invalid finalized-program provenance')
        program = functional(rule['program'])
        if program['mode'] != 'open_loop' or program['id'] != rule['condition_id']:
            raise ValueError('Finalized program identity does not match reviewed settings')
        return {**program, 'available': True, 'label': 'Finalized OL', 'source': source,
                'rule_sha256': hashlib.sha256(raw).hexdigest()}
    except (OSError, ValueError, KeyError, TypeError):
        return {'available': False, 'message': 'The finalized open-loop reference needs a valid reviewed home-program rule.'}


def home_signature(settings):
    """Compare the full normalized home program, independent of group letters.

    Ignore only labels, transient therapy state and sampled contact currents;
    retain contacts/fractions, limits, sensing, thresholds and all timing fields.
    """
    ignored = {'Group', 'Tablet target', 'Stimulation status', 'Exported contact amplitudes (snapshot)'}
    normalized = {scope: sorted((field['label'], field['value']) for field in fields
                               if field['label'] not in ignored)
                  for scope, fields in settings.items()}
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def current_closed_loop(publication, context, now):
    """Use current reviewed home settings; join only exact source-boundary evidence."""
    empty = {'available': False, 'message': 'Current home closed-loop settings are not established.'}
    homes = [event for event in context.get('home_transitions', []) if event['time'] <= now]
    if not homes or any(gap['start'] <= now and (gap['end'] is None or now < gap['end'])
                        for gap in context.get('home_unknown_intervals', [])):
        return empty
    latest_time = max(event['time'] for event in homes)
    latest = [event for event in homes if event['time'] == latest_time]
    if len({home_signature(event['settings']) for event in latest}) != 1:
        return empty
    home = latest[0]
    settings = home['settings']
    if not any(field['label'] == 'Mode at observation' and field['value'] == 'Closed loop'
               for field in settings['group']):
        return empty
    signature = home_signature(settings)
    snapshots = {}
    for snapshot in context.get('_comparison_snapshots', []):
        snapshots.setdefault((snapshot['source'], snapshot['phase']), set()).add(snapshot['signature'])
    matched = set()
    for assignment in publication.get('assignments', []):
        phase = 'Final' if assignment['boundary'] == 'final' else 'Initial'
        if snapshots.get((assignment['session_source'], phase)) == {signature}:
            matched.add(assignment['condition'])
    conditions = {condition['id']: condition for condition in publication.get('conditions', [])}
    matched = {key for key in matched if conditions[key]['mode'] == 'closed_loop'}
    # Multiple functional identities are not silently pooled into a new cohort.
    identity = next(iter(matched)) if len(matched) == 1 else 'home-' + signature[:20]
    return {'available': True, 'id': identity, 'label': 'Current CL', 'mode': 'closed_loop',
            'home_settings': settings,
            'settings': [{'label': (scope.capitalize() + ' ' if scope != 'group' else '') + field['label'],
                          'value': field['value']} for scope, fields in settings.items() for field in fields],
            'source': {'title': 'Current reviewed home program', 'url': home.get('source_url', ''),
                       'range': home.get('evidence', ''), 'verified_at': dt.datetime.fromtimestamp(home['time'], ZONE).isoformat()},
            'home_signature': signature, 'home_time': home['time'],
            'matching_message': 'Exact source-boundary program match.' if len(matched) == 1 else
                'No unique matched survey program for these current home settings; older configurations are excluded.'}


def stim_publication(rows, canonical):
    lookup = {record_identity(row): row for row in canonical}
    seen, assignments, conditions = set(), [], {}
    counts = {'source_rows': len(rows), 'canonical_rows': len(canonical), 'matched': 0,
              'not_canonical': 0, 'score_or_time_mismatch': 0, 'unknown_stimulation': 0}
    source_times = []
    for row in rows:
        identity = record_identity(row)
        if identity in seen:
            raise ValueError('Duplicate stimulation survey assignment')
        seen.add(identity)
        stamp = timestamp(row['survey_start']); source_times.append(stamp)
        if row.get('participant_id') != 'RCS08' or identity not in lookup:
            counts['not_canonical'] += 1
            continue
        reference = lookup[identity]
        if (not flag(row['include_in_analysis']) or stamp != timestamp(reference['survey_start'])
                or any(key not in row or finite(row[key]) != finite(reference.get(key)) for key, _, _ in METRICS)):
            counts['score_or_time_mismatch'] += 1
            continue
        try:
            condition = functional(row)
        except (ValueError, KeyError):
            counts['unknown_stimulation'] += 1
            continue
        conditions[condition['id']] = condition
        assignments.append({'record': identity, 'time': stamp, 'condition': condition['id'],
                            'boundary': row['stim_json_boundary_used'],
                            'quality': row.get('stim_json_match_quality', ''),
                            'session_source': Path(row.get('stim_json_file', '')).name})
    counts['matched'] = len(assignments)
    counts['unmatched_canonical'] = len(canonical) - len(assignments)
    counts['source_max_survey'] = max(source_times, default=None)
    return {'available': bool(assignments), 'message': 'Same-day reviewed notebook assignments; unmatched surveys remain unassigned.',
            'assignments': assignments, 'conditions': list(conditions.values()), 'provenance': counts,
            'finalized_open_loop': finalized_reference()}


def med_publication(rows, canonical):
    stage1 = [timestamp(row['survey_start']) for row in canonical if row['study_stage'] == 'stage_1']
    if not stage1:
        raise ValueError('Medication matching requires a Stage 1 survey')
    first = day_epoch(dt.datetime.fromtimestamp(min(stage1), ZONE).date().isoformat())
    episodes, missing = medications(rows, first)
    assignments, conditions = [], {}
    for row in canonical:
        stamp = timestamp(row['survey_start'])
        day = day_epoch(dt.datetime.fromtimestamp(stamp, ZONE).date().isoformat())
        active = [episode for episode in episodes if episode['analysis'] and episode['start'] is not None
                  and episode['start'] <= day and (episode['end'] is None and episode['ongoing'] or
                                                   episode['end'] is not None and day < episode['end'])]
        generics = [episode['generic'] for episode in active]
        if len(set(generics)) != len(generics):
            raise ValueError('Medication intervals overlap on a canonical survey date')
        for episode in active:
            key = episode['condition_id']
            conditions[key] = {**episode, 'id': key}
            assignments.append({'record': record_identity(row), 'time': stamp, 'condition': key})
    return {'available': bool(episodes), 'message': 'Documented regimens; PRN availability does not establish ingestion.',
            'assignments': assignments, 'conditions': list(conditions.values()), 'episodes': episodes,
            'provenance': {'canonical_rows': len(canonical), 'matched': len({item['record'] for item in assignments}),
                           'source_rows': len(rows), 'regimens_without_complete_interval': missing,
                           'period_start': first, 'source_max_survey': max((timestamp(row['survey_start']) for row in canonical), default=None)}}


def publish(canonical, reviewed_hash, directory=None, period_start=None):
    root = directory or os.environ.get('RCS08_COMPARISON_SOURCE_DIR')
    result = {'version': VERSION, 'code_sha256': code_identity(), 'reviewed_sha256': reviewed_hash}
    canonical = canonical_rows(canonical)
    for key, relative, builder in (
        ('stimulation', 'stim/rcs08_stage1_to_stage3_pain_stim_matches.csv', stim_publication),
        ('medications', 'medications/rcs08_medications.csv', med_publication)):
        if not root:
            result[key] = unavailable('Notebook comparison sources have not been configured.')
            continue
        try:
            rows, source_hash = source_csv(Path(root) / relative)
            section = builder(rows, canonical)
            section['provenance'].update(source_file=relative, source_sha256=source_hash,
                grouping_version=VERSION, grouping_code_sha256=result['code_sha256'],
                period_label='Stage 1 to present', period_start=period_start or min((day_epoch(dt.datetime.fromtimestamp(timestamp(row['survey_start']), ZONE).date().isoformat()) for row in canonical), default=None))
            result[key] = section
        except (OSError, ValueError, KeyError, TypeError, csv.Error):
            result[key] = unavailable('The optional notebook source is missing or invalid. Routine surveys remain available.')
    return base64.b64encode(zlib.compress(json.dumps(result, allow_nan=False).encode())).decode()


def grouped(metrics, publication, medication=False):
    conditions = {condition['id']: condition for condition in publication.get('conditions', [])}
    lookup = {}
    for assignment in publication.get('assignments', []):
        lookup.setdefault((assignment['record'], assignment['time']), []).append(assignment)
    output = []
    for metric in metrics:
        groups = {}
        for point in metric['points']:
            if point['source'] != 'Daily PRO' or point['phase'] not in ('stage_1', 'stage_2', 'stage_3'):
                continue
            for assignment in lookup.get((point['record'], point['time']), []):
                groups.setdefault(assignment['condition'], []).append({k:point[k] for k in ('time','value','record')})
        entries = []
        baseline = None
        for key, points in groups.items():
            condition = conditions[key]
            entry = {**condition, 'count': len(points), 'median': statistics.median(point['value'] for point in points),
                     'points': points, 'start': min(p['time'] for p in points), 'end': max(p['time'] for p in points)}
            if medication:
                entry['background'] = len({(a['record'],a['time']) for a in publication.get('assignments', []) if a['condition'] == key}) == publication['provenance']['canonical_rows']
            if condition.get('mode') == 'no_active_current':
                baseline = entry
            else:
                entries.append(entry)
        entries.sort(key=lambda item: (item['median'], item['label'], item['id']))
        output.append({'key': metric['key'], 'label': metric['label'], 'range': metric['range'],
                       'conditions': entries, 'baseline': baseline, 'top': {
                           mode: [item['id'] for item in entries if item.get('mode') == mode and item['count'] >= 5][:3]
                           for mode in ('open_loop','closed_loop')}})
    return output


def read(form, metrics, now, context=None):
    raw = form.record[0].get('comparison_context')
    empty = {key: unavailable('Notebook comparisons need a reviewed data sync.') for key in ('stimulation','medications')}
    if raw is None:
        return empty
    try:
        publication = json.loads(zlib.decompress(base64.b64decode(raw, validate=True)))
        if (publication['version'] != VERSION or publication.get('code_sha256') != code_identity()
                or publication['reviewed_sha256'] != form.record[0]['processing']['reviewed_sha256']):
            raise ValueError('Comparison publication is stale')
        result = {}
        for key in ('stimulation','medications'):
            section = publication[key]
            if not isinstance(section, dict):
                raise ValueError('Malformed comparison section')
            result[key] = {**section, 'metrics': grouped(metrics, section, key == 'medications'),
                           'episodes': [episode for episode in section.get('episodes', []) if episode['start'] is None or episode['start'] <= now]}
            result[key].pop('assignments', None); result[key].pop('conditions', None)
        result['stimulation']['current_closed_loop'] = current_closed_loop(publication['stimulation'], context or {}, now)
        return result
    except (ValueError, KeyError, TypeError, zlib.error):
        return {key: unavailable('Comparison publication is damaged or stale; refresh through the normal data sync.') for key in empty}
