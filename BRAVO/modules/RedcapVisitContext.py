"""Publish testing-day context from the SAME canonical QC pass as daily PROs.

These points never become routine ScaleRecords. The timeline display may include
them in its rolling median, without changing routine analysis exclusions. Only
the deliberate testing-day exclusion is relaxed; every other QC exclusion wins.
"""
import base64
import json
import zlib
from modules.RedcapTimeline import METRICS, TimelineNotReady, finite

VERSION = 'redcap-visit-context-1'
REASON = 'intentional stimulation-testing day'


def pack(publication):
    # Keep the form small for BRAVO's existing form-list queries. This is a
    # lossless publication envelope, not a second scoring/preprocessing pass.
    return base64.b64encode(zlib.compress(json.dumps(publication, allow_nan=False).encode())).decode()


def publish(canonical, reviewed_hash):
    from modules.RCS08Sync import _redcap_timestamp
    metrics = {key: [] for key, _, _ in METRICS}
    rows = canonical.loc[canonical.stim_testing_date & ~canonical.include_in_analysis
                         & canonical.exclusion_reason.eq(REASON)]
    for row in rows.to_dict('records'):
        stamp, _ = _redcap_timestamp(str(row['survey_start']))
        identity = ':'.join(str(row.get(key, '')) for key in ('source_event', 'source_instrument', 'repeat_instance'))
        for key, _, upper in METRICS:
            value = finite(row.get(key))
            if value is not None and 0 <= value <= upper:
                metrics[key].append({'time': stamp, 'value': value, 'record': identity,
                                     'source': 'Daily PRO · stimulation-testing day',
                                     'phase': row['study_stage']})
    return {'version': VERSION, 'reviewed_sha256': reviewed_hash, 'metrics': metrics,
            'eligible_surveys': len(rows), 'exclusion_reason': REASON}


def read(form, now):
    publication = form.record[0].get('visit_context')
    if publication is None:
        return {'available': False, 'metrics': {}, 'message': 'Testing-day context needs a reviewed data sync.'}
    if isinstance(publication, str):
        try:
            publication = json.loads(zlib.decompress(base64.b64decode(publication, validate=True)))
        except (ValueError, zlib.error):
            raise TimelineNotReady('Testing-day context publication is damaged') from None
    if (not isinstance(publication, dict) or publication.get('version') != VERSION
            or publication.get('reviewed_sha256') != form.record[0]['processing']['reviewed_sha256']
            or publication.get('exclusion_reason') != REASON
            or not isinstance(publication.get('metrics'), dict)
            or set(publication['metrics']) != {key for key, _, _ in METRICS}):
        raise TimelineNotReady('Testing-day context does not match the reviewed daily publication')
    metrics = {}
    for key, _, upper in METRICS:
        points = publication['metrics'][key]
        if not isinstance(points, list):
            raise TimelineNotReady('Testing-day context observations must be a list')
        for point in points:
            if (not isinstance(point, dict)
                    or not isinstance(point.get('time'), (int, float))
                    or not isinstance(point.get('value'), (int, float))
                    or finite(point['time']) is None or finite(point['value']) is None
                    or not 0 <= point['value'] <= upper):
                raise TimelineNotReady('Testing-day context contains an invalid observation')
        metrics[key] = [point for point in points if point['time'] <= now]
    return {'available': True, 'metrics': metrics, 'reviewed_sha256': publication['reviewed_sha256'],
            'message': 'X markers are QC-valid testing-day surveys, included in the display median; routine analysis exclusions are unchanged.'}
