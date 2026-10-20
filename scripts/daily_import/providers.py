"""Optional target-only provider stages, called under the host data lock.

Reuse canonical REDCap processing and native survey/Oura persistence. Configuration
and device setup are separate actions; missing configuration never enables a fetch.
"""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import uuid

try:
    from . import state
except ImportError:
    import state


def records_key(records):
    """Exact date and JSON values; never use the native rounded-date shortcut."""
    return sorted((float(r['Date']), json.dumps(r['Result'], sort_keys=True, allow_nan=False)) for r in records)


def form_snapshot(models, person, form):
    return records_key([{'Date': r.date, 'Result': r.record}
        for r in models.ScaleRecord.objects.filter(source=form, participant=person)])


def persist_redcap(person, frame, mapping, models, service, parser, transaction):
    from pandas.api.types import is_datetime64_any_dtype
    metrics = [key for key in mapping['metric_labels'] if key in frame.columns]
    if not metrics or frame.empty or '_pro_time_utc' not in frame or not is_datetime64_any_dtype(frame['_pro_time_utc']):
        raise ValueError('Canonical REDCap data or UTC timestamps unavailable')
    for metric in metrics:
        if metric.startswith('_') or metric in ('date_time_s1_daily', 'timestamp', 'date'):
            raise ValueError('Time/helper columns cannot be survey metrics')
        if any(math.isinf(float(value)) for value in frame[metric].dropna()):
            raise ValueError('Nonfinite REDCap metric')
    name = 'Daily REDCap ' + person.uid
    options = {'instrument_name': name, 'layout': 'wide', 'timestamp_col': '_pro_time_utc', 'metric_cols': metrics}
    parsed, = parser.parse_export(frame, **options)
    expected = records_key(parsed['records'])
    if not expected:
        raise ValueError('Empty canonical export cannot replace stored surveys')
    with transaction.atomic():
        models.Participant.objects.select_for_update().get(uid=person.uid, institute_id=person.institute_id)
        form = models.ScaleForms.find(institute=person.institute, name=name, record_type=parser.RECORD_TYPE)
        if form is not None and form.record != parsed['FieldMapping']:
            raise ValueError('Survey field schema changed; retain existing form for review')
        unchanged = form is not None and form_snapshot(models, person, form) == expected
        results = service.import_export(person, person.institute, frame, replace=True,
                                        skip_if_unchanged=unchanged, **options)
        if len(results) != 1:
            raise ValueError('Unexpected native form import result')
        form = models.ScaleForms.objects.get(uid=results[0]['FormId'], institute=person.institute)
        if form.record != parsed['FieldMapping'] or form_snapshot(models, person, form) != expected:
            raise ValueError('Native survey exact readback failed')
        if not models.ParticipantLinkRel.include(participant=person, record=form):
            raise ValueError('Native survey participant link missing')
        repeated = service.import_export(person, person.institute, frame, replace=True,
                                         skip_if_unchanged=True, **options)
        if len(repeated) != 1 or repeated[0].get('Unchanged') is not True or repeated[0]['FormId'] != form.uid or form_snapshot(models, person, form) != expected:
            raise ValueError('Native survey repeated import changed records')
    return {'records': len(expected), 'metrics': len(metrics), 'skipped_timestamps': parsed['skipped'], 'unchanged': unchanged}


def redcap(person):
    from django.db import transaction
    from pandas.testing import assert_frame_equal
    from Server import models
    from modules.Biomarkers import bravo_service as bravo
    from modules.SurveyForms import RedcapImport, RedcapImportService
    if os.environ.get('BRAVO_REDCAP_PASS_DIR'):
        raise ValueError('Daily provider stage requires a fresh provider fetch')
    mapping = bravo._load_pt_config(person, {})
    if not mapping or str(mapping.get('pt')) != person.name:
        raise ValueError('REDCap participant mapping mismatch')
    # A new process/request scope, with pass-file reuse refused above, fetches fresh reports.
    with bravo.pro_request_scope():
        frame = bravo._load_pros({'ParticipantId': person.uid}, person)
    if frame is None or frame.empty:
        raise ValueError('No fresh REDCap reports; previous records retained')
    signature = (bravo._REDCAP_SNAPSHOT_KIND, bravo._REDCAP_SNAPSHOT_RULE_VERSION, person.uid, bravo._pro_table_digest(frame))
    key = bravo._cache_store.product_key(bravo._REDCAP_SNAPSHOT_KIND, person.uid, signature)
    if frame.attrs.get(bravo.PRO_STORE_KEY_ATTR) != key:
        raise ValueError('Fresh REDCap provenance snapshot unavailable')
    saved = bravo._cache_store.load(bravo._REDCAP_SNAPSHOT_KIND, person.uid, signature, root=bravo._SHARED_CACHE_DIR_OVERRIDE)
    if saved is None:
        raise ValueError('Fresh REDCap provenance snapshot missing')
    assert_frame_equal(frame, saved, check_exact=True, rtol=0, atol=0)
    return persist_redcap(person, frame, mapping, models, RedcapImportService, RedcapImport, transaction)


def oura(person):
    from Server import models
    from modules.OURA import DataManager
    devices = list(models.OuraRingDevice.objects.filter(owner=person))
    if len(devices) != 1 or devices[0].auth.get('managed_token_file') is not True:
        raise ValueError('A single explicitly configured managed Oura device is required')
    result = DataManager.refreshOuraRingData(devices[0])
    # Native managed refresh validates account identity and authenticates saved readback.
    counts = result['counts']
    if not isinstance(counts, dict) or any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError('Invalid native Oura completion receipt')
    return {'counts': counts, 'unchanged': result['unchanged']}


def run_stages(config, person, functions):
    """Failures are isolated, durably recorded, and still fail the overall daily job."""
    from target_adapter import verify_receipt_directory
    settings = config['providers']
    verify_receipt_directory(settings['receipts'])
    if any(type(settings.get(name + '_enabled', False)) is not bool for name in ('redcap', 'oura')):
        raise ValueError('Provider enable flags must be explicit booleans')
    result = {'failed': False}
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex
    for name in ('redcap', 'oura'):
        enabled = settings.get(name + '_enabled', False)
        if not enabled:
            result[name] = {'status': 'disabled'}
            continue
        try:
            detail = {'status': 'success', **functions[name](person)}
        except Exception:
            # Never emit provider exception strings, account IDs, or observations.
            detail = {'status': 'failed'}
            result['failed'] = True
        receipt = {'format': 1, 'provider': name, 'runtime_revision': config['runtime_revision'],
                   'target_participant_uid': person.uid, 'run_id': run_id, **detail}
        state.atomic_json(Path(settings['receipts']) / (run_id + '-' + name + '-' + detail['status'] + '.json'), receipt)
        result[name] = detail
    return result


def refresh_target(config):
    import django
    django.setup()
    from django.conf import settings
    from Server import models
    db = settings.DATABASES['default']
    if (db['NAME'], db['USER']) != (config['database_name'], config['database_user']) or os.environ['BRAVO_BUILD_REVISION'] != config['runtime_revision']:
        raise ValueError('Provider target runtime mismatch')
    person = models.Participant.objects.get(uid=config['target_participant_uid'], institute_id=config['target_institute_uid'], name=config['participant_name'])
    if person.uid == config['source_participant_uid']:
        raise ValueError('Provider target must be the separate fresh installation')
    return run_stages(config, person, {'redcap': redcap, 'oura': oura})
