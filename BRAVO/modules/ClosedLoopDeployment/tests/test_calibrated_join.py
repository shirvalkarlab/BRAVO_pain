"""Track G step 1: the joined table and its fingerprint accept the calibrated frame.

Since 2026-09-05 `evidence_inputs` returns one row per three-second tile with one column per band
(`band_lsb_<centre>`), already on the device's scale, and no per-bin spectrum. The join and its
content fingerprint still assumed the older one-spectrum-per-row frame, so the deployment report
raised on every candidate and the evidence triangle showed "not estimated". These tests pin the
calibrated path: power read from the band's own column, the tile-quality gate applied, the
fingerprint hashing every band column, and the pipeline running end to end on such a frame.

Merged here 2026-10-05: test_pain_joined_on_own_setting.py, test_joined_table_one_band.py.
"""
import numpy as np
import pandas as pd

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment import pipeline as PL

T0 = 1_750_000_000.0
CENTRES = tuple(float(c) for c in np.arange(8.5, 30.0, 1.0))


def _cal_frame(n=40, channels=("ZERO_TWO_LEFT", "ONE_THREE_LEFT"), seed=0):
    rng = np.random.default_rng(seed)
    blocks = []
    for ch in channels:
        cols = {"t": T0 + 3.0 * np.arange(n), "channel": [ch] * n, "source": ["tiles"] * n,
                "family": ["td"] * n, "tile_ok": np.ones(n, bool), "tile_saturated": np.zeros(n, bool),
                "band_half_hz": np.full(n, 2.5), "tile_window_s": np.full(n, 3.0)}
        for c in CENTRES:
            cols[f"band_lsb_{c:g}"] = rng.uniform(100.0, 900.0, n)
            cols[f"band_native_{c:g}"] = np.zeros(n, bool)
        blocks.append(pd.DataFrame(cols))
    return pd.concat(blocks, ignore_index=True)


def _epochs():
    t0 = pd.Timestamp(T0, unit="s", tz="UTC")
    return pd.DataFrame({"t_start": [t0, t0 + pd.Timedelta(seconds=60)],
                         "t_end": [t0 + pd.Timedelta(seconds=60), t0 + pd.Timedelta(seconds=200)],
                         "amp_mA_Left": [1.5, 2.5], "amp_mA_Right": [np.nan, np.nan],
                         "freq_hz": [55.0, 55.0], "pw_us_Left": [60.0, 60.0],
                         "dur_h": [1 / 60, 140 / 3600], "epoch": [1.0, 2.0]})


def test_the_calibrated_frame_is_recognised_by_its_own_columns():
    assert AD.calibrated_centres(_cal_frame()) == CENTRES
    assert AD.calibrated_centres(pd.DataFrame({"t": [1.0], "psd": [[1.0]], "freqs": [[1.0]]})) == ()
    assert AD.calibrated_centres(None) == ()


def test_power_is_read_from_the_bands_own_column_and_nothing_is_integrated():
    f = _cal_frame(n=10)
    T = AD.joined_table(f, _epochs(), centers=(26.5, 8.5))
    assert set(T["center_hz"].unique()) == {26.5, 8.5}
    row = T[(T.channel == "ZERO_TWO_LEFT") & (T.center_hz == 26.5)].sort_values("t")
    src = f[f.channel == "ZERO_TWO_LEFT"].sort_values("t")
    assert np.array_equal(row["power_linear"].to_numpy(), src["band_lsb_26.5"].to_numpy())
    assert "power_log_of_linear" not in row.columns and "power_mean_of_log" not in row.columns  # decision 202
    assert (row["band_width_hz"] == 5.0).all() and (row["device_native"] == False).all()
    assert T.attrs["band_power_source"] == "calibrated"


def test_a_centre_the_frame_does_not_carry_yields_no_rows_never_a_neighbour():
    T = AD.joined_table(_cal_frame(n=5), _epochs(), centers=(26.4, 26.5))
    assert set(T["center_hz"].unique()) == {26.5}


def test_the_tile_quality_gate_leaves_out_unusable_and_railed_tiles():
    f = _cal_frame(n=10, channels=("ZERO_TWO_LEFT",))
    f.loc[2, "tile_ok"] = False
    f.loc[5, "tile_saturated"] = True
    T = AD.joined_table(f, _epochs(), centers=(26.5,))
    assert len(T) == 8 and T.attrs["rows_dropped_by_tile_gate"] == 2
    assert not np.isin(f.loc[[2, 5], "t"].to_numpy(), T["t"].to_numpy()).any()


def test_the_epoch_context_and_current_are_joined_onto_every_tile_row():
    T = AD.joined_table(_cal_frame(n=70, channels=("ZERO_TWO_LEFT",)), _epochs(), centers=(26.5,))
    in_first = T[T.setting_epoch == 0]
    in_second = T[T.setting_epoch == 1]
    assert (in_first["amp_mA_Left"] == 1.5).all() and (in_second["amp_mA_Left"] == 2.5).all()
    assert (in_first["freq_hz"] == 55.0).all()
    assert (T.setting_epoch == -1).sum() > 0, "tiles after the last epoch belong to no epoch"
    assert T.loc[T.setting_epoch == -1, "amp_mA_Left"].isna().all()
    assert "era_Left" in T.columns


def test_the_fingerprint_hashes_every_band_column_so_one_changed_power_is_a_new_key():
    f, e = _cal_frame(n=6), _epochs()
    a = AD._joined_signature(f, e, (26.5,), 5.0)
    g = f.copy()
    g.loc[3, "band_lsb_12.5"] = g.loc[3, "band_lsb_12.5"] + 1.0     # a band the join was not asked for
    assert AD._joined_signature(g, e, (26.5,), 5.0) != a
    h = f.copy()
    h.loc[3, "tile_ok"] = False
    assert AD._joined_signature(h, e, (26.5,), 5.0) != a


def test_the_pipeline_runs_end_to_end_on_a_calibrated_frame_and_returns_three_edges():
    f = _cal_frame(n=120, channels=("ZERO_TWO_LEFT",))
    e = _epochs()
    rep = PL.run("P", psd_frame=f, epochs=e, design_matrix=None,
                 candidates=[{"channel": "ZERO_TWO_LEFT", "center_hz": 8.5, "band_width_hz": 5.0}],
                 hemisphere="Left", power_scale="power_linear")
    d = AD.report_to_dict(rep)
    assert d["available"] is True
    assert set(d["edges"]) >= {"E1", "E2", "E3"}, "all three edges are reported, resolved or not"
    assert d["manifest"]["n_table_rows"] > 0

# ------------------------------------------------------------------------------------------------
# Each chunk carries the pain ratings of its own setting (from test_pain_joined_on_own_setting.py,
# merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# Each 3-second chunk carries the pain ratings of the setting it was RECORDED under.
#
# The Closed-Loop joined table (one row per chunk and band) attaches the per-setting pain ratings
# the band-to-pain reading (E2) and its current-removed version read. The chunk knows its setting as
# a POSITION in the settings table (0, 1, 2, ...); the ratings are filed under the settings table's
# own NUMBER, which `StimOptimizer.adapter.exposure_epochs` starts at 1. The join matched one against
# the other, so every chunk carried the ratings of the setting before its own (found 2026-09-25,
# checked against the recording and report times on RCS08). These tests decide "own setting" from
# the timestamps, never from a column name, and hold the two neighbouring settings' ratings far
# apart so a one-step slip cannot pass.
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


# ------------------------------------------------------------------------------------------------
# The joined table built for the chosen contact and band only (from test_joined_table_one_band.py,
# merged 2026-10-05)
# ------------------------------------------------------------------------------------------------
# The joined table is built for the chosen contact and band only (the PI, 2026-10-04, decision 419).
#
# The report built one row per 3 s chunk for every contact and every band (about 1.6 million rows on
# RCS08, 8.5 s of the 40 s report), and every reader then took the rows of one contact at one band.
# Built for that contact and band alone, the rows -- and every value read from them -- are the same;
# the manifest's row count still states the size of the whole table, so no field of the report moves.
try:
    from modules.ClosedLoopDeployment import adapter as AD_M, pipeline as PL_M, edges as E_M
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import adapter as AD_M, pipeline as PL_M, edges as E_M

from ClosedLoopDeployment.tests.test_chunk_rule_on_e2_and_threshold import (
    _cache, _epochs as _chunk_epochs, _pro, CAND, FC)
from StimOptimizer.routines import lfp_evidence as EV


def _two_contact_frame():
    a, b = _cache(seed=0), _cache(seed=1)
    b = dict(b, channel="ONE_THREE_LEFT")
    return EV.frame_from_lsb_cache({"ZERO_TWO_LEFT": a, "ONE_THREE_LEFT": b})


def test_the_one_band_table_is_the_full_tables_rows_for_that_band():
    f, e = _two_contact_frame(), _chunk_epochs()
    full = AD_M.joined_table(f, e, centers=(8.5, 12.5, FC), pro_frame=_pro())
    one = AD_M.joined_table(f, e, centers=(FC,), pro_frame=_pro(), channels=("ZERO_TWO_LEFT",))
    want = full[(full.channel == "ZERO_TWO_LEFT") & np.isclose(full.center_hz, FC)].reset_index(drop=True)
    assert list(one.columns) == list(want.columns)
    pd.testing.assert_frame_equal(one.reset_index(drop=True), want, check_exact=True)


def test_the_row_count_of_the_whole_table_is_kept():
    f, e = _two_contact_frame(), _chunk_epochs()
    cen = (8.5, 12.5, FC)
    full = AD_M.joined_table(f, e, centers=cen, pro_frame=_pro())
    one = AD_M.joined_table(f, e, centers=cen, pro_frame=_pro(), channels=("ZERO_TWO_LEFT",),
                          only_center=FC)
    assert one.attrs["n_rows_all_contacts_bands"] == len(full)
    assert set(one.channel) == {"ZERO_TWO_LEFT"} and set(one.center_hz) == {FC}


def test_the_report_reads_the_same_answers_and_states_the_same_row_count():
    f, e = _two_contact_frame(), _chunk_epochs()
    rep = PL_M.run("P", psd_frame=f, epochs=e, pro_frame=_pro(), candidates=CAND, hemisphere="Left")
    cen = tuple(sorted(set(AD_M.DEFAULT_BAND_CENTERS_HZ) | {FC}))
    full = AD_M.joined_table(f, e, centers=cen, pro_frame=_pro())
    assert rep.manifest["n_table_rows"] == len(full)
    e1 = E_M.actuation_edge(full, channel="ZERO_TWO_LEFT", center_hz=FC, hemisphere="Left")
    e2 = E_M.state_edge(full, channel="ZERO_TWO_LEFT", center_hz=FC, outcome="nrs",
                      adjust_for_column="amp_mA_Left")
    for got, want in ((rep.edges["E1"], e1), (rep.edges["E2"], e2)):
        assert (got.estimate, got.ci, got.n, got.note) == (want.estimate, want.ci, want.n, want.note)
