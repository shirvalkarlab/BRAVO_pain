"""Synthetic current-gap and cache integration boundaries for the source update."""
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd

from ClosedLoopDeployment import adapter as AD


def test_simulation_current_gaps_and_epoch_fallback_preserve_observed_counts(monkeypatch):
    from ClosedLoopDeployment import three_source_response as TSR
    t = np.array([0., 1., 2., 3., 8., 9., 10., 11.])
    entry = {'centres_hz': [15.5], 'td': {'t': t, 'lsb': np.full((8,1),20.),
                                       'ok': [True]*7+[False], 'saturated': [False]*6+[True,False]}}
    cache = {'ZERO_THREE_LEFT': entry}
    service = SimpleNamespace(_load_recordings=lambda *a: [], POWERDOMAIN_TYPES=(), TIMEDOMAIN_TYPES=(),
                              AVAILABILITY_PSD_TYPES=(), _derive_chan_order=lambda td: [],
                              _build_sensing_config_index=lambda td: {}, _event_psd_lsb_blocks=lambda *a, **k: [],
                              _montage_psd_lsb_blocks=lambda *a, **k: [], _raw_lsb_cache_cached=lambda *a, **k: cache)
    import Biomarkers
    monkeypatch.setattr(Biomarkers, 'bravo_service', service, raising=False)
    monkeypatch.setitem(sys.modules,'Biomarkers.bravo_service',service)
    blocks = [dict(t=np.array([0.]),mA={'ZERO_THREE_LEFT':np.array([1.])}),
              dict(t=np.array([20.,21.]),mA={'ZERO_THREE_LEFT':np.array([1.,1.])}),
              dict(t=np.array([0.,1.,2.,8.,9.,10.]),mA={'ZERO_THREE_LEFT':np.array([1.,1.,1.,2.,2.,2.])})]
    monkeypatch.setattr(TSR,'read_device_current',lambda p:dict(blocks=blocks))
    args = dict(contact='ZERO_THREE_LEFT',centre_hz=15.5,hemisphere='Left')
    out = AD.simulation_inputs_for_participant('synthetic',**args)
    assert out['n_from_device_current'] == 6
    assert out['n_dropped_no_amplitude'] == 2
    assert np.array_equal(out['t'],[0,1,2,8,9,10])
    assert np.array_equal(out['amp_obs'],[1,1,1,2,2,2])
    assert np.isnan(out['power'][-1])
    epochs = pd.DataFrame({'t_start':pd.to_datetime([0.],unit='s'), 't_end':pd.to_datetime([20.],unit='s'),
                           AD.canonical_amp_col('Left'):[3.]})
    out = AD.simulation_inputs_for_participant('synthetic',**args,epochs=epochs,
                                              loaded=dict(cache=cache,power=[],td=[],psd=[]))
    assert out['n_from_epochs'] == 2 and out['n_dropped_no_amplitude'] == 0
    assert out['amp_obs'][3] == 3.
    # If no settings column can be resolved, unknown observations remain withheld.
    out = AD.simulation_inputs_for_participant('synthetic',**args,epochs=pd.DataFrame({'other':[1]}))
    assert out['n_dropped_no_amplitude'] == 2
    for bad_cache in ({}, {'ZERO_THREE_LEFT':{'td':{'t':t,'lsb':np.ones((8,1))},'centres_hz':[]}}):
        out = AD.simulation_inputs_for_participant('synthetic',**args,loaded=dict(cache=bad_cache))
        assert out['absent_reason']
    entry['td'].pop('ok');entry['td'].pop('saturated')
    assert AD.simulation_inputs_for_participant('synthetic',**args)['n_unusable_pieces'] == 0
