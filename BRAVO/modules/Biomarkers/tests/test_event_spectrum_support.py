"""Synthetic tests of manufacturer-defined censored event-spectrum bins.

These spectra are independently constructed, not copied from participant data.
"""
import pathlib
import sys
import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from modules.Biomarkers.routines.event_spectra import (
    interpolate_observed_event_spectrum as interp, event_band_supported,
)
from modules.Biomarkers.routines import streaming_psd as sp, availability as av
from modules.Biomarkers.routines import analytics, timeline_detail


def test_censored_tail_and_no_endpoint_extension_with_valid_zero():
    f = [0, 1, 2, 3, 4]
    result = interp(f, [0, 2, 4, -1, -1], [-1, 0, .5, 1, 2, 2.5, 3, 4, 5])
    np.testing.assert_equal(result, [np.nan, 0, 1, 2, 4, np.nan, np.nan, np.nan, np.nan])


@pytest.mark.parametrize('missing', [-1, np.nan, np.inf])
def test_internal_missing_bin_is_not_bridged(missing):
    np.testing.assert_equal(interp([0, 1, 2, 3, 4], [1, 2, missing, 6, 8],
                                  [0, 1, 1.5, 2, 2.5, 3, 3.5, 4]),
                            [1, 2, np.nan, np.nan, np.nan, 6, 7, 8])


def test_missing_frequency_splits_runs_and_single_observation_only_matches_itself():
    np.testing.assert_equal(interp([0, np.nan, 2], [1, 3, 5], [0, .1, 1, 2]),
                            [1, np.nan, np.nan, 5])
    np.testing.assert_equal(interp([-1, 0, 1], [9, 2, -1], [-1, 0, .5]), [np.nan, 2, np.nan])


@pytest.mark.parametrize('f,m', [([], []), ([1], []), ([[1]], [[2]]), ([1], [[2]]),
                                ([1, 1], [1, 2]), ([2, 1], [1, 2]),
                                (['bad'], [1]), ([1], ['bad']), ([0, 1], [-1, -2])])
def test_invalid_or_fully_censored_spectrum_has_no_support(f, m):
    assert np.isnan(interp(f, m, [0, 1, 2])).all()
    assert not event_band_supported(f, m, 1, .2)


@pytest.mark.parametrize('center,half', [('bad', 1), (1, 'bad'), (np.nan, 1),
                                        (1, np.inf), (1, 0), (1, -1)])
def test_invalid_band_is_unavailable(center, half):
    assert not event_band_supported([0, 1, 2], [1, 2, 3], center, half)


def test_band_requires_contiguous_support_over_its_whole_width():
    f = np.arange(6.)
    m = [1, 0, 3, -1, 5, 6]
    assert event_band_supported(f, m, 1, 1)
    assert event_band_supported(f, m, 4.5, .5)
    assert not event_band_supported(f, m, 2, 1)
    assert not event_band_supported(f, m, 2.5, 2.5)
    assert not event_band_supported(f, m, .5, 1)
    assert not event_band_supported(f, m, 5, 1)


def _row(power, source='Patient event', freq=None):
    return {'channel':'ZERO_THREE_LEFT','t':1_750_000_000., 'source':source,
            'freq':np.arange(len(power), dtype=float) if freq is None else freq,'power':power}


def test_matrix_masks_event_only_and_preserves_existing_welch_numerics():
    grid = np.arange(-.5, 5, .5)
    event = _row([0, 2, 4, -1, -1])
    welch = _row([0, 2, 4, 6, 8], 'BrainSense TD')
    out = sp.psd_rows_to_matrix([event,welch], f_set=grid)
    np.testing.assert_equal(out['X'][0], interp(event['freq'],event['power'],grid))
    # Independently preserve the old waveform rule (strict-positive mask, NumPy endpoints).
    np.testing.assert_array_equal(out['X'][1], np.interp(grid,[1,2,3,4],[2,4,6,8]))
    assert out['source'].tolist() == ['Patient event','BrainSense TD']


def test_matrix_keeps_single_valid_zero_but_omits_wholly_unavailable_event():
    assert sp.psd_rows_to_matrix([_row([-1,-1])], f_set=[0,1]) is None
    out=sp.psd_rows_to_matrix([_row([0,-1]),_row([-1,-1]),_row([1,2],'BrainSense TD'),
                               dict(_row([1,2]),t=None),dict(_row([1,2]),channel=None)],f_set=[0,1])
    np.testing.assert_equal(out['X'], [[0,np.nan]])


def test_event_hover_and_detail_display_missing_bins_as_null_without_changing_raw():
    f=[0,1,2,3,4]; m=[0,2,-1,6,-1]
    out=av.event_markers([{'name':'synthetic label','category':'Patient event','t':1_750_000_000,
                           'psds':[(f,m)]}], fmin=0)['events'][0]
    assert out['psd']['mag'] == [0,2,None,6,None]
    assert out['peak_power']==6
    detail=timeline_detail._event_psd([_row(m,freq=f)],'ZERO_THREE_LEFT',1_750_000_000.)
    assert detail['mag']==[0,2,None,6,None]
    assert detail['unit']=='µVp'
    assert m == [0,2,-1,6,-1]


def test_event_hover_aligns_hemisphere_grids_without_extrapolating():
    event={'name':'synthetic','t':1_750_000_000.,'psds':[([0,1,2],[2,4,6]),([1,2,3],[10,12,14])]}
    assert av.event_markers([event])['events'][0]['psd']['mag']==[2,7,9]
    event['psds']=[([0,1,2],[-1,-1,-1])]
    out=av.event_markers([event])['events'][0]
    assert out['psd']['mag']==[None,None,None] and out['peak_hz'] is None


def test_montage_hover_path_retains_its_values():
    event={'name':'Montage PSD','category':'Montage PSD','t':1_750_000_000.,'psds':[([0,1,2],[1,2,3])]}
    assert av.event_markers([event])['events'][0]['psd']['mag']==[1,2,3]


@pytest.mark.parametrize('indexed',[True,False])
def test_lsb_timeline_retains_exact_observed_band_and_rejects_partial_band(indexed,monkeypatch):
    monkeypatch.setattr(av,'USE_CHANNEL_INDEX',indexed)
    f=np.arange(0,31.);m=np.ones(31);m[20:]=-1
    event=dict(_row(m,freq=f),center_hz=10.)
    out=av.lsb_series([],[],event_psd_recordings=[event])
    assert out[event['channel']]['y']==[analytics.device_psd_to_lsb(f,m,10.)]
    event['center_hz']=19.
    assert av.lsb_series([],[],event_psd_recordings=[event])=={}


@pytest.mark.parametrize('indexed',[True,False])
def test_modeled_band_keeps_exact_fully_observed_result_and_omits_censored_band(indexed,monkeypatch):
    monkeypatch.setattr(av,'USE_CHANNEL_INDEX',indexed)
    f=np.arange(0,31.);m=np.ones(31);m[20:]=-1
    rec={'ChannelNames':['ZERO_THREE_LEFT'],'Frequencies':f,'PSD':m,'source':'Patient event'}
    expected=analytics.device_psd_to_lsb(f,m,10.)
    assert av.modeled_lsb_at_center('ZERO_THREE_LEFT',10.,psd_recordings=[rec]).tolist()==[expected]
    assert av.modeled_lsb_at_center('ZERO_THREE_LEFT',19.,psd_recordings=[rec]).size==0


def test_raw_sweep_retains_observed_bands_but_censored_support_stays_missing():
    f=np.arange(0,31.);m=np.ones(31);m[20:]=-1
    event=_row(m,freq=f)
    out=av.raw_lsb_spectrum_cache('ZERO_THREE_LEFT',[10.,19.,25.],event_psd_recordings=[event])
    assert out['psd']['lsb'][0]==[analytics.device_psd_to_lsb(f,m,10.),None,None]


@pytest.mark.parametrize('indexed',[True,False])
@pytest.mark.parametrize('tag',[{}, {'source':'Montage PSD'}, {'RecordingType':'PatientControllerEvent'}])
def test_legacy_untyped_and_montage_path_not_reclassified_as_events(indexed,tag,monkeypatch):
    monkeypatch.setattr(av,'USE_CHANNEL_INDEX',indexed)
    f=np.arange(0,31.);m=np.ones(31);m[20:]=-1
    rec={'ChannelNames':['ZERO_THREE_LEFT'],'Frequencies':f,'PSD':m,**tag}
    got=av.modeled_lsb_at_center('ZERO_THREE_LEFT',19.,psd_recordings=[rec])
    if tag.get('RecordingType')=='PatientControllerEvent':
        assert got.size==0
    else:
        assert got.tolist()==[analytics.device_psd_to_lsb(f,m,19.)]


@pytest.mark.parametrize('ambiguity',[{'SenseIDConflict':True},{'SenseIDStatus':'ambiguous'}])
def test_ambiguous_contact_cannot_enter_channel_pool_or_index(ambiguity,monkeypatch):
    from types import SimpleNamespace
    from modules.Biomarkers import bravo_service as bs
    monkeypatch.setattr(bs.models.Participant,'find',lambda **kw: object())
    monkeypatch.setattr(bs.models.SourceFile,'find_all',lambda **kw: [object()])
    block={'Frequency':[0,1,2],'FFTBinData':[1,2,3],
           'DateTime':'2026-01-01T00:00:00Z','SenseID':'SensingElectrodeConfigDef.ZERO_AND_THREE',**ambiguity}
    monkeypatch.setattr(bs,'_patient_event_rows',lambda *a:[SimpleNamespace(
        metadata={'HemisphereLocationDef.Left':block},date=1_750_000_000.,name='Synthetic')])
    def must_not_resolve(*a,**kw):
        raise AssertionError('ambiguous source contacts reached channel resolver')
    monkeypatch.setattr(bs,'_resolve_event_channel',must_not_resolve)
    assert bs._event_psd_rows('synthetic')==[]
    assert bs._event_psd_index('synthetic')==[]


def test_event_markers_reject_malformed_arrays_and_montage_different_length():
    events=[{'name':'synthetic','t':1_750_000_000.,'psds':[([],[]),([0,1],[3])]},
            {'name':'Montage PSD','category':'Montage PSD','t':1_750_000_001.,
             'psds':[([0,1],[1,2]),([0,1,2],[3,4,5])]}]
    out=av.event_markers(events)['events']
    assert out[0]['psd'] is None and out[1]['psd']['mag']==[1,2]


def test_event_detail_matching_and_missing_arrays():
    assert timeline_detail._event_psd([], 'ZERO_THREE_LEFT', 1_750_000_000.) is None
    rows=[_row([1,2]),dict(_row([9,10]),t=1_750_000_000.5)]
    assert timeline_detail._event_psd(rows, 'ZERO_THREE_LEFT', 1_750_000_000.)['mag']==[1,2]
    assert timeline_detail._event_psd([dict(_row([1,2]),freq=None)],'ZERO_THREE_LEFT',1_750_000_000.) is None


@pytest.mark.parametrize('which',['_event_psd_rows','_event_psd_index'])
@pytest.mark.parametrize('case',['no_participant','no_sources','bad_metadata','bad_block','bad_arrays',
                                'no_time','no_channel','valid_block_time','valid_row_time'])
def test_channel_pool_and_index_keep_existing_nonambiguous_rules(which,case,monkeypatch):
    from types import SimpleNamespace
    from modules.Biomarkers import bravo_service as bs
    monkeypatch.setattr(bs.models.Participant,'find',lambda **kw: None if case=='no_participant' else object())
    monkeypatch.setattr(bs.models.SourceFile,'find_all',lambda **kw: [] if case=='no_sources' else [object()])
    block={'Frequency':[0,1,2],'FFTBinData':[1,2,3],
           'DateTime':'2026-01-01T00:00:00Z','SenseID':'SensingElectrodeConfigDef.ZERO_AND_THREE'}
    if case=='bad_arrays':block['FFTBinData']=[]
    if case in ['no_time','valid_row_time']:block['DateTime']=None
    md={'HemisphereLocationDef.Left': None if case=='bad_block' else block}
    if case=='bad_metadata':md=None
    row=SimpleNamespace(metadata=md,date=None if case=='no_time' else 1_750_000_000.,name='Synthetic')
    monkeypatch.setattr(bs,'_patient_event_rows',lambda *a:[row])
    monkeypatch.setattr(bs,'_resolve_event_channel',lambda *a,**kw:None if case=='no_channel' else 'ZERO_THREE_LEFT')
    assert len(getattr(bs,which)('synthetic'))==(1 if case.startswith('valid') else 0)


def test_matrix_signature_changes_with_event_metadata_even_if_uid_and_hash_do_not(monkeypatch):
    from modules.Biomarkers import bravo_service as bs
    metadata={'HemisphereLocationDef.Left':{'Frequency':[0,1,2],'FFTBinData':[1,2,3],
              'SenseID':'SensingElectrodeConfigDef.ZERO_AND_THREE','SenseIDStatus':'resolved'}}
    class EventRows:
        def values_list(self,*fields):
            assert fields==('uid','hashed','metadata')
            return [('synthetic-uid','unchanged-source-hash',metadata)]
    monkeypatch.setattr(bs,'_recording_rows_for_psd',lambda *a:[])
    monkeypatch.setattr(bs.models.Participant,'find',lambda **kw:object())
    monkeypatch.setattr(bs.models.SourceFile,'find_all',lambda **kw:[object()])
    monkeypatch.setattr(bs,'_patient_event_rows',lambda *a:EventRows())
    first=bs._psd_matrix_signature_orm('synthetic')[0]
    block=metadata['HemisphereLocationDef.Left']
    block.update(SenseID='',SenseIDStatus='ambiguous',SenseIDConflict=True)
    ambiguous=bs._psd_matrix_signature_orm('synthetic')[0]
    assert ambiguous!=first
    assert bs._psd_matrix_signature_orm('synthetic')[0]==ambiguous
    block['FFTBinData'][1]=4
    assert bs._psd_matrix_signature_orm('synthetic')[0]!=ambiguous
