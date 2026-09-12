"""Track G step 1: the joined table and its fingerprint accept the calibrated frame.

Since 2026-09-05 `evidence_inputs` returns one row per three-second tile with one column per band
(`band_lsb_<centre>`), already on the device's scale, and no per-bin spectrum. The join and its
content fingerprint still assumed the older one-spectrum-per-row frame, so the deployment report
raised on every candidate and the evidence triangle showed "not estimated". These tests pin the
calibrated path: power read from the band's own column, the tile-quality gate applied, the
fingerprint hashing every band column, and the pipeline running end to end on such a frame.
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
    assert AD.calibrated_centres(pd.DataFrame({"t": [1.0], "log_psd": [[1.0]], "freqs": [[1.0]]})) == ()
    assert AD.calibrated_centres(None) == ()


def test_power_is_read_from_the_bands_own_column_and_nothing_is_integrated():
    f = _cal_frame(n=10)
    T = AD.joined_table(f, _epochs(), centers=(26.5, 8.5))
    assert set(T["center_hz"].unique()) == {26.5, 8.5}
    row = T[(T.channel == "ZERO_TWO_LEFT") & (T.center_hz == 26.5)].sort_values("t")
    src = f[f.channel == "ZERO_TWO_LEFT"].sort_values("t")
    assert np.array_equal(row["power_linear"].to_numpy(), src["band_lsb_26.5"].to_numpy())
    assert np.allclose(row["power_log_of_linear"].to_numpy(), 10 * np.log10(src["band_lsb_26.5"].to_numpy()))
    assert row["power_mean_of_log"].isna().all(), "no per-bin spectrum, so no mean of the log"
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
