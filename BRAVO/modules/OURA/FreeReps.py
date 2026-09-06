"""Compact first-party adapter for FreeReps views over BRAVO's QC Oura data.

Daily identities use Oura's day, never UTC-midnight conversion. Sleep daily
metrics use only the longest session per day; naps remain available as details.
No Oura service requests or independent QC policy exist in this adapter.
"""
import hashlib
import math

import numpy as np

from modules.OURA.QualityControl import day_label, sample_times

VERSION = 'oura-freereps-1'


class SleepNotFound(KeyError):
    """The selected session disappeared following a source/QC refresh."""

# key, label, unit, stream, descriptor (None means the genuine daily score), divisor
DAILY = (
    ('readiness', 'Readiness score', 'score', 'DailyReadiness', None, 1),
    ('sleep_score', 'Sleep score', 'score', 'DailySleep', None, 1),
    ('activity', 'Activity score', 'score', 'DailyActivity', None, 1),
    ('steps', 'Steps', 'steps', 'DailyActivity', 'Steps', 1),
    ('active_calories', 'Active calories', 'kcal', 'DailyActivity', 'ActiveCalories', 1),
    ('total_calories', 'Total calories', 'kcal', 'DailyActivity', 'TotalCalories', 1),
    ('activity_high', 'High activity', 'min', 'DailyActivity', 'HighActivityTime', 60),
    ('activity_medium', 'Medium activity', 'min', 'DailyActivity', 'MediumActivityTime', 60),
    ('activity_low', 'Low activity', 'min', 'DailyActivity', 'LowActivityTime', 60),
    ('sedentary', 'Sedentary time', 'h', 'DailyActivity', 'SedentaryActivityTime', 3600),
    ('temperature', 'Temperature deviation', '°C', 'DailyReadiness', 'TemperatureDeviation', 1),
    ('spo2', 'Blood oxygen saturation', '%', 'DailySpo2', 'Spo2', 1),
    ('breathing_disturbance', 'Breathing disturbance index', 'index', 'DailySpo2', 'BreathingDisturbance', 1),
    ('stress', 'High stress time', 'min', 'DailyStress', 'StressHigh', 60),
    ('recovery', 'High recovery time', 'min', 'DailyStress', 'RecoveryHigh', 60),
    ('vascular_age', 'Cardiovascular age', 'years', 'DailyCardiovascularAge', 'VascularAge', 1),
)
SLEEP_METRICS = (
    ('sleep_duration', 'Main sleep duration', 'h', 'duration_hours'),
    ('sleep_efficiency', 'Main sleep efficiency', '%', 'efficiency'),
    ('sleep_hr', 'Main sleep heart rate (eligible samples)', 'bpm', 'hr'),
    ('sleep_hrv', 'Main sleep HRV (eligible samples)', 'ms', 'hrv'),
)


def finite(value):
    if isinstance(value, (bool, str)) or value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def summary_allowed(row):
    return bool(day_label(row) and row.get('Metadata', {}).get('QualityControl', {}).get('summary_included', True))


def samples(row):
    """Honor missing cells even for participants without the RCS08 policy."""
    times = sample_times(row)
    values = np.asarray(row['Data'], dtype=float).copy()
    names = row.get('ChannelNames', [])
    if not len(times):
        return times, np.empty((0, len(names))), names
    missing = np.asarray(row.get('Missing', np.zeros_like(values)), dtype=bool)
    if values.shape != (len(times), len(names)) or missing.shape != values.shape:
        raise ValueError('Oura sample/channel/mask shapes do not match')
    values[missing | ~np.isfinite(values)] = np.nan
    valid = np.isfinite(times)
    order = np.argsort(times[valid], kind='stable')
    return times[valid][order], values[valid][order], names


def channel(times, values, names, name):
    if name not in names:
        return []
    column = values[:, names.index(name)]
    # Nulls preserve gaps in line charts; missing values never enter statistics.
    return [{'time': float(t), 'value': finite(v) if v >= (1 if name == 'Heart Rate' else 0) else None}
            for t, v in zip(times, column)]


def mean_observed(series):
    values = [point['value'] for point in series if point['value'] is not None]
    return sum(values) / len(values) if values else None


def sleep_record(row, detail=False):
    day = day_label(row)
    if not day:
        return None
    times, values, names = samples(row)
    descriptor = row.get('Descriptor', {}) if summary_allowed(row) else {}
    start = finite(descriptor.get('BedtimeStart'))
    end = finite(descriptor.get('BedtimeEnd'))
    rate = finite(row.get('SamplingRate'))
    interval = 1 / rate if rate and rate > 0 else 0
    if start is None and len(times):
        start = float(times[0])
    if end is None and len(times):
        end = float(times[-1] + interval)
    if start is None or end is None or end <= start:
        return None
    hr = channel(times, values, names, 'Heart Rate')
    hrv = channel(times, values, names, 'Heart Rate Variability')
    duration = finite(descriptor.get('TotalSleepDuration'))
    result = {'id': hashlib.sha256(f'{day}:{start}:{end}'.encode()).hexdigest()[:24],
              'day': day, 'start': start, 'end': end,
              'duration_hours': duration / 3600 if duration is not None and duration >= 0 else None,
              'efficiency': finite(descriptor.get('Efficiency')),
              'hr': mean_observed(hr), 'hrv': mean_observed(hrv),
              'summary_included': summary_allowed(row)}
    if detail:
        stages = []
        if 'Sleep Phase' in names:
            for index, value in enumerate(values[:, names.index('Sleep Phase')]):
                stage = {1: 'Deep', 2: 'Light', 3: 'REM', 4: 'Awake'}.get(value)
                stop = min(float(times[index] + interval), end)
                begin = max(float(times[index]), start)
                if not stage or stop <= begin:
                    continue
                if stages and stages[-1]['stage'] == stage and stages[-1]['end'] == begin:
                    stages[-1]['end'] = stop
                else:
                    stages.append({'start': begin, 'end': stop, 'stage': stage})
        result.update(stages=stages, heart_rate=hr, hrv_series=hrv)
    return result


def build_report(data, sleep_id=None):
    """Input MUST be the standard, already QC-filtered loadOuraRingData result."""
    sleep_rows = []
    for row in data.get('Sleep', []):
        record = sleep_record(row)
        if record:
            sleep_rows.append((record, row))
    # Duplicate records can arise from overlapping source fetch windows.
    sessions = {record['id']: (record, row) for record, row in sleep_rows}
    sleeps = sorted((pair[0] for pair in sessions.values()), key=lambda item: (item['day'], item['start']))
    main = {}
    for record in sleeps:
        if record['summary_included']:
            previous = main.get(record['day'])
            if previous is None or record['end'] - record['start'] > previous['end'] - previous['start']:
                main[record['day']] = record
    versions = sorted({row.get('Metadata', {}).get('QualityControl', {}).get('version', 'standard-source-missing-mask')
                       for records in data.values() for row in records})
    provenance = {'adapter_version': VERSION, 'timezone': 'America/Los_Angeles', 'qc_versions': versions,
                  'records_loaded': sum(len(records) for records in data.values()), 'sleep_sessions': len(sleeps),
                  'main_sleep_days': len(main), 'sleep_aggregation': 'Longest session per Oura day; naps are not added',
                  'sample_statistics': 'Mean of QC-eligible sleep samples; missing values excluded',
                  'source': 'BRAVO standard QC-filtered Oura store'}
    if sleep_id is not None:
        if sleep_id not in sessions:
            raise SleepNotFound('Sleep session no longer available')
        return {'sleep': sleep_record(sessions[sleep_id][1], detail=True), 'provenance': provenance}
    metrics = []
    for key, label, unit, kind, descriptor, divisor in DAILY:
        points = {}
        for row in data.get(kind, []):
            if not summary_allowed(row):
                continue
            value = finite(row.get('Descriptor', {}).get(descriptor) if descriptor else row.get('Metadata', {}).get('Score'))
            if value is not None and (descriptor is not None or 0 <= value <= 100):
                points[day_label(row)] = value / divisor
        if points:
            metrics.append({'key': key, 'label': label, 'unit': unit,
                            'points': [{'day': day, 'value': points[day]} for day in sorted(points)]})
    for key, label, unit, field in SLEEP_METRICS:
        points = [{'day': day, 'value': record[field]} for day, record in sorted(main.items()) if record[field] is not None]
        if points:
            metrics.append({'key': key, 'label': label, 'unit': unit, 'points': points})
    return {'metrics': metrics, 'sleep': sleeps, 'provenance': provenance}
