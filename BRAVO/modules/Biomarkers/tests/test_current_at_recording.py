"""The current taken out of the heat map is the current the band power was MEASURED under (decision
483; the PI, 2026-10-18: "do all", change 1). Until 483 it was the current in force when the pain
report was filed, which on a report whose 15-minute window straddles a settings change is not the
current any of its recording ran under. Now: the median, over the report's own pieces of recording
(its TD pieces, or its device PSD snapshots where it has no TD), of the current in force at each.

Run:  python3 modules/Biomarkers/tests/test_current_at_recording.py   (or through either suite)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import availability as av, stim_current as sc
except ImportError:                                            # pragma: no cover - host spelling
    from Biomarkers.routines import availability as av, stim_current as sc

CENTERS = [8.5, 12.5]
T0 = 1_700_000_000.0


def _row(base):
    return [float(base + j) for j in range(len(CENTERS))]


def _cache(td_t, psd_t=()):
    nC = len(CENTERS)
    td_t = [float(t) for t in td_t]
    return {"channel": "ONE_THREE_LEFT", "centers_hz": [float(c) for c in CENTERS],
            "window_s": 3.0, "band_half_hz": 2.5,
            "td": {"t": td_t, "lsb": [_row(100.0) for _ in td_t], "saturated": [False] * len(td_t),
                   "source": ["constructed"] * len(td_t), "n_finite_s": [3.0] * len(td_t),
                   "ok": [True] * len(td_t)},
            "psd": {"t": [float(t) for t in psd_t], "lsb": [_row(200.0) for _ in psd_t],
                    "calibrated": [[True] * nC] * len(psd_t), "source": ["constructed"] * len(psd_t)},
            "n_td_windows": len(td_t), "n_psd_windows": len(psd_t)}


def _match(pro, cache, lengths=(3.0, 30.0)):
    return av.live_lsb_band_medians_by_length(
        pro, cache, tol_s=900.0, lengths_s=list(lengths), centers_hz=CENTERS,
        band_ceilings=[np.inf] * len(CENTERS), match_direction="prior")


def _stream(changes, hemi="Left"):
    """``changes`` = [(epoch s, mA), ...] on one side."""
    return {"t_s": np.array([t for t, _ in changes], float),
            "hemi": np.array([hemi] * len(changes), dtype=object),
            "amp_mA": np.array([a for _, a in changes], float), "store_key": "constructed",
            "n_rows": len(changes)}


def test_the_matcher_hands_back_each_reports_own_pieces():
    # report at T0+600 with TD pieces before it (prior matching); a second report with nothing
    td = [T0 + 300.0 + 3.0 * k for k in range(10)]
    _p, info, _s = _match([T0 + 600.0, T0 + 50_000.0], _cache(td))
    rec = info["recording_times_s"]
    assert len(rec) == 2
    # the nearest pieces up to the longest length asked for (30 s = 10 pieces of 3 s)
    assert sorted(rec[0]) == sorted(td), rec[0]
    assert rec[1] == []


def test_a_window_straddling_a_change_takes_the_current_at_its_pieces_not_at_the_rating():
    td = [T0 + 300.0 + 3.0 * k for k in range(10)]               # T0+300 .. T0+327
    _p, info, _s = _match([T0 + 600.0], _cache(td))
    stream = _stream([(T0, 1.0), (T0 + 500.0, 3.0)])             # changed after the recording
    at_report = sc.current_in_force_at([T0 + 600.0], stream, hemisphere="Left")
    assert at_report.tolist() == [3.0]
    vals, info2 = sc.current_at_recordings(info["recording_times_s"], stream, hemisphere="Left")
    assert vals.tolist() == [1.0], vals
    assert info2["n_reports_spanning_two_currents"] == 0


def test_the_span_counter_counts_reports_whose_pieces_ran_under_two_currents():
    times = [[T0 + 10.0, T0 + 20.0, T0 + 30.0],                 # 1, 1, 3 mA -> median 1, spans
             [T0 + 40.0, T0 + 50.0],                            # 3, 3 -> 3
             [],                                                # no pieces -> unknown
             [T0 - 100.0]]                                      # before the first setting -> unknown
    stream = _stream([(T0, 1.0), (T0 + 25.0, 3.0)])
    vals, info = sc.current_at_recordings(times, stream, hemisphere="Left")
    assert vals[0] == 1.0 and vals[1] == 3.0
    assert np.isnan(vals[2]) and np.isnan(vals[3])
    assert info["n_reports_spanning_two_currents"] == 1
    assert info["n_reports_without_pieces"] == 1
    # the other side's settings never count (each band is judged on its own side, decision 141)
    vals_r, _ = sc.current_at_recordings(times, stream, hemisphere="Right")
    assert np.isnan(vals_r).all()


def test_the_psd_only_route_uses_the_snapshot_times():
    psd = [T0 + 200.0, T0 + 400.0]
    # 60 s asks for two 30 s snapshots, so both are the report's own; at 30 s only the nearest is
    _p, info, _s = _match([T0 + 600.0], _cache([], psd_t=psd), lengths=(3.0, 60.0))
    assert sorted(info["recording_times_s"][0]) == psd
    stream = _stream([(T0, 1.0), (T0 + 300.0, 2.0), (T0 + 500.0, 4.0)])
    vals, inf = sc.current_at_recordings(info["recording_times_s"], stream, hemisphere="Left")
    assert vals.tolist() == [1.5]                               # median of 1 and 2, never 4
    assert inf["n_reports_spanning_two_currents"] == 1


def test_the_report_level_wrapper_states_where_the_current_was_read():
    sc_settings = sc.settings_stream_for
    try:
        sc.settings_stream_for = lambda uid: _stream([(T0, 1.0), (T0 + 25.0, 3.0)])
        vals, block = sc.current_at_recordings_for_reports(
            "constructed", [[T0 + 10.0, T0 + 30.0, T0 + 31.0], [T0 + 10.0]], channel="ONE_THREE_LEFT")
        assert vals.tolist() == [3.0, 1.0]
        assert block["read_at"] == "recording" and block["available"] is True
        assert block["n_reports_spanning_two_currents"] == 1 and block["hemisphere"] == "Left"
        sc.settings_stream_for = lambda uid: None
        vals, block = sc.current_at_recordings_for_reports(
            "constructed", [[T0 + 10.0]], channel="ONE_THREE_LEFT")
        assert np.isnan(vals).all() and block["available"] is False and block["reason"]
    finally:
        sc.settings_stream_for = sc_settings


def test_the_setting_chooses_and_the_neutral_setting_reads_at_the_report():
    assert sc.CURRENT_READ_AT == "recording"
    sc_settings = sc.settings_stream_for
    keep = sc.CURRENT_READ_AT
    try:
        sc.settings_stream_for = lambda uid: _stream([(T0, 1.0), (T0 + 500.0, 3.0)])
        pro, rec = [T0 + 600.0], [[T0 + 300.0, T0 + 303.0]]
        v, b = sc.covariate_for_reports("constructed", pro, rec, channel="ONE_THREE_LEFT")
        assert v.tolist() == [1.0] and b["read_at"] == "recording"
        sc.CURRENT_READ_AT = "report"
        v, b = sc.covariate_for_reports("constructed", pro, rec, channel="ONE_THREE_LEFT")
        old_v, old_b = sc.current_in_force_for_reports("constructed", pro, channel="ONE_THREE_LEFT")
        assert v.tolist() == old_v.tolist() == [3.0] and b == old_b and "read_at" not in b
    finally:
        sc.settings_stream_for = sc_settings
        sc.CURRENT_READ_AT = keep


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
