"""RCS08 Oura eligibility, with separate day and sample decisions.

Policy source: Percept/output/handoffs/RCS08_oura_pain_2026-09-03/
oura_data/oura_exclusion_windows.csv. Raw snapshots are never modified.
"""
import copy
import csv
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

VERSION = 'rcs08-oura-qc-1'
PACIFIC = ZoneInfo('America/Los_Angeles')
POLICY_PATH = Path(__file__).resolve().parents[2] / 'config' / 'rcs08_oura_exclusion_windows.csv'


def policy():
    with POLICY_PATH.open() as stream:
        rules = list(csv.DictReader(stream))
    by_basis = {r['target_time_basis']: r for r in rules}
    if len(rules) != 2 or any(r['participant_id'] != 'RCS08' or r['action'] != 'exclude' for r in rules):
        raise ValueError('Invalid RCS08 Oura eligibility policy')
    return by_basis['Oura day'], by_basis['timezone-aware timestamp']


def sample_times(record):
    n = len(record['Data'])
    if 'Time' in record:
        times = np.asarray(record['Time'], dtype=float)
    elif n:
        rate = float(record.get('SamplingRate', 0))
        if rate <= 0:
            raise ValueError('Oura samples have no explicit time or positive sampling rate')
        times = float(record['StartTime']) + np.arange(n) / rate
    else:
        times = np.empty(0)
    if times.shape != (n,):
        raise ValueError('Oura sample/time lengths do not match')
    return times


def day_label(record):
    value = record.get('Metadata', {}).get('DayLabel')
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return None


def apply_quality_control(data):
    """Return independent analysis data and a per-record audit, without writes.

    Excluded timestamps are masked rather than compressed: plotted lines cannot
    bridge a staff-testing interval and implicit sampling never shifts. Day-level
    descriptors are suppressed independently, preserving eligible May 27 samples.
    """
    daily, timed = policy()
    start = dt.datetime.fromisoformat(timed['start_inclusive']).timestamp()
    end = dt.datetime.fromisoformat(timed['end_exclusive']).timestamp()
    cleaned, audit = {}, []
    for kind, records in data.items():
        cleaned[kind] = []
        for index, original in enumerate(records):
            row = copy.deepcopy(original)
            label = day_label(row)
            has_summary = kind != 'HeartRate'
            in_day_window = bool(label and daily['start_inclusive'] <= label < daily['end_exclusive'])
            summary_ok = bool(has_summary and label and not in_day_window)
            times = sample_times(row)
            time_window = (times >= start) & (times < end)
            invalid_time = ~np.isfinite(times)
            blocked = time_window | invalid_time
            values = np.asarray(row['Data'], dtype=float).copy()
            missing = np.asarray(row.get('Missing', np.zeros_like(values)), dtype=bool)
            if values.shape != missing.shape:
                raise ValueError('Oura data/missing-mask shapes do not match')
            invalid_value = missing | ~np.isfinite(values)
            if len(values):
                values[invalid_value] = np.nan
                values[blocked, :] = np.nan
                row['Data'] = values
                row['Missing'] = (~np.isfinite(values)).astype(float)
                row['Time'] = times.copy()
            else:
                row['Data'] = values
            # The source chunk's HeartRate StateLabels are decoding metadata.
            if has_summary and not summary_ok:
                row['Descriptor'] = {}
                row['Metadata']['Score'] = None
                row['Metadata']['ScoreContributors'] = {}
            row['Metadata']['QualityControl'] = {
                'version': VERSION, 'summary_included': summary_ok,
                'day_rule': daily['filter_id'] if in_day_window else None,
                'timestamp_rule': timed['filter_id'],
            }
            if summary_ok or (len(times) and (~blocked).any()):
                cleaned[kind].append(row)
            audit.append({
                'id': f'{kind}:{index + 1}', 'stream': kind, 'index': index,
                'day': label, 'start': float(original['StartTime']),
                'summary_applicable': has_summary, 'summary_included': summary_ok,
                'summary_reason': ('No daily summary; chunk day is not sample identity' if not has_summary else
                                   'Missing/invalid Oura day' if not label else
                                   daily['reason'] if in_day_window else 'Outside reviewed exclusion window'),
                'sample_rows': len(times), 'window_excluded_samples': int(time_window.sum()),
                'invalid_time_samples': int(invalid_time.sum()),
                'eligible_time_samples': int((~blocked).sum()),
                'missing_cells_before': int(invalid_value.sum()),
                'eligible_missing_cells': int(invalid_value[~blocked].sum()),
                'eligible_observed_cells': int(np.isfinite(values).sum()),
            })
    return cleaned, audit


def timeline_series(data):
    """Render daily values by Oura day and sample values by their exact times."""
    result = []
    for kind, records in data.items():
        descriptors = sorted({key for row in records for key, value in row['Descriptor'].items()
                              if isinstance(value, (int, float)) or value is None})
        summary_rows = [r for r in records if r.get('Metadata', {}).get('QualityControl', {}).get('summary_included', True)
                        and day_label(r)]
        if descriptors and summary_rows:
            summary_rows.sort(key=lambda r: day_label(r))
            times = [dt.datetime.combine(dt.date.fromisoformat(day_label(r)), dt.time(), PACIFIC).timestamp()
                     for r in summary_rows]
            values = [[r['Descriptor'].get(key) for r in summary_rows] for key in descriptors]
            values = [[float(v) if isinstance(v, (int, float)) and np.isfinite(v) else None for v in arr] for arr in values]
            # Explicit blank days prevent a line across absent/excluded summaries.
            expanded_times, expanded_values = [], [[] for _ in values]
            for i, time in enumerate(times):
                if i and (dt.date.fromisoformat(day_label(summary_rows[i])) -
                          dt.date.fromisoformat(day_label(summary_rows[i-1]))).days > 1:
                    expanded_times.append(times[i-1] + 86400)
                    for channel in expanded_values:
                        channel.append(None)
                expanded_times.append(time)
                for channel, original in zip(expanded_values, values):
                    channel.append(original[i])
            times, values = expanded_times, expanded_values
            result.append({'AnalysisType': 'CustomizedTimelineData', 'Time': times, 'Duration': [86400] * len(times),
                           'ChannelNames': [f'[OURA] {kind} {key}' for key in descriptors],
                           'ChannelUnits': [''] * len(descriptors), 'Data': values})
        for row in records:
            if not len(row['Data']):
                continue
            times = sample_times(row)
            values = np.asarray(row['Data'], dtype=float).copy()
            missing = np.asarray(row.get('Missing', np.zeros_like(values)), dtype=bool)
            values[missing | ~np.isfinite(values)] = np.nan
            series = []
            units = []
            for col, name in enumerate(row['ChannelNames']):
                if name == 'Sleep Phase':
                    stages = {1: 'deep', 2: 'light', 3: 'rem', 4: 'awake'}
                    series.append([stages.get(int(v)) if np.isfinite(v) else None for v in values[:, col]])
                    units.append('Category')
                else:
                    series.append([float(v) if np.isfinite(v) else None for v in values[:, col]])
                    units.append('')
            valid = np.isfinite(times)
            result.append({'AnalysisType': 'CustomizedTimelineData', 'Time': times[valid].tolist(),
                           'Duration': np.diff(times[valid], append=times[valid][-1]).tolist() if valid.any() else [],
                           'ChannelNames': [f'[OURA] {kind} {name}' for name in row['ChannelNames']],
                           'ChannelUnits': units, 'Data': [[v for v, keep in zip(arr, valid) if keep] for arr in series]})
    return result
