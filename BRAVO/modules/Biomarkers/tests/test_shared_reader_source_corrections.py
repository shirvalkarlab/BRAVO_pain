"""Source corrections invalidate products and never emit unusable channel spectra."""
from types import SimpleNamespace
import numpy as np
from modules.Biomarkers import bravo_service as service


def test_raw_tile_identity_tracks_metadata_changes_and_missing_rows(monkeypatch):
    state = {'person': object(), 'sources': ['s'], 'rows': []}
    fake = SimpleNamespace(Participant=SimpleNamespace(find=lambda **k: state['person']),
        SourceFile=SimpleNamespace(find_all=lambda **k: state['sources']),
        Recording=SimpleNamespace(find_all=lambda **k: state['rows']))
    monkeypatch.setattr(service, 'models', fake)
    monkeypatch.setattr(service._data_start, 'data_start_s', lambda u: 0)
    assert service._raw_lsb_recording_identity_uncached('synthetic') is None
    row = SimpleNamespace(uid='r', hashed='immutable', type=service.TIMEDOMAIN_TYPES[0], metadata={})
    event = SimpleNamespace(uid='event', hashed='', type=service.PATIENT_EVENT_TYPE, metadata={'Frequency': [10]}, date=100)
    bare = SimpleNamespace(uid='bare', hashed='b', type=service.TIMEDOMAIN_TYPES[0], metadata=None)
    state['rows'] = [row, event, bare]
    initial = service._raw_lsb_recording_identity_uncached('synthetic')
    row.metadata = {'SignalLeadSchedule': [[0, 'LEFT']]}
    changed = service._raw_lsb_recording_identity_uncached('synthetic')
    assert initial != changed
    state['rows'].reverse()
    assert changed == service._raw_lsb_recording_identity_uncached('synthetic')
    event.metadata = {'Frequency': [20]}
    assert changed != service._raw_lsb_recording_identity_uncached('synthetic')
    state['rows'] = []
    assert service._load_recordings_uncached('synthetic', []) == []
    state['sources'] = []
    assert service._raw_lsb_recording_identity_uncached('synthetic') is None
    state['person'] = None
    assert service._raw_lsb_recording_identity_uncached('synthetic') is None
    assert service._load_recordings_uncached('synthetic', []) == []
    state['person'] = object()
    assert service._load_recordings_uncached('synthetic', []) == []


def test_saturated_channel_never_emits_rows_in_either_welch_route():
    spectrum = np.array([[[np.nan, np.nan], [1.0, 2.0]]])
    processor = SimpleNamespace(F_SET=np.array([10., 20.]), WELCH_MAX_SECONDS=30,
        welch_rating_centered=lambda *a, **k: (spectrum, np.array([30.]), np.array([True])),
        welch_psd_for_instance=lambda *a, **k: spectrum)
    recording = {'ChannelNames': ['ZERO_THREE_LEFT', 'ZERO_THREE_RIGHT'],
                 'Data': np.ones((7500, 2)), 'SamplingRate': 250, 'StartTime': 1_700_000_000}
    for pro in (None, [1_700_000_015]):
        rows, counts = [], {}
        service._welch_rows_into(rows, [None, {}, dict(recording, Data=[1]),
             dict(recording, StartTime=None), recording], 'TD streaming', processor,
             pro_times=pro, counts=counts)
        assert len(rows) == 1 and rows[0]['channel'] == 'ZERO_THREE_RIGHT'
        assert counts == {'n_centered_fell_back': 0, 'n_skipped': 0}
    processor.welch_psd_for_instance = lambda *a, **k: np.full((1,2,2), np.nan)
    rows = []
    service._welch_rows_into(rows, [recording], 'TD streaming', processor)
    assert rows == []


def test_montage_missing_time_values_and_channel_are_withheld(monkeypatch):
    monkeypatch.setattr(service, '_load_recordings', lambda *a: [])
    assert service._montage_psd_lsb_blocks('synthetic') == []
    def record(descriptor, **extra):
        return dict(StartTime=1_700_000_000, Descriptor=descriptor, **extra)
    cases = [None, {}, record({'SignalCheck': {}}),
        record({'MedtronicPSD': [None, {}, {'LFPFrequency': [1], 'LFPMagnitude': [2]}]}, RunUnknown=True)]
    assert service._montage_psd_lsb_blocks('synthetic', cases) == []
