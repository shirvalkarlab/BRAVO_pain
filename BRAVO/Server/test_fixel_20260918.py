"""Synthetic integration regressions for Fixel adaptations; no owner data or services."""
import json
import struct
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from django.db import connection
from django.test import TestCase

from Server import models
from modules import Database
from modules.BIDSExport import Gather, Convert
from modules.ExternalDevices import BRAVOfflineWinUI as mdat


def packet(name, data, timestamp=1000000):
    name = name.encode()
    data = data.encode() if isinstance(data, str) else np.asarray(data, dtype='<f8').tobytes()
    return b'PFF\x00' + struct.pack('<qii', timestamp, len(name), len(data)) + name + data


def channel(name='EMG', rate=2):
    return packet('Delsys_ChannelIDs', name) + packet('Delsys_SamplingRate', [rate])


def test_v3_channels_preserve_independent_clock_lengths_gaps_and_missing():
    raw = (channel('A', 2) + channel('B', 4)
           + packet('Delsys_DataPacket|A', [1, 2], 1000000)
           + packet('Delsys_DataPacket|A', [3, np.nan], 1001000)
           + packet('Delsys_DataPacket|A', [5], 1005000)
           + packet('Delsys_DataPacket|B', [9, 8, 7], 2000000))
    decoded = mdat.decodeMDATv3(raw)
    assert [entry['StartTime'] for entry in decoded] == [1000, 1005, 2000]
    assert [entry['Duration'] for entry in decoded] == [2, .5, .75]
    np.testing.assert_equal(decoded[0]['Data'][:, 0], [1, 2, 3, np.nan])
    assert decoded[0]['Missing'][:, 0].tolist() == [0, 0, 0, 1]
    assert decoded[0]['PacketTimesMilliseconds'] == [1000000, 1001000]
    assert decoded[2]['Time'].tolist() == [0, .25, .5]
    assert [entry['ChannelNames'] for entry in decoded] == [['A'], ['A'], ['B']]
    assert mdat.decodeMDATAuto(raw)[0]['StartTime'] == 1000


def test_legacy_v2_auto_routing_retains_output():
    raw = (packet('TriggerText', 'Delsys Started') + packet('EMG SamplingRate', [2])
           + packet('EMG', [1, 2, 3]))
    expected = mdat.decodeMDATv2(raw)
    actual = mdat.decodeMDATAuto(raw)
    assert actual[0]['StartTime'] == expected[0]['StartTime'] == 1000
    np.testing.assert_equal(actual[0]['Data'], expected[0]['Data'])


@pytest.mark.parametrize('raw', [
    b'', b'PFF', b'BAD!' + b'\x00' * 20,
    b'PFF\x00' + struct.pack('<qii', 1, -1, 0),
    b'PFF\x00' + struct.pack('<qii', 1, 1, -1),
    b'PFF\x00' + struct.pack('<qii', 1, 30, 0),
    b'PFF\x00' + struct.pack('<qii', 1, 1, 1) + b'Ax',
])
def test_mdat_rejects_malformed_framing(raw):
    with pytest.raises(ValueError):
        mdat.decodeMDATAuto(raw)


@pytest.mark.parametrize('raw', [
    channel('', 2), packet('Delsys_SamplingRate', [2]),
    channel('A', 0), channel('A', -1), channel('A', np.nan),
    channel('A', np.inf), packet('Delsys_ChannelIDs', 'A') + packet('Delsys_SamplingRate', []),
    channel('A', 2) + channel('A', 3),
    packet('Delsys_DataPacket|A', [1]),
    channel('A', 2) + packet('Delsys_DataPacket|A', []),
    channel('A', 2),
    channel('A', 2) + packet('Delsys_DataPacket|A', [1, 2]) + packet('Delsys_DataPacket|A', [3]),
])
def test_v3_rejects_ambiguous_rates_and_overlaps(raw):
    with pytest.raises(ValueError):
        mdat.decodeMDATv3(raw)


def test_v3_same_rate_redeclaration_and_trigger_metadata():
    raw = channel() + channel() + packet('TriggerText', 'Delsys Started') + packet('Delsys_DataPacket|EMG', [1])
    assert mdat.decodeMDATv3(raw)[0]['Data'].tolist() == [[1]]


def test_bids_new_labels_and_legacy_identity_are_stable(tmp_path):
    new = tmp_path / 'new'
    assert Gather._subject_label(str(new), 'a') == '0001'
    assert Gather._subject_label(str(new), 'b') == '0002'
    assert Gather._subject_label(str(new), 'a') == '0001'
    old = tmp_path / 'old'; old.mkdir()
    (old / '.bravo_subject_ids.json').write_text(json.dumps({'a': 1, 'b': 999}))
    assert Gather._subject_label(str(old), 'a') == '001'
    assert Gather._subject_label(str(old), 'c') == '1000'
    assert Gather._subject_label(str(old), 'a') == '001'


def test_bids_dedup_preserves_devices_corrections_and_all_source_lineage():
    seen = {}
    devices = {'a': 'one', 'b': 'one', 'c': 'two'}
    first = {'date': 40, 'type': 'Therapy', 'value': 1, 'source_id': 'a'}
    repeat = {**first, 'source_id': 'b'}
    corrected = {**repeat, 'value': 2}
    other = {**first, 'source_id': 'c'}
    assert Gather._dedupe_history([first, first], seen, devices) == [first]
    assert Gather._dedupe_history([repeat, corrected, other], seen, devices) == [corrected, other]
    assert len(seen) == 3
    assert list(seen.values())[0]['source_ids'] == ['a', 'b']
    assert first == {'date': 40, 'type': 'Therapy', 'value': 1, 'source_id': 'a'}
    unknown = {}
    assert len(Gather._dedupe_history([first, repeat], unknown, {})) == 2


@pytest.mark.parametrize('bounds', [None, (0, 10), (None, 10), (0, None)])
def test_bids_event_times_are_physical_elapsed_seconds(bounds):
    for value in [-10000, 0, 5, 10000]:
        assert Convert._clamp_onset(value, bounds) == value
    events = Convert.patient_events_dataframe([{'date': 10, 'source_id': 'synthetic'}], 100, bounds)
    assert events['onset'].tolist() == [-90]
    annotations = Convert.annotations_dataframe([{'date': 200, 'duration': 3}], 100, bounds)
    assert annotations['onset'].tolist() == [100]
    assert annotations['EndTimestamp'].tolist() == ['1970-01-01T00:03:23Z']


def test_reexport_removes_only_now_empty_generated_history(tmp_path):
    folder = tmp_path / 'sub-001' / 'ses-20260101' / 'beh'; folder.mkdir(parents=True)
    history = folder / 'sub-001_ses-20260101_task-TherapyHistory_beh.tsv'
    history.write_text('old duplicate')
    sidecar = history.with_suffix('.json'); sidecar.write_text('{}')
    unrelated = folder / 'sub-001_ses-20260101_task-Annotations_beh.tsv'; unrelated.write_text('keep')
    events = folder / 'sub-001_ses-20260101_task-PatientEvents_beh.tsv'; events.write_text('keep')
    Gather._clear_empty_history(str(tmp_path), '001', '20260101', {'therapies': [], 'events': [{}], 'impedance_measurements': []})
    assert not history.exists() and not sidecar.exists()
    assert unrelated.read_text() == events.read_text() == 'keep'


class DatabaseAndAlignmentTests(TestCase):
    def setUp(self):
        self.person = models.Participant.objects.create(name='Synthetic Fixel fixture')
        self.source = models.SourceFile.objects.create(owner=self.person, metadata={'Device': 'one'})
        self.first = models.Recording.objects.create(source=self.source, type='SynchronizedMDAT', date=100)
        self.sibling = models.Recording.objects.create(source=self.source, type='CustomizedTimelineData', date=200)
        self.neural = models.Recording.objects.create(source=self.source, type='MedtronicChronicBrainSense', date=300)
        self.other = models.Recording.objects.create(source=models.SourceFile.objects.create(owner=self.person), type='SynchronizedMDAT')

    def test_sqlite_lookup_and_containment_query_contract(self):
        other = models.Participant.objects.create()
        models.SourceFile.objects.create(owner=other, metadata={'Device': 'one'})
        models.SourceFile.objects.create(owner=self.person, metadata={'Device': None})
        selected = models.SourceFile.find_all(owner=self.person, **Database.deviceMetadataLookup('one'))
        self.assertEqual(list(selected), [self.source])
        with patch.object(connection.features, 'supports_json_field_contains', True):
            self.assertEqual(Database.deviceMetadataLookup('one'), {'metadata__contains': {'Device': 'one'}})
            self.assertEqual(Database.deviceMetadataLookup('one', 'source__metadata'), {'source__metadata__contains': {'Device': 'one'}})

    def test_source_alignment_is_scoped_and_invalidates_after_commit(self):
        from Server.APIs.DataHandler import updateRecordingAlignment
        with patch.object(Database, 'deleteCachedResult') as invalidate, self.captureOnCommitCallbacks(execute=True):
            updateRecordingAlignment(self.first, '2.5', propagate=True)
            invalidate.assert_not_called()
        invalidate.assert_called_once_with(participant_uid=self.person.uid)
        for obj, expected in [(self.first, 2.5), (self.sibling, 2.5), (self.neural, 0), (self.other, 0)]:
            obj.refresh_from_db(); self.assertEqual(obj.adjusted_alignment, expected)
        self.assertEqual((self.first.date, self.sibling.date, self.neural.date), (100, 200, 300))

    def test_single_record_and_non_synchronized_alignment(self):
        from Server.APIs.DataHandler import updateRecordingAlignment
        updateRecordingAlignment(self.first, -3)
        updateRecordingAlignment(self.neural, 4, propagate=True)
        self.first.refresh_from_db(); self.sibling.refresh_from_db(); self.neural.refresh_from_db()
        self.assertEqual((self.first.adjusted_alignment, self.sibling.adjusted_alignment, self.neural.adjusted_alignment), (-3, 0, 4))

    def test_invalid_alignment_and_failure_are_atomic(self):
        from Server.APIs.DataHandler import updateRecordingAlignment
        for value in ['nan', 'inf', '-inf', 'bad']:
            with self.assertRaises(ValueError):
                updateRecordingAlignment(self.first, value, propagate=True)
        with patch.object(models.Participant, 'save', side_effect=RuntimeError('synthetic write failure')):
            with self.assertRaises(RuntimeError):
                updateRecordingAlignment(self.first, 5, propagate=True)
        self.first.refresh_from_db(); self.sibling.refresh_from_db()
        self.assertEqual((self.first.adjusted_alignment, self.sibling.adjusted_alignment), (0, 0))

    def test_mdat_v3_storage_roundtrip_dedup_and_participant_isolation(self):
        from modules import DataCurator
        raw = channel() + packet('Delsys_DataPacket|EMG', [7, 8])
        original_source = DataCurator.saveCacheFile('synthetic [one].mdat', {'UploadType': 'UFMDATv3', 'Uploader': 'fixture'}, raw)
        DataCurator.UFMDATv3Decoder(original_source, self.person)
        first = models.Recording.objects.get(source=original_source)
        saved = Database.loadSourceFile(first.pointer, first.hashed)
        self.assertEqual(saved['Data'].tolist(), [[7], [8]])
        self.assertEqual(saved['PacketTimesMilliseconds'], [1000000])
        original_source.refresh_from_db()
        self.assertEqual(DataCurator.loadCacheFile(original_source), raw)
        duplicate = DataCurator.saveCacheFile('synthetic.mdat', {'UploadType': 'UFMDATv3', 'Uploader': 'fixture'}, raw)
        DataCurator.UFMDATAutoDecoder(duplicate, self.person)
        self.assertFalse(models.Recording.objects.filter(source=duplicate).exists())
        other = models.Participant.objects.create()
        second_source = DataCurator.saveCacheFile('synthetic.mdat', {'UploadType': 'UFMDATv3', 'Uploader': 'fixture'}, raw)
        DataCurator.UFMDATv3Decoder(second_source, other)
        self.assertTrue(models.Recording.objects.filter(source=second_source).exists())
        changed = DataCurator.saveCacheFile('synthetic.mdat', {'UploadType': 'UFMDATv3', 'Uploader': 'fixture'}, channel() + packet('Delsys_DataPacket|EMG', [9, 10]))
        DataCurator.UFMDATv3Decoder(changed, self.person)
        self.assertTrue(models.Recording.objects.filter(source=changed).exists())

    def test_mdat_storage_failure_surfaces_without_moving_original(self):
        from modules import DataCurator
        source = DataCurator.saveCacheFile('synthetic.mdat', {'UploadType': 'UFMDATv3'}, channel() + packet('Delsys_DataPacket|EMG', [7]))
        original = source.pointer
        with patch.object(Database, 'saveSourceFile', return_value=None), self.assertRaises(IOError):
            DataCurator.UFMDATv3Decoder(source, self.person)
        self.assertTrue(Path(original).exists())
        self.assertFalse(models.Recording.objects.filter(source=source).exists())

    def test_fitbit_sort_keeps_values_with_dates_in_actual_timeline_output(self):
        from modules import DataAnalysis
        models.SourceFile.objects.create(owner=self.person, type='FitbitWebAPISource')
        # Ignore unrelated recordings set up for alignment tests.
        records = [{'StartTime': t, 'Data': np.array([[value]]), 'ChannelNames': ['steps']}
                   for t, value in [(300, 3), (100, 1), (200, 2)]]
        with patch.object(DataAnalysis.FitbitDataManager, 'loadFitbitData', return_value={'activity': records}), patch.object(models.Recording, 'include', return_value=False):
            timelines, _ = DataAnalysis.queryChronicTimeline(self.person.uid, {})
        self.assertEqual(timelines[0]['Time'], [100, 200, 300])
        self.assertEqual(timelines[0]['Data'].tolist(), [[1, 2, 3]])

    def test_complete_bids_reexport_dedup_keeps_provenance_and_real_time(self):
        import os
        import tempfile
        import pandas as pd
        sources = [models.SourceFile.objects.create(owner=self.person, date=time,
                   pointer=f'/synthetic-unread-{i}.json', metadata={'Device': 'same', 'Timezone': 'UTC+00:00'})
                   for i, time in enumerate([86400, 172800])]
        def gathered(source):
            return {'participant': {'sex': 'Unknown', 'diagnosis': 'Synthetic', 'session_date': source.date},
                    'electrodes': [], 'device': None, 'electrode_info': {},
                    'streaming_recordings': [], 'survey_recordings': [], 'therapies': [],
                    'impedance_measurements': [], 'events': [{'date': 10, 'source_id': source.uid, 'type': 'Synthetic'}]}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DATASERVER_PATH': folder}), patch.object(Gather, 'gather_session', side_effect=gathered):
            self.assertEqual(Gather.export_participant(self.person.uid), [source.uid for source in sources])
            root = Path(folder) / 'BIDS'
            tables = list(root.glob('sub-*/ses-*/beh/*PatientEvents_beh.tsv'))
            self.assertEqual(len(tables), 1)
            self.assertEqual(pd.read_csv(tables[0], sep='\t')['onset'].tolist(), [-86390])
            lineage_path = root / 'sourcedata/bravo/sub-0001_history_sources.json'
            lineage = json.loads(lineage_path.read_text())['records']['events']
            self.assertEqual(list(lineage.values())[0]['source_ids'], [source.uid for source in sources])
            stale = root / 'sub-0001/ses-19700103/beh/sub-0001_ses-19700103_task-PatientEvents_beh.tsv'
            stale.parent.mkdir(parents=True, exist_ok=True); stale.write_text('stale duplicate')
            Gather.export_participant(self.person.uid)
            self.assertFalse(stale.exists())
            self.assertEqual(len(list(root.glob('sub-*/ses-*/beh/*PatientEvents_beh.tsv'))), 1)
            self.assertEqual(json.loads(lineage_path.read_text())['records']['events'], lineage)

    def test_legacy_multichannel_v2_upload_keeps_shared_sensor_name(self):
        from modules import DataCurator
        raw = (packet('TriggerText', 'Delsys Started')
               + packet('A EMG SamplingRate', [2]) + packet('B EMG SamplingRate', [2])
               + packet('A EMG', [1, 2]) + packet('B EMG', [3, 4]))
        source = DataCurator.saveCacheFile('legacy [recording].mdat', {'UploadType': 'UFMDATv2'}, raw)
        DataCurator.UFMDATv2Decoder(source, self.person)
        recording = models.Recording.objects.get(source=source)
        self.assertEqual(recording.metadata['SensorType'], 'EMG')
        self.assertEqual(recording.metadata['ChannelNames'], ['A EMG', 'B EMG'])
        self.assertEqual(Database.loadSourceFile(recording.pointer, recording.hashed)['Data'].tolist(), [[1, 3], [2, 4]])

    def test_therapy_query_call_sites_resolve_device_scoped_sources(self):
        from modules import Therapy
        device = models.DBSDevice.objects.create(owner=self.person)
        self.source.metadata = {'Device': device.uid}; self.source.save()
        models.TherapyModification.objects.create(source=self.source, owner=self.person, date=100, type='Synthetic')
        self.assertEqual(len(Therapy.queryTherapyModification(self.person)), 1)
        self.assertEqual(Therapy.queryTherapyGroups(self.person), [])
        self.assertFalse(Therapy.checkDuplicate(device, None, {'type': 'Synthetic', 'date': 100}))
