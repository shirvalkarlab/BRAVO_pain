"""Read-only pre-trial timeline over the same reviewed ScaleRecords used by BRAVO.

No raw REDCap access or reprocessing occurs on this read path. Historical forms
remain distinct sources; only the notebook's explicitly equivalent metrics join.
"""
import csv
import copy
import datetime as dt
import hashlib
import math
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from Server import models
from modules.RCS08SurveyProcessing import STANDARD_MPQ, EXTRA_MPQ

VERSION = 'redcap-pretrial-1'
TIMEZONE = 'America/Los_Angeles'
METRICS = [
    ('mood_vas', 'Mood VAS', 100), ('nrs_intensity', 'Overall NRS', 10),
    ('vas_intensity', 'Overall VAS', 100), ('left_leg_vas_intensity', 'Left-leg VAS', 100),
    ('back_vas_intensity', 'Back VAS', 100), ('mpq_standard_0_45', 'Standard MPQ total', 45),
    ('relief_vas', 'Pain relief VAS', 100), ('mpq_sens', 'MPQ sensory', 33),
    ('mpq_aff', 'MPQ affective', 12),
    *[(f'mpq_{name}', name.replace('_', ' ').capitalize(), 3) for name in STANDARD_MPQ],
    *[(name, 'Fiery' if name == 'firey' else name.capitalize(), 3) for name in EXTRA_MPQ],
]
DAILY_MAPPING = dict(zip(
    ('mood', 'nrs', 'vas', 'left_leg_vas', 'back_vas', 'mpq_standard', 'relief', 'mpq_sen', 'mpq_aff'),
    (entry[0] for entry in METRICS[:9])))
DAILY_MAPPING.update({key: key for key, _, _ in METRICS[9:]})
MPQ_MAPPING = {key: key for key, _, _ in METRICS if key.startswith('mpq_')}
FORMS = {
    'RCS08 Daily PRO (REDCap)': ('Daily PRO', DAILY_MAPPING, 'reviewed_sha256'),
    'RCS08 Fluctuation - Pain and mood': ('Pre-/post-trial fluctuation survey',
        {key: key for key in ('mood_vas', 'nrs_intensity', 'vas_intensity')}, 'source_sha256'),
    'RCS08 Fluctuation - MPQ': ('Pre-/post-trial SF-MPQ', MPQ_MAPPING, 'source_sha256'),
    'RCS08 Stage 0 - Mini VAS': ('Stage 0 mini VAS',
        {'pain_vas_mini': 'vas_intensity', 'pain_relief_mini': 'relief_vas'}, 'source_sha256'),
    'RCS08 Stage 0 - Short NRS VAS': ('Stage 0 short NRS/VAS',
        {'pain_nrs_short': 'nrs_intensity', 'pain_vas_short': 'vas_intensity', 'relief_vas_short': 'relief_vas'}, 'source_sha256'),
    'RCS08 Stage 0 - Long NRS VAS MPQ': ('Stage 0 long NRS/VAS/MPQ',
        {'pain_nrs_long': 'nrs_intensity', 'pain_vas_long': 'vas_intensity', **MPQ_MAPPING,
         **{name: name for name in EXTRA_MPQ}}, 'source_sha256'),
}
PHASE_STYLES = [
    ('pre_trial', 'Pre-trial', '#777777'),
    ('stage_0', 'Stage 0 trial', '#E68173'),
    ('post_stage_0_pre_stage_1', 'Post-Stage 0 / pre-Stage 1', '#9A9A9A'),
    ('stage_1', 'Stage 1 biomarker discovery', '#D9A900'),
    ('stage_2', 'Stage 2 active-stim optimization', '#2AAFA8'),
]


class TimelineNotReady(ValueError):
    """Stored managed inputs require a successful normal data sync."""


def stages_path():
    return Path(os.environ.get('RCS08_PROCESSING_RULES', '/run/secrets/rcs08_processing')) / 'rcs08_study_stages.csv'


def phase_table(path=None):
    path = Path(path or stages_path())
    raw = path.read_bytes()
    stages = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
    indexed = {row['stage']: row for row in stages}
    if len(indexed) != len(stages) or not {'stage_0', 'stage_1', 'stage_2'} <= set(indexed):
        raise TimelineNotReady('Study-stage definitions are incomplete or duplicated')
    zone = ZoneInfo(TIMEZONE)

    def boundary(stage, field, inclusive=False):
        value = indexed[stage][field]
        if not value and stage == 'stage_2' and field == 'end_date':
            return None
        day = dt.date.fromisoformat(value)
        if inclusive:
            day += dt.timedelta(days=1)
        return dt.datetime.combine(day, dt.time(), zone).timestamp()

    s0, e0 = boundary('stage_0', 'start_date'), boundary('stage_0', 'end_date', True)
    s1, e1 = boundary('stage_1', 'start_date'), boundary('stage_1', 'end_date', True)
    s2, e2 = boundary('stage_2', 'start_date'), boundary('stage_2', 'end_date', True)
    if not s0 < e0 <= s1 < e1 or e1 != s2 or (e2 is not None and e2 <= s2):
        raise TimelineNotReady('Study-stage boundaries are inconsistent')
    intervals = [(None, s0), (s0, e0), (e0, s1), (s1, e1), (s2, e2)]
    phases = [{'key': key, 'label': label + (' (ongoing)' if key == 'stage_2' and e2 is None else ''),
               'color': color, 'start': start, 'end': end}
              for (key, label, color), (start, end) in zip(PHASE_STYLES, intervals)]
    return phases, hashlib.sha256(raw).hexdigest()


def finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def checked_fields(form, mapping, hash_key):
    if not isinstance(form.record, list) or not form.record or not isinstance(form.record[0], dict):
        raise TimelineNotReady('The managed survey has no field mapping')
    audit = form.record[0].get('processing', {})
    if (not isinstance(audit, dict) or audit.get('timeline_schema') != VERSION
            or not re.fullmatch('[0-9a-f]{64}', str(audit.get(hash_key, '')))):
        raise TimelineNotReady('The managed survey requires an updated reviewed sync')
    fields = [(p, q, question.get('variableName')) for p, page in enumerate(form.record)
              for q, question in enumerate(page['questions']) if question.get('type') == 'score']
    keys = [key for _, _, key in fields]
    if len(set(keys)) != len(keys) or not set(mapping) <= set(keys):
        raise TimelineNotReady('The managed survey is missing required metric fields')
    return [(p, q, mapping[key]) for p, q, key in fields if key in mapping], audit


def stored_phases(form):
    if form is None:
        raise TimelineNotReady('The daily survey stage definitions need a reviewed sync')
    _, audit = checked_fields(form, DAILY_MAPPING, 'reviewed_sha256')
    phases = copy.deepcopy(audit.get('timeline_phases'))
    digest = audit.get('timeline_stage_sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', str(digest)) or not isinstance(phases, list) or len(phases) != 5:
        raise TimelineNotReady('Stored study-stage provenance is incomplete')
    for i, (phase, style) in enumerate(zip(phases, PHASE_STYLES)):
        if (not isinstance(phase, dict) or phase.get('key') != style[0]
                or not isinstance(phase.get('label'), str) or phase.get('color') != style[2]):
            raise TimelineNotReady('Stored study-stage metadata is invalid')
        start, end = phase.get('start'), phase.get('end')
        if ((i > 0 and finite(start) is None) or (i < 4 and finite(end) is None)
                or (start is not None and end is not None and start > end)
                or (i > 0 and start != phases[i-1]['end'])):
            raise TimelineNotReady('Stored study-stage boundaries are invalid')
    return phases, digest


def build_report(participant, *, now=None):
    from modules.RCS08DataPolicy import applies_to
    if not applies_to(participant):
        raise TimelineNotReady('This participant does not have the reviewed pre-trial mapping')
    daily = models.ScaleForms.find(institute=participant.institute, name='RCS08 Daily PRO (REDCap)',
                                   record_type='REDCap API Sync')
    phases, stage_hash = stored_phases(daily)
    now = dt.datetime.now(dt.timezone.utc).timestamp() if now is None else now
    metrics = {key: {'key': key, 'label': label, 'range': [0, upper], 'points': []}
               for key, label, upper in METRICS}
    source_audits = []
    missing_forms = []
    rejected = {'future_records': 0, 'missing_values': 0, 'invalid_values': 0, 'outside_stages': 0}
    for name, (source, mapping, hash_key) in FORMS.items():
        form = models.ScaleForms.find(institute=participant.institute, name=name, record_type='REDCap API Sync')
        if form is None:
            missing_forms.append(source)
            continue
        fields, audit = checked_fields(form, mapping, hash_key)
        count = 0
        for record in models.ScaleRecord.find_all(source=form, participant=participant).order_by('date', 'name'):
            if (not isinstance(record.record, list) or len(record.record) != len(form.record)
                    or any(not isinstance(values, list) or len(values) != len(page['questions'])
                           for values, page in zip(record.record, form.record))):
                raise TimelineNotReady('A managed survey row does not match its field mapping')
            stamp = finite(record.date)
            if stamp is None:
                raise TimelineNotReady('A managed survey timestamp is invalid')
            if stamp > now:
                rejected['future_records'] += 1
                continue
            phase = next((item for item in phases if (item['start'] is None or item['start'] <= stamp)
                          and (item['end'] is None or stamp < item['end'])), None)
            if phase is None:
                rejected['outside_stages'] += 1
                continue
            count += 1
            for p, q, key in fields:
                raw = record.record[p][q]
                value = finite(raw)
                if value is None:
                    rejected['missing_values' if raw is None or raw == '' else 'invalid_values'] += 1
                    continue
                if not 0 <= value <= metrics[key]['range'][1]:
                    rejected['invalid_values'] += 1
                    continue
                metrics[key]['points'].append({'time': stamp, 'value': value, 'source': source,
                                                'record': str(record.name), 'phase': phase['key']})
        source_audits.append({'source': source, 'form_uid': form.uid, 'records': count, 'processing': audit})
    if not source_audits:
        raise TimelineNotReady('No reviewed pre-trial survey data is available')
    for metric in metrics.values():
        metric['points'].sort(key=lambda point: (point['time'], point['source'], point['record']))
    first = min((point['time'] for metric in metrics.values() for point in metric['points']), default=phases[1]['start'])
    phases[0]['start'] = min(first, phases[1]['start'])
    return {'metrics': list(metrics.values()), 'phases': phases, 'provenance': {
        'adapter_version': VERSION, 'timezone': TIMEZONE, 'stage_sha256': stage_hash,
        'sources': source_audits, 'missing_sources': missing_forms, 'omitted': rejected,
        'source': 'Reviewed shared BRAVO ScaleRecords',
        'historical_completion': 'Completed forms only (2)',
        'stage0_mpq_scoring': 'Sum observed items; wholly absent blocks remain missing',
    }}
