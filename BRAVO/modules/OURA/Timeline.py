"""First-party daily Oura timeline over the standard QC-filtered BRAVO store.

This module is independent of the FreeReps adapter. It never fetches, saves or
changes source data. Daily identities are Oura days, not converted UTC dates.
"""
import datetime as dt
import math
from numbers import Real

import numpy as np

from modules.OURA.QualityControl import PACIFIC, day_label, sample_times

VERSION = 'oura-timeline-4'
DEFAULT_METRICS = ('steps', 'heart_rate', 'hrv', 'total_calories', 'sleep_duration', 'sleep_total')
# key, label, unit, group, stream, source descriptor (None = genuine score), divisor
CATALOG = (
    ('heart_rate', 'Heart rate', 'bpm', 'Physiology', '@sample', 'Heart Rate', 1),
    ('hrv', 'Heart-rate variability', 'ms', 'Physiology', '@sample', 'Heart Rate Variability', 1),
    ('sleep_total', 'Total sleep duration, including naps', 'h', 'Sleep', 'SleepTotal', 'TotalSleepDuration', 3600),
    ('sleep_duration', 'Sleep duration (longest episode)', 'h', 'Sleep', 'Sleep', 'TotalSleepDuration', 3600),
    ('sleep_efficiency', 'Main sleep efficiency', '%', 'Sleep', 'Sleep', 'Efficiency', 1),
    ('sleep_hr', 'Main sleep heart rate (eligible samples)', 'bpm', 'Sleep', 'Sleep', '@Heart Rate', 1),
    ('sleep_hrv', 'Main sleep HRV (eligible samples)', 'ms', 'Sleep', 'Sleep', '@Heart Rate Variability', 1),
    ('steps', 'Steps', 'steps', 'Activity', 'DailyActivity', 'Steps', 1),
    ('sleep_score', 'Sleep score', 'score', 'Scores', 'DailySleep', None, 1),
    ('readiness', 'Readiness score', 'score', 'Scores', 'DailyReadiness', None, 1),
    ('activity', 'Activity score', 'score', 'Scores', 'DailyActivity', None, 1),
    ('sleep_breath', 'Main sleep respiratory rate', 'breaths/min', 'Sleep', 'Sleep', 'AverageBreath', 1),
    ('sleep_awake', 'Main sleep awake time', 'min', 'Sleep', 'Sleep', 'AwakeTime', 60),
    ('sleep_in_bed', 'Main sleep time in bed', 'h', 'Sleep', 'Sleep', 'TimeInBed', 3600),
    ('sleep_deep', 'Main sleep deep sleep', 'h', 'Sleep', 'Sleep', 'DeepSleepDuration', 3600),
    ('sleep_light', 'Main sleep light sleep', 'h', 'Sleep', 'Sleep', 'LightSleepDuration', 3600),
    ('sleep_rem', 'Main sleep REM sleep', 'h', 'Sleep', 'Sleep', 'RemSleepDuration', 3600),
    ('sleep_latency', 'Main sleep latency', 'min', 'Sleep', 'Sleep', 'Latency', 60),
    ('sleep_restless', 'Main sleep restless periods', 'count', 'Sleep', 'Sleep', 'RestlessPeriods', 1),
    ('sleep_hr_summary', 'Main sleep heart rate (Oura summary)', 'bpm', 'Sleep', 'Sleep', 'AverageHeartRate', 1),
    ('sleep_hrv_summary', 'Main sleep HRV (Oura summary)', 'ms', 'Sleep', 'Sleep', 'AverageHRV', 1),
    ('active_calories', 'Active calories', 'kcal', 'Activity', 'DailyActivity', 'ActiveCalories', 1),
    ('total_calories', 'Total calories', 'kcal', 'Activity', 'DailyActivity', 'TotalCalories', 1),
    ('activity_high', 'High activity time', 'min', 'Activity', 'DailyActivity', 'HighActivityTime', 60),
    ('activity_medium', 'Medium activity time', 'min', 'Activity', 'DailyActivity', 'MediumActivityTime', 60),
    ('activity_low', 'Low activity time', 'min', 'Activity', 'DailyActivity', 'LowActivityTime', 60),
    ('sedentary', 'Sedentary time', 'h', 'Activity', 'DailyActivity', 'SedentaryActivityTime', 3600),
    ('resting_time', 'Resting time', 'h', 'Activity', 'DailyActivity', 'RestingTime', 3600),
    ('nonwear', 'Non-wear time', 'h', 'Activity', 'DailyActivity', 'NonWearTime', 3600),
    ('inactivity_alerts', 'Inactivity alerts', 'count', 'Activity', 'DailyActivity', 'InactivityAlert', 1),
    ('walking_distance', 'Equivalent walking distance', 'm', 'Activity', 'DailyActivity', 'EquivalentWalkingDistance', 1),
    ('meters_to_target', 'Distance to activity target', 'm', 'Activity', 'DailyActivity', 'MetersToTarget', 1),
    ('target_distance', 'Activity target distance', 'm', 'Activity', 'DailyActivity', 'TargetMets', 1),
    ('high_met', 'High activity MET minutes', 'MET·min', 'Activity', 'DailyActivity', 'HighActivityMETMinutes', 1),
    ('medium_met', 'Medium activity MET minutes', 'MET·min', 'Activity', 'DailyActivity', 'MediumActivityMETMinutes', 1),
    ('low_met', 'Low activity MET minutes', 'MET·min', 'Activity', 'DailyActivity', 'LowActivityMETMinutes', 1),
    ('sedentary_met', 'Sedentary MET minutes', 'MET·min', 'Activity', 'DailyActivity', 'SedentaryActivityMETMinutes', 1),
    ('temperature', 'Temperature deviation', '°C', 'Readiness', 'DailyReadiness', 'TemperatureDeviation', 1),
    ('temperature_trend', 'Temperature trend deviation', '°C', 'Readiness', 'DailyReadiness', 'TemperatureTrendDeviation', 1),
    ('spo2', 'Blood oxygen saturation', '%', 'Physiology', 'DailySpo2', 'Spo2', 1),
    ('breathing_disturbance', 'Breathing disturbance index', 'index', 'Physiology', 'DailySpo2', 'BreathingDisturbance', 1),
    ('stress', 'High stress time', 'min', 'Stress and recovery', 'DailyStress', 'StressHigh', 60),
    ('recovery', 'High recovery time', 'min', 'Stress and recovery', 'DailyStress', 'RecoveryHigh', 60),
    ('vascular_age', 'Cardiovascular age', 'years', 'Physiology', 'DailyCardiovascularAge', 'VascularAge', 1),
)


def finite(value):
    """Do not coerce strings, booleans, containers or missing values into data."""
    return float(value) if isinstance(value, Real) and not isinstance(value, (bool, np.bool_)) and math.isfinite(value) else None


def allowed(row):
    return bool(day_label(row) and row.get('Metadata', {}).get('QualityControl', {}).get('summary_included', True))


def daily_rows(records):
    """One record per Oura day; latest source timestamp wins, ties last loaded."""
    result = {}
    for row in records:
        if not allowed(row):
            continue
        day = day_label(row)
        timestamp = finite(row.get('Metadata', {}).get('DailySummaryTimestamp'))
        timestamp = timestamp if timestamp is not None else finite(row.get('StartTime'))
        timestamp = timestamp if timestamp is not None else -math.inf
        if day not in result or timestamp >= result[day][0]:
            result[day] = (timestamp, row)
    return {day: pair[1] for day, pair in result.items()}


def sleep_bounds(row):
    descriptor = row.get('Descriptor', {})
    start, end = finite(descriptor.get('BedtimeStart')), finite(descriptor.get('BedtimeEnd'))
    if start is None or end is None:
        times = sample_times(row)
        times = times[np.isfinite(times)]
        rate = finite(row.get('SamplingRate'))
        if not len(times) or rate is None or rate <= 0:
            return None
        start = float(times.min()) if start is None else start
        end = float(times.max() + 1 / rate) if end is None else end
    return (start, end) if end > start else None


def main_sleep_rows(records):
    """Longest time-in-bed session per eligible Oura day; never add naps."""
    sessions = {}
    for row in records:
        if not allowed(row):
            continue
        bounds = sleep_bounds(row)
        if bounds is not None:
            sessions[(day_label(row), *bounds)] = row
    main = {}
    for (day, start, end), row in sorted(sessions.items()):
        if day not in main or end - start > main[day][0]:
            main[day] = (end - start, row)
    return {day: pair[1] for day, pair in main.items()}, len(sessions)


def total_sleep_rows(records):
    """Sum distinct nonoverlapping sessions; incomplete days remain unavailable."""
    sessions, invalid = {}, set()
    for row in records:
        if not allowed(row):
            continue
        day, bounds = day_label(row), sleep_bounds(row)
        if bounds is None:
            invalid.add(day)
            continue
        sessions[(day, *bounds)] = row
    totals, previous_end = {}, {}
    for (day, start, end), row in sorted(sessions.items()):
        duration = finite(row.get('Descriptor', {}).get('TotalSleepDuration'))
        if duration is None or duration < 0 or duration > end - start or start < previous_end.get(day, -math.inf):
            invalid.add(day)
        else:
            totals[day] = totals.get(day, 0) + duration
        previous_end[day] = max(end, previous_end.get(day, end))
    return {day: {'Descriptor': {'TotalSleepDuration': total}} for day, total in totals.items() if day not in invalid}, sorted(invalid)


def sample_metric(data, name):
    """Exact eligible timestamps across source coverage, with explicit null cells.

    HR and HRV search every available channel, without sleep/state filtering.
    Standard HeartRate observations take priority at duplicate HR timestamps;
    another eligible finite observation fills an absent source cell.
    The standard current ingest only supplies HRV in Sleep, which is reported.
    """
    unique, streams, intervals = {}, set(), set()
    aliases = {'Heart Rate Variability', 'HRV'} if name == 'Heart Rate Variability' else {'Heart Rate'}
    for stream, records in data.items():
        for row in records:
            names = row.get('ChannelNames', [])
            column = next((i for i, channel in enumerate(names) if channel in aliases), None)
            if column is None:
                continue
            times = sample_times(row)
            values = np.asarray(row['Data'], dtype=float)
            missing = np.asarray(row.get('Missing', np.zeros_like(values)), dtype=bool)
            if values.shape != (len(times), len(names)) or missing.shape != values.shape:
                raise ValueError('Oura sample/channel/mask shapes do not match')
            streams.add(stream)
            rate = finite(row.get('SamplingRate'))
            if rate is not None and rate > 0:
                intervals.add(1 / rate)
            for time, value, absent in zip(times, values[:, column], missing[:, column]):
                if not np.isfinite(time):
                    continue
                observed = None if absent or not np.isfinite(value) or value < (1 if name == 'Heart Rate' else 0) else float(value)
                priority = 0 if observed is None else 2 if name == 'Heart Rate' and stream == 'HeartRate' else 1
                # Prefer eligible observations; standard HR wins finite conflicts.
                # Last loaded wins equal-priority records, without extra weight.
                if float(time) not in unique or priority >= unique[float(time)][2]:
                    unique[float(time)] = (observed, stream, priority)
    points = [{'time': time, 'day': dt.datetime.fromtimestamp(time, PACIFIC).date().isoformat(), 'value': value, 'source': stream}
              for time, (value, stream, _) in sorted(unique.items())]
    return {'points': points, 'resolution': 'sample', 'max_gap_seconds': 900,
            'source_streams': sorted(streams), 'source_interval_seconds': sorted(intervals),
            'day_basis': 'Sample timestamp in America/Los_Angeles',
            'coverage': {'recorded_points': len(points), 'observed_points': sum(point['value'] is not None for point in points),
                         'start': points[0]['time'] if points else None, 'end': points[-1]['time'] if points else None},
            'coverage_note': ('HRV is available only where recorded; current standard ingest records HRV during sleep.'
                              if name == 'Heart Rate Variability' else
                              'All recorded heart-rate channels and times; standard HeartRate observations preferred when timestamps overlap.'),
            'available': any(point['value'] is not None for point in points)}


def sample_mean(row, name):
    names = row.get('ChannelNames', [])
    if name not in names:
        return None
    times = sample_times(row)
    values = np.asarray(row['Data'], dtype=float)
    missing = np.asarray(row.get('Missing', np.zeros_like(values)), dtype=bool)
    if values.shape != (len(times), len(names)) or missing.shape != values.shape:
        raise ValueError('Oura sample/channel/mask shapes do not match')
    column = names.index(name)
    # Duplicate timestamps do not gain weight; the last source cell wins.
    unique = {}
    for time, value, absent in zip(times, values[:, column], missing[:, column]):
        if np.isfinite(time):
            unique[float(time)] = None if absent or not np.isfinite(value) or value < (1 if name == 'Heart Rate' else 0) else float(value)
    observed = [value for value in unique.values() if value is not None]
    return sum(observed) / len(observed) if observed else None


def metric_value(row, descriptor):
    if descriptor is None:
        value = finite(row.get('Metadata', {}).get('Score'))
        return value if value is not None and 0 <= value <= 100 else None
    if descriptor.startswith('@'):
        return sample_mean(row, descriptor[1:])
    value = finite(row.get('Descriptor', {}).get(descriptor))
    # Negative temperature deviations and distance-to-goal values are real.
    if value is not None and value < 0 and descriptor not in {'TemperatureDeviation', 'TemperatureTrendDeviation', 'MetersToTarget'}:
        return None
    return value


def build_report(data):
    """Accept ONLY standard, already QC-filtered loadOuraRingData output."""
    main, sessions = main_sleep_rows(data.get('Sleep', []))
    streams = {kind: daily_rows(rows) for kind, rows in data.items() if kind != 'Sleep'}
    streams['Sleep'] = main
    streams['SleepTotal'], incomplete_sleep_days = total_sleep_rows(data.get('Sleep', []))
    metrics = []
    for key, label, unit, group, stream, descriptor, divisor in CATALOG:
        if stream == '@sample':
            metrics.append({'key': key, 'label': label, 'unit': unit, 'group': group,
                            'default': key in DEFAULT_METRICS, **sample_metric(data, descriptor)})
            continue
        points = []
        for day, row in sorted(streams.get(stream, {}).items()):
            value = metric_value(row, descriptor)
            if value is not None:
                points.append({'day': day, 'value': value / divisor})
        metrics.append({'key': key, 'label': label, 'unit': unit, 'group': group,
                        'points': points, 'resolution': 'day', 'available': bool(points), 'default': key in DEFAULT_METRICS,
                        'definition': ('Time asleep in the longest recorded sleep episode for each Oura day. This is usually overnight but can occur during daytime; awake time and other sleep episodes are excluded.'
                                       if key == 'sleep_duration' else
                                       'Sum of distinct nonoverlapping sessions, including naps, per Oura day. Awake time excluded; incomplete days omitted.'
                                       if key == 'sleep_total' else 'Oura estimated total daily energy expenditure.'
                                       if key == 'total_calories' else '')})
    versions = sorted({row.get('Metadata', {}).get('QualityControl', {}).get('version', 'standard-source-missing-mask')
                       for rows in data.values() for row in rows})
    return {'metrics': metrics, 'defaults': list(DEFAULT_METRICS), 'provenance': {
        'adapter_version': VERSION, 'source': 'BRAVO standard QC-filtered Oura store',
        'day_basis': 'Oura day (no UTC date conversion)', 'timezone': 'America/Los_Angeles',
        'qc_versions': versions, 'records_loaded': sum(len(rows) for rows in data.values()),
        'sleep_sessions': sessions, 'main_sleep_days': len(main),
        'sleep_aggregation': 'Main sleep: longest time-in-bed session per Oura day. Total sleep: sum of distinct nonoverlapping sessions including naps; awake time excluded.',
        'incomplete_sleep_total_days': incomplete_sleep_days,
        'sample_trace_policy': 'Exact source timestamps; explicit missing/null readings; chart lines break across gaps over 900 seconds',
        'sample_statistics': 'Default HR/HRV preserve individual samples. At duplicate timestamps, eligible values take priority over missing cells; standard HeartRate observations win HR conflicts. Optional main-sleep summary means exclude missing values.',
        'daily_duplicates': 'Latest summary timestamp per Oura day; last loaded wins equal timestamps',
        'missing_days': 'Missing and QC-excluded days are absent observations, never zeros; line charts must preserve gaps',
        'score_policy': 'Only genuine Metadata.Score values, never contributor averages',
        'non_numeric_fields': ['Stress day summary', 'Score contributor detail', 'Sleep bedtime timestamps',
                               'Sleep stages and movement samples', 'Activity classes and MET samples', 'Heart-rate state samples'],
    }}
