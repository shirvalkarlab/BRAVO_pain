"""The modelled LSB at every standard band centre of a contact, worked out once and saved (the PI,
2026-10-04, plan item 6, decision 433). The deployment summary and the band-power panel each worked
out the modelled LSB at their band's centre (about 2 s each: grouping the recordings by contact, then
an FFT of every 1 s window of every trace). The FFT does not depend on the centre, so one pass
gives every centre; the per-centre sums are kept separate, as the one-centre path does them, so
every value is identical to it (a matrix product over all centres at once rounds differently:
340 of 1,352 live values differed). The table depends on the recordings alone (no pain rating) and
is saved under the recording set's identity and the code's fingerprint.

Values: each centre's numbers equal the one-centre path's exactly; a second centre on the same
contact is read from the saved table without working anything out; a centre not on the table, or
no recordings, is worked out directly; a new recording set builds a new table.

Merged here 2026-10-05: test_modeled_lsb_only_when_needed.py.
"""
import datetime
import os
import shutil
import tempfile
import numpy as np
from modules.Biomarkers.routines import analytics, availability as av
T0 = datetime.datetime(2025, 8, 29, 12, 0, 0).timestamp()


def _td_rec(channel, centre, fs=250.0, secs=30, seed=0, start=T0):
    rng = np.random.default_rng(seed)
    n = int(fs * secs)
    t = np.arange(n) / fs
    sig = 8.0 * np.sin(2 * np.pi * centre * t) + rng.normal(0, 2.0, n)
    return {"ChannelNames": [channel], "Data": sig[:, None], "SamplingRate": fs, "StartTime": start}


def test_each_centre_apart_equals_the_one_centre_path_exactly():
    rng = np.random.default_rng(7)
    centres = np.arange(2.5, 100.0, 1.0)
    for n in (250, 251, 1000, 7777, 25000):
        x = rng.normal(0, 3.0, n)
        each = analytics.td_transform_band_power(x, 250.0, centres, half_hz=2.5, each_center=True)
        one = np.asarray([analytics.td_transform_band_power(x, 250.0, float(c), half_hz=2.5)
                          for c in centres])
        assert np.array_equal(each, one, equal_nan=True)
    short = analytics.td_transform_band_power(rng.normal(0, 1, 100), 250.0, centres, each_center=True)
    assert short.shape == centres.shape and np.isnan(short).all()


def test_table_values_equal_the_one_centre_path_exactly():
    recs = [_td_rec("ZERO_THREE_LEFT", 20.0, seed=s, start=T0 + 60 * s) for s in range(4)]
    recs.append(_td_rec("ZERO_THREE_RIGHT", 12.0, seed=9))
    idx = av.channel_index(td_recordings=recs)
    centres = np.arange(2.5, 100.0, 1.0)
    table = av.modeled_lsb_by_centre("ZERO_THREE_LEFT", centres, index=idx, half_hz=2.5)
    assert sorted(table) == [float(c) for c in centres]
    for c in centres:
        ref = av.modeled_lsb_at_center("ZERO_THREE_LEFT", float(c), index=idx, half_hz=2.5)
        assert np.array_equal(table[float(c)], ref)
    assert table[19.5].size == 4


class _Service:
    """The service's saved table, in a sandbox store, with the recordings and their identity stubbed."""

    def __init__(self, recs, identity="set-1"):
        from modules.Biomarkers import bravo_service as bs
        from modules.CacheStore import store as st, ledger as lg
        self.bs, self.st, self.lg = bs, st, lg
        self.recs, self.identity, self.builds = recs, identity, 0

    def __enter__(self):
        bs, st, lg = self.bs, self.st, self.lg
        self.tmp = tempfile.mkdtemp(prefix="mlsb_")
        self.saved = (st.DIR_OVERRIDE, lg.ENABLED, bs._recording_set_identity, av.modeled_lsb_by_centre)
        st.DIR_OVERRIDE, lg.ENABLED = self.tmp, False
        bs._recording_set_identity = lambda uid: self.identity
        real = self.saved[3]

        def counted(*a, **k):
            self.builds += 1
            return real(*a, **k)
        av.modeled_lsb_by_centre = counted
        return self

    def values(self, centre, half=2.5, recs=None):
        return self.bs._modeled_lsb_values("u-test", "ZERO_THREE_LEFT", centre,
                                           self.recs if recs is None else recs, half)

    def __exit__(self, *exc):
        bs, st, lg = self.bs, self.st, self.lg
        st.DIR_OVERRIDE, lg.ENABLED, bs._recording_set_identity, av.modeled_lsb_by_centre = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


def test_second_centre_on_a_contact_is_read_from_the_saved_table():
    recs = [_td_rec("ZERO_THREE_LEFT", 20.0, seed=s, start=T0 + 60 * s) for s in range(3)]
    idx = av.channel_index(td_recordings=recs)
    with _Service(recs) as sv:
        a = sv.values(20.5)
        b = sv.values(23.5)
        assert sv.builds == 1
        assert os.listdir(sv.tmp)
    assert np.array_equal(a, av.modeled_lsb_at_center("ZERO_THREE_LEFT", 20.5, index=idx, half_hz=2.5))
    assert np.array_equal(b, av.modeled_lsb_at_center("ZERO_THREE_LEFT", 23.5, index=idx, half_hz=2.5))


def test_off_table_centre_and_no_recordings_are_worked_out_directly():
    recs = [_td_rec("ZERO_THREE_LEFT", 20.0, seed=1)]
    idx = av.channel_index(td_recordings=recs)
    with _Service(recs) as sv:
        off = sv.values(20.25)
        none = sv.values(20.5, recs=[])
        assert sv.builds == 0
    assert np.array_equal(off, av.modeled_lsb_at_center("ZERO_THREE_LEFT", 20.25, index=idx, half_hz=2.5))
    assert none.size == 0


def test_a_new_recording_set_builds_a_new_table():
    recs = [_td_rec("ZERO_THREE_LEFT", 20.0, seed=1)]
    with _Service(recs) as sv:
        sv.values(20.5)
        sv.identity = "set-2"
        sv.values(20.5)
        assert sv.builds == 2


# --------------------------------------------------------------------------------------------------
# merged from test_modeled_lsb_only_when_needed.py
# The modelled LSB is worked out only when the device has no measured threshold for the band (the
# PI, 2026-10-04: "check if anything reads it", decision 434). Both the deployment summary and the
# band-power panel read it in one place: the estimated threshold, used only when the device sensed
# the band fewer than 20 times. On RCS08 the device sensed 46 of the 132 grid bands that often, and
# for those the modelled values were worked out and thrown away.
#
# Values: with 30 device-sensed values in the band, neither answer asks for the modelled values and
# the threshold is the measured one; with all 30 outside the band, each asks once and the threshold is estimated.


import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))
from Biomarkers.tests.test_summary_auc_current_taken_out import (  # noqa: E402
    CH, _record, _django_available)


def _run(build_name, n_native):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
    import django
    django.setup()
    from Biomarkers import bravo_service as bs
    from Biomarkers.routines import stim_current as sc
    detail, stream = _record("own")
    core = {"available": True, "participant_uid": "u", "Participant": None, "channel": CH,
            "center_hz": 24.5, "band_width_hz": 5.0, "pooled": detail, "stim_series": None,
            "glmer": {}, "stim": {}, "verdict": None, "label_metric": "nrs",
            "composite_parts": None, "label_strategy": "tertile", "low_pct": 33.3333,
            "high_pct": 66.6667, "match_direction": "prior", "clinic_sheet_ratings": None}
    rng = np.random.default_rng(3)
    # 30 device-sensed values, all in the band or (n_native=0) all at 60 Hz, outside it
    hz = [24.5] * n_native + [60.0] * (30 - n_native)
    series = {CH: {"y": list(rng.uniform(100, 900, 30)), "center_hz": hz,
                   "source": ["chronic"] * 30, "modeled": [False] * 30, "t": list(range(30))}}
    asked = []
    names = ("_validate_band_core", "_sign_off_recordings", "_calibration_scatter",
             "_modeled_lsb_values", "_programmed_adaptive_thresholds")
    saved = {k: getattr(bs, k) for k in names if hasattr(bs, k)}
    saved_sc, saved_lsb = sc.settings_stream_for, bs.availability.lsb_series
    try:
        bs._validate_band_core = lambda rd: dict(core)
        bs._sign_off_recordings = lambda uid: ([], [], [], [])
        bs._calibration_scatter = lambda uid: None
        bs._programmed_adaptive_thresholds = lambda p: {}
        bs.availability.lsb_series = lambda *a, **k: series

        def modeled(*a, **k):
            asked.append(a)
            return np.linspace(200.0, 800.0, 40)
        bs._modeled_lsb_values = modeled
        sc.settings_stream_for = lambda uid: stream
        out = getattr(bs, build_name)({"ParticipantId": "u", "Channel": CH, "CenterHz": 24.5,
                                       "BandWidthHz": 5.0, "NBoot": 200, "Cutpoint": 0.0})
    finally:
        for k, v in saved.items():
            setattr(bs, k, v)
        sc.settings_stream_for, bs.availability.lsb_series = saved_sc, saved_lsb
    return out, asked


def _threshold(build_name, out):
    if build_name == "_band_lsb_and_power_build":
        return out["threshold_lsb"]
    return out


def test_summary_skips_modelled_values_when_the_device_measured_the_band():
    if not _django_available():
        return
    out, asked = _run("_deployment_summary_build", 30)
    assert out.get("available") is True, out
    assert asked == []
    out, asked = _run("_deployment_summary_build", 0)
    assert len(asked) == 1


def test_band_power_skips_modelled_values_when_the_device_measured_the_band():
    if not _django_available():
        return
    out, asked = _run("_band_lsb_and_power_build", 30)
    assert asked == [] and out["threshold_lsb"]["estimated"] is False, out.get("threshold_lsb")
    out, asked = _run("_band_lsb_and_power_build", 0)
    assert len(asked) == 1 and out["threshold_lsb"]["estimated"] is True, out.get("threshold_lsb")
