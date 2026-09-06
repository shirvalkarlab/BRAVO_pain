"""Window selection must preserve chronological provenance and observed exclusions."""
import numpy as np
import pandas as pd
import pytest
from StimOptimizer.routines import lfp_evidence as EV
from Biomarkers.routines import analytics as AN


def test_validation_window_is_record_anchored_and_optional():
    times = ['2026-01-01', '2026-01-15', '2026-01-22', '2026-02-05']
    finite = np.array([True, False, True, True])
    eras, mask, weeks, dropped, before = AN._validation_week_mask(times, finite, 3)
    assert eras.tolist() == [0, 2, 3, 5]
    assert mask.tolist() == [False, False, True, True]
    assert (weeks, dropped, before) == (3, 1, 3)
    assert AN._validation_week_mask(times, finite, None)[1].tolist() == finite.tolist()
    assert AN._validation_week_mask(times, finite, 9)[1].sum() == 0


@pytest.mark.parametrize('recent', [None, 0, 5])
def test_recent_eras_handles_empty_surviving_observations(recent):
    empty = pd.DataFrame(columns=['era', 't'])
    assert EV._recent_response_eras(empty, EV.EvidenceAudit(channel='test', hemisphere='Left', rate_hz=55.), recent).empty


def test_recent_era_order_follows_timestamps_and_labels_are_explicit_fallback():
    frame = pd.DataFrame({'era': ['z', 'a', 'b'], 't': [1, 3, 2]})
    audit = EV.EvidenceAudit(channel='test', hemisphere='Left', rate_hz=55.)
    out = EV._recent_response_eras(frame, audit, 2)
    assert out.era.tolist() == ['a', 'b']
    assert audit.n_dropped_old_eras == 1 and audit.recent_eras_kept == ('b', 'a')
    audit = EV.EvidenceAudit(channel='test', hemisphere='Left', rate_hz=55.)
    out = EV._recent_response_eras(frame.drop(columns=['t']), audit, 1)
    assert out.era.tolist() == ['z'] and 'LABEL' in audit.era_order_source
