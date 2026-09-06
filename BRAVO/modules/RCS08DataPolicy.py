"""Reviewed RCS08 import boundaries; raw reports are always retained.

Implant day: 2025-07-16, verified in RCS08-Stage-1-Operative-Notes.docx.
The date boundary is local midnight, not an inferred exact surgery time.
Tablet labels are Left GPi / Right VIM, per the user's instruction.
"""
import datetime as dt
from zoneinfo import ZoneInfo

IMPLANT_DAY = dt.datetime(2025, 7, 16, tzinfo=ZoneInfo('America/Los_Angeles')).timestamp()
CANONICAL_NAME = 'RCS08 Right Percept RC'
EXPECTED_TARGETS = {'Left GPi', 'Right VIM'}


def applies_to(participant):
    """Keep the reviewed policy associated with its owner after a display rename."""
    if participant is None:
        return False
    if participant.name == 'RCS08':
        return True
    from Server import models
    return models.SourceFile.include(owner=participant, type='RCS08SurveyAudit')


def source_exclusion(report):
    device = report.get('DeviceInformation', {}).get('Final', {})
    if 'benchtop' in str(device.get('DeviceName', '')).lower():
        return 'Benchtop report; not the reviewed RCS08 implant'
    leads = report.get('LeadConfiguration', {}).get('Final', [])
    actual = {(lead.get('Hemisphere'), lead.get('LeadLocation'), lead.get('Model')) for lead in leads}
    expected = {
        ('HemisphereLocationDef.Left', 'LeadLocationDef.Gpi', 'LeadModelDef.LEAD_B33015'),
        ('HemisphereLocationDef.Right', 'LeadLocationDef.Vim', 'LeadModelDef.LEAD_B33015'),
    }
    if actual != expected:
        return 'Lead configuration does not match the reviewed RCS08 GPi/VIM B33015 implant'
    return None


def filter_decoded_entries(entries):
    """Remove pre-implant derived entries without modifying the original JSON."""
    import numpy as np
    removed = {}
    for key in ('Therapies', 'TherapyChangeHistory', 'SurveyRecordings', 'StreamingRecordings', 'EventRecordings'):
        rows = entries.get(key, [])
        keep = [row for row in rows if row.get('date', 0) >= IMPLANT_DAY]
        if len(keep) != len(rows): removed[key] = len(rows) - len(keep)
        entries[key] = keep
    rows = []
    for item in entries.get('ChronicRecordings', []):
        recording = item['recording']
        times = np.asarray(recording['Time'])
        keep = times >= IMPLANT_DAY
        if not keep.all():
            removed['ChronicSamples'] = removed.get('ChronicSamples', 0) + int((~keep).sum())
            if not keep.any(): continue
            recording['Time'] = times[keep]
            recording['Data'] = np.asarray(recording['Data'])[keep, :]
            recording['StartTime'] = float(recording['Time'][0])
            recording['Duration'] = float(recording['Time'][-1] - recording['Time'][0])
            item['date'] = recording['StartTime']
            item['metadata']['Duration'] = recording['Duration']
        rows.append(item)
    entries['ChronicRecordings'] = rows
    return removed
