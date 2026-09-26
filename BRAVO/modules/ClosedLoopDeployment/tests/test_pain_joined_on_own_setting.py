"""Each 3-second chunk carries the pain ratings of the setting it was RECORDED under.

The Closed-Loop joined table (one row per chunk and band) attaches the per-setting pain ratings
the band-to-pain reading (E2) and its current-removed version read. The chunk knows its setting as
a POSITION in the settings table (0, 1, 2, ...); the ratings are filed under the settings table's
own NUMBER, which `StimOptimizer.adapter.exposure_epochs` starts at 1. The join matched one against
the other, so every chunk carried the ratings of the setting before its own (found 2026-09-25,
checked against the recording and report times on RCS08). These tests decide "own setting" from
the timestamps, never from a column name, and hold the two neighbouring settings' ratings far
apart so a one-step slip cannot pass.
"""
import numpy as np
import pandas as pd

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment.tests.test_calibrated_join import _cal_frame

try:
    from StimOptimizer import adapter as SA
except ImportError:                                                  # pragma: no cover
    from modules.StimOptimizer import adapter as SA

T0 = 1_750_000_000.0
RATINGS = {1.0: (2.0, 10.0), 2.0: (5.0, 50.0), 3.0: (9.0, 90.0)}    # label -> (nrs, left_leg_vas)


def _epochs3():
    """Three one-minute settings, numbered as `exposure_epochs` numbers them (from 1)."""
    t0 = pd.Timestamp(T0, unit="s", tz="UTC")
    starts = [t0 + pd.Timedelta(seconds=60 * k) for k in range(3)]
    return pd.DataFrame({"t_start": starts, "t_end": [s + pd.Timedelta(seconds=60) for s in starts],
                         "amp_mA_Left": [1.0, 2.0, 3.0], "amp_mA_Right": [np.nan] * 3,
                         "freq_hz": [55.0] * 3, "pw_us_Left": [60.0] * 3, "dur_h": [1 / 60] * 3,
                         "epoch": [1.0, 2.0, 3.0], "open_ended": [False, False, False]})


def _pain_frame():
    """What `pipeline.run` builds from the design matrix: one row per setting number."""
    return pd.DataFrame({"epoch": list(RATINGS), "report_id": [f"{k:g}" for k in RATINGS],
                         "nrs": [v[0] for v in RATINGS.values()],
                         "vas": [10.0 * v[0] for v in RATINGS.values()],
                         "left_leg_vas": [v[1] for v in RATINGS.values()]})


def _own_label_by_time(t_s, epochs):
    s = pd.to_datetime(epochs["t_start"], utc=True).map(lambda x: x.timestamp()).to_numpy()
    e = pd.to_datetime(epochs["t_end"], utc=True).map(lambda x: x.timestamp()).to_numpy()
    out = np.full(len(t_s), np.nan)
    for k in range(len(epochs)):
        m = (t_s >= s[k]) & (t_s < e[k])
        out[m] = float(epochs["epoch"].iloc[k])
    return out


def _check_every_chunk_carries_its_own_settings_ratings(T, epochs):
    own = _own_label_by_time(T["t"].to_numpy(dtype=float), epochs)
    assert np.isfinite(own).all(), "the fixture puts every chunk inside a setting"
    want_nrs = np.array([RATINGS[x][0] for x in own])
    want_leg = np.array([RATINGS[x][1] for x in own])
    got_nrs = T["nrs"].to_numpy(dtype=float)
    got_leg = T["left_leg_vas"].to_numpy(dtype=float)
    wrong = int((~np.isclose(got_nrs, want_nrs) | np.isnan(got_nrs)).sum())
    assert wrong == 0, (f"{wrong} of {len(T)} chunks carry another setting's NRS; "
                        f"by own setting {dict(zip(own, got_nrs))}")
    assert np.allclose(got_leg, want_leg), dict(zip(own, got_leg))
    assert (pd.to_numeric(T["report_id"]).to_numpy(dtype=float) == own).all()


def test_the_numbering_the_join_must_match_is_the_settings_tables_own_from_one():
    """The premise, pinned on the real function: `exposure_epochs` numbers settings from 1, so a
    setting's number is its position plus one, never its position."""
    t0 = pd.Timestamp(T0, unit="s", tz="UTC")
    rows = []
    for k, amp in enumerate((1.0, 2.0, 3.0)):
        for hemi in ("Left", "Right"):
            rows.append({"t": t0 + pd.Timedelta(seconds=60 * k), "hemi": hemi, "amp": amp,
                         "pw": 60.0, "rate": 55.0, "cathode": "C+2-"})
    ep = SA.exposure_epochs(pd.DataFrame(rows))
    assert ep["epoch"].tolist() == [1.0, 2.0, 3.0], ep["epoch"].tolist()


def test_calibrated_chunks_carry_their_own_settings_ratings_not_the_previous_ones():
    f = _cal_frame(n=60, channels=("ONE_THREE_LEFT",))            # 3 s apart over 180 s
    T = AD.joined_table(f, _epochs3(), centers=(24.5,), pro_frame=_pain_frame())
    assert len(T) == 60
    _check_every_chunk_carries_its_own_settings_ratings(T, _epochs3())


def test_spectrum_frame_chunks_carry_their_own_settings_ratings_too():
    fr = np.arange(8.0, 31.0, 1.0)
    f = pd.DataFrame([{"t": T0 + 3.0 * k, "channel": "ONE_THREE_LEFT", "source": "td",
                       "psd": np.sin(fr) + 2.0 + k, "freqs": fr} for k in range(60)])
    T = AD.joined_table(f, _epochs3(), centers=(24.5,), pro_frame=_pain_frame())
    assert len(T) == 60
    _check_every_chunk_carries_its_own_settings_ratings(T, _epochs3())


def test_a_chunk_in_no_setting_carries_no_rating_and_a_setting_with_none_gives_none():
    f = _cal_frame(n=70, channels=("ONE_THREE_LEFT",))            # the last 10 fall after 180 s
    pro = _pain_frame().iloc[[0, 2]]                                 # setting 2 has no ratings
    T = AD.joined_table(f, _epochs3(), centers=(24.5,), pro_frame=pro)
    t = T["t"].to_numpy(dtype=float)
    after = t >= T0 + 180.0
    second = (t >= T0 + 60.0) & (t < T0 + 120.0)
    assert after.sum() == 10 and T.loc[after, "nrs"].isna().all()
    assert T.loc[second, "nrs"].isna().all(), "setting 2 was rated by no one"
    assert (T.loc[t < T0 + 60.0, "nrs"] == 2.0).all()
    assert (T.loc[(t >= T0 + 120.0) & ~after, "nrs"] == 9.0).all()
    assert len(T) == 70, "attaching ratings never adds or drops a chunk"
