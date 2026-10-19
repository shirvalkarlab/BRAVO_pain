"""The chronic log as the main source of band choice (wave 2, C5; the PI, 2026-10-18: "the chronic
log may choose"; `routines/chronic_band_choice.py`).

Held here, on values:
  * each chronic frequency goes on the heat map's nearest band centre only when it is LESS than
    0.5 Hz away (24.41 Hz -> 24.5 Hz; 7.8 Hz -> no centre);
  * readings filed under another contact pair never count for this one (CLAUDE.md rule 13), and
    adding them changes nothing on this pair, field for field;
  * a band the chronic log does not cover (no frequency maps to it, or too few reports matched)
    cannot be labelled "chronic"; it says "no home record at this band" or why it is too thin;
  * a chronic reading's current is its own lead's: after the merge files the right log's copies
    of the left lead's signal under the left lead, the left pair's readings take the LEFT lead's
    current, never the right lead's;
  * the grid's key changes when the chronic recordings change, and does not without the chronic
    choice (the neutral setting);
  * BY DEFAULT each report takes the ONE reading whose 10-minute average covers it (the PI,
    2026-10-19); a reading's time is the start of its 10 minutes, so a report at exactly the next
    reading's time belongs to that next reading only; a report in a gap of the log has no reading
    and is counted; the heat map's matching window does not change the default; the page's
    override ("window") gives the first C5 build's numbers and carries the not-the-default warning,
    and puts the setting in the grid's key.

Run inside the container: python3 _agent_bridge/_snr6_run.py Biomarkers/tests/test_chronic_band_choice.py
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from modules.Biomarkers.routines import chronic_band_choice as CBC      # noqa: E402
from modules.Biomarkers.routines import sweep_settings as SW            # noqa: E402
from modules.DecodeCommon import representation as R                     # noqa: E402

T0 = 1_760_000_000.0
CENTRES = [8.5 + k for k in range(22)]


def _rec(t, lfp, amp, side="Left", contacts=None, freq=24.41, lead=None):
    t = np.asarray(t, dtype=float)
    rec = {"ChannelNames": [f"{side}Hemisphere LFP", f"{side}Hemisphere Amplitude"],
           "Data": np.column_stack([np.asarray(lfp, float), np.asarray(amp, float)]),
           "Time": t, "SamplingRate": -1, "RecordingType": "MedtronicChronicBrainSense",
           "FreqScheduleHz": [[float(t[0]) - 1.0, freq]],
           "ContactSchedule": contacts or [[float(t[0]) - 1.0, "1-3"]]}
    if lead is not None:
        rec["SignalLeadSchedule"] = [[float(t[0]) - 1.0, lead]]
    return rec


def _reports(n=40, seed=1):
    rng = np.random.default_rng(seed)
    rt = T0 + 3600.0 * np.arange(n) + 30.0
    pain = rng.normal(5.0, 2.0, n)
    return rt, pain


def test_each_chronic_frequency_goes_on_the_nearest_centre_only_under_half_a_hertz():
    assert CBC.grid_centre_for(24.41, CENTRES) == 24.5
    assert CBC.grid_centre_for(24.4, CENTRES) == 24.5        # the device's snapped bin
    assert CBC.grid_centre_for(9.77, CENTRES) == 9.5
    assert CBC.grid_centre_for(7.81, CENTRES) is None          # 0.69 Hz from 8.5: no centre
    assert CBC.grid_centre_for(9.0, [8.5, 9.5]) is None        # exactly 0.5 Hz: not less than
    assert CBC.grid_centre_for(29.9, CENTRES) == 29.5
    assert CBC.grid_centre_for(30.1, CENTRES) is None


def _pair_samples(pain, rt, extra_other_pair=False):
    """Left 1-3 readings that follow pain, at each report's time; optionally readings filed under
    left 0-3 (the schedule switches pair) that run against it, at other times."""
    t13 = rt - 60.0
    lfp13 = 100.0 + 10.0 * pain
    recs = [_rec(t13, lfp13, np.full(t13.size, 1.0))]
    if extra_other_pair:
        t03 = rt - 300.0
        recs.append(_rec(t03, 500.0 - 30.0 * pain, np.full(t03.size, 1.0),
                         contacts=[[float(t03[0]) - 1.0, "0-3"]]))
    merged, _ = R.merge_chronic_repeats(recs)
    return merged


def test_readings_on_another_contact_pair_never_count():
    rt, pain = _reports()
    alone = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(_pair_samples(pain, rt)),
                                    {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=200)
    both_recs = _pair_samples(pain, rt, extra_other_pair=True)
    both = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(both_recs), {}, rt, pain,
                                   centres=CENTRES, tol_s=900.0, n_boot=200)
    assert set(both) == {"ONE_THREE_LEFT", "ZERO_THREE_LEFT"}, set(both)
    a, b = alone["ONE_THREE_LEFT"], both["ONE_THREE_LEFT"]
    assert a["n_readings"] == b["n_readings"] == rt.size
    ea, eb = a["by_centre"][24.5], b["by_centre"][24.5]
    for k in ea:                                    # field for field, no tolerance
        va, vb = ea[k], eb[k]
        assert (va == vb) or (va != va and vb != vb), (k, va, vb)
    assert ea["n_reports"] == rt.size and ea["pearson_r"] > 0.99
    # and the other pair's own answer is its own readings' (power falls as pain rises)
    assert both["ZERO_THREE_LEFT"]["by_centre"][24.5]["pearson_r"] < -0.99


def test_a_band_the_chronic_log_does_not_cover_cannot_be_labelled_chronic():
    rt, pain = _reports()
    res = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(_pair_samples(pain, rt)), {},
                                  rt, pain, centres=CENTRES, tol_s=900.0, n_boot=200)
    blk = res["ONE_THREE_LEFT"]
    rows = [{"band_center_hz": c, "pearson_r": 0.1} for c in (23.5, 24.5)]
    CBC.label_rows(rows, blk, SW.GRID_SOURCE_TD)
    assert rows[1]["choice_source"] == "chronic" and rows[1]["chronic"]["covered"] is True
    assert rows[0]["choice_source"] == "TD", rows[0]
    assert rows[0]["chronic"] == {"covered": False, "n_reports": 0,
                                  "words": "no home record at this band"}
    # a chronic frequency 0.69 Hz from every centre covers nothing
    recs, _ = R.merge_chronic_repeats([_rec(rt - 60.0, 100.0 + pain, np.ones(rt.size), freq=7.81)])
    far = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(recs), {}, rt, pain,
                                  centres=CENTRES, tol_s=900.0, n_boot=200)["ONE_THREE_LEFT"]
    assert far["by_centre"] == {} and far["frequencies"][0]["grid_centre_hz"] is None
    assert far["frequencies"][0]["covered"] is False
    # too few reports matched: covered False, the row stays TD and says why
    few, _ = R.merge_chronic_repeats([_rec(rt[:5] - 60.0, 100.0 + pain[:5], np.ones(5))])
    thin = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(few), {}, rt, pain,
                                   centres=CENTRES, tol_s=900.0, n_boot=200)["ONE_THREE_LEFT"]
    row = CBC.label_rows([{"band_center_hz": 24.5}], thin, SW.GRID_SOURCE_TD)[0]
    assert row["choice_source"] == "TD" and row["chronic"]["covered"] is False
    assert row["chronic"]["n_reports"] == 5 and "too thin" in row["chronic"]["words"]
    # PSD-only and mixed rows never choose, covered or not
    for src in (SW.GRID_SOURCE_PSD, SW.GRID_SOURCE_MIXED):
        r = CBC.label_rows([{"band_center_hz": 24.5}], blk, src)[0]
        assert r["choice_source"] == "none" and r["chronic"]["covered"] is True
    # an area-under-the-curve row stays TD's (the chronic log gives no such value)
    r = CBC.label_rows([{"band_center_hz": 24.5}], blk, SW.GRID_SOURCE_TD, correlation=False)[0]
    assert r["choice_source"] == "TD" and r["choice_source_why"] == CBC.AUC_STAYS_TD


def test_a_chronic_readings_current_is_its_own_leads():
    """The right log holds copies of the left lead's signal (adaptive group: both logs sense the
    left lead), with the RIGHT lead's current. After the merge, the left pair's readings must take
    the LEFT lead's current (here varying 1.0 / 2.0 mA), never the right's (a constant 3.0 mA)."""
    rt, pain = _reports()
    t = rt - 60.0
    left_amp = np.where(np.arange(t.size) % 2 == 0, 1.0, 2.0)
    left = _rec(t, 100.0 + 10.0 * pain, left_amp, side="Left", lead="LEFT")
    right = _rec(t, 100.0 + 10.0 * pain, np.full(t.size, 3.0), side="Right", lead="LEFT")
    merged, counts = R.merge_chronic_repeats([left, right])
    assert counts["other_lead_copies_merged"] == t.size, counts
    cur = CBC.lead_currents(merged)
    got, n_two = CBC.current_at_times(t, cur["Left"])
    assert np.array_equal(got, left_amp) and n_two == 0, got
    assert set(CBC.current_at_times(t, cur["Right"])[0].tolist()) == {3.0}
    res = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(merged), cur, rt, pain,
                                  centres=CENTRES, tol_s=900.0, n_boot=200)
    assert set(res) == {"ONE_THREE_LEFT"}, set(res)        # the copies are not a right-lead pair
    e = res["ONE_THREE_LEFT"]["by_centre"][24.5]
    chk = e["current_removed_check"]
    assert chk["n_distinct_currents"] == 2, chk             # 1.0 and 2.0: the left lead's own
    assert e["n_readings_without_current"] == 0


def test_the_answer_reads_interval_and_rotation_p_and_the_current_check_never_moves_it():
    rt, pain = _reports(n=60)
    res = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(_pair_samples(pain, rt)), {},
                                  rt, pain, centres=CENTRES, tol_s=900.0, n_boot=200)
    e = res["ONE_THREE_LEFT"]["by_centre"][24.5]
    assert e["answer"] == "established" and e["p_rotation"] <= 0.05 and e["pearson_r_low"] > 0
    assert e["n_rotations"] == 59
    # no current at all: the check says "not assessed" (a warning) and the answer is unchanged
    assert e["current_removed_check"]["status"] == "not assessed"
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 1, rt.size)
    recs, _ = R.merge_chronic_repeats([_rec(rt - 60.0, 100.0 + noise, np.ones(rt.size))])
    e2 = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(recs), {}, rt, pain, centres=CENTRES,
                                 tol_s=900.0, n_boot=200)["ONE_THREE_LEFT"]["by_centre"][24.5]
    assert e2["answer"] == "not_resolved" or e2["p_rotation"] > 0.05


def test_the_window_and_one_reading_for_one_report():
    rt = np.array([T0, T0 + 600.0, T0 + 5000.0])
    st = np.array([T0 - 100.0, T0 + 250.0, T0 + 400.0, T0 + 4000.0])
    owned = CBC.match_reports(rt, st, tol_s=900.0)
    assert owned == [[0, 1], [2], []], owned               # each reading to its nearest report
    assert CBC.match_reports(rt, st, tol_s=900.0, allow_window_reuse=True)[1] == [0, 1, 2]
    assert CBC.match_reports(rt, st, tol_s=900.0, match_direction="prior")[0] == [0]


def test_the_grid_key_carries_the_chronic_recordings_only_with_the_chronic_choice():
    from modules.Biomarkers import bravo_service as B
    import pandas as pd
    pro = pd.DataFrame({"x": [1]})
    pro.attrs[B.PRO_STORE_KEY_ATTR] = "redcap_reports/u/abc"
    saved = (B._raw_lsb_shared_signature, B._chronic_recording_identity, SW.CHRONIC_CHOICE)
    ident = ["one"]
    try:
        B._raw_lsb_shared_signature = lambda uid, centers, identity=None: ("tiles", 1)
        B._chronic_recording_identity = lambda uid: ident[0]
        SW.CHRONIC_CHOICE = True
        k1 = B._band_sweep_signature("u", pro, "nrs", {"a": 1})[0]
        ident[0] = "two"
        k2 = B._band_sweep_signature("u", pro, "nrs", {"a": 1})[0]
        assert k1 != k2
        SW.CHRONIC_CHOICE = False
        k3 = B._band_sweep_signature("u", pro, "nrs", {"a": 1})[0]
        ident[0] = "three"
        assert B._band_sweep_signature("u", pro, "nrs", {"a": 1})[0] == k3
        assert "chronic_recordings" not in repr(k3)
    finally:
        B._raw_lsb_shared_signature, B._chronic_recording_identity, SW.CHRONIC_CHOICE = saved


def test_by_default_each_report_takes_the_one_reading_whose_ten_minutes_cover_it():
    st = np.array([T0, T0 + 600.0, T0 + 1200.0])
    # 1150 s: the reading stamped 600 s covers it ([600, 1200)); the one stamped 1200 s is nearer
    owned, gap = CBC.covering_reports([T0 + 1150.0, T0 + 10.0], st)
    assert owned == [[1], [0]] and not gap.any(), owned


def test_a_report_at_the_exact_boundary_goes_to_the_next_reading_only():
    st = np.array([T0, T0 + 600.0, T0 + 1200.0])
    owned, gap = CBC.covering_reports([T0 + 600.0, T0 + 1800.0 - 1e-6, T0 + 1800.0], st)
    assert owned[0] == [1], owned                           # [600, 1200) holds 600, [0, 600) does not
    assert owned[1] == [2] and owned[2] == [] and not gap.any(), (owned, gap)   # 1800 is past the log


def test_a_report_in_a_gap_of_the_log_has_no_reading_and_is_counted():
    rt, pain = _reports(n=30)
    t = rt - 60.0
    keep = np.ones(rt.size, dtype=bool); keep[[5, 6, 7]] = False          # the log stops for 3 hours
    recs, _ = R.merge_chronic_repeats([_rec(t[keep], 100.0 + 10.0 * pain[keep], np.ones(int(keep.sum())))])
    owned, gap = CBC.covering_reports(rt, t[keep])
    assert [len(o) for o in owned] == [0 if not k else 1 for k in keep] and gap.sum() == 3
    e = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(recs), {}, rt, pain, centres=CENTRES,
                                tol_s=900.0, n_boot=200)["ONE_THREE_LEFT"]["by_centre"][24.5]
    assert e["n_reports"] == 27 and e["n_reports_in_gap"] == 3 and e["chronic_match"] == "covering"
    assert e["n_reports_log_elsewhere"] == 0
    # the same three hours logged at another frequency: not a gap, the log was at that frequency
    other = _rec(t[~keep], 50.0 + pain[~keep], np.ones(3), freq=9.77)
    recs2, _ = R.merge_chronic_repeats([_rec(t[keep], 100.0 + 10.0 * pain[keep], np.ones(int(keep.sum()))), other])
    e2 = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(recs2), {}, rt, pain, centres=CENTRES,
                                 tol_s=900.0, n_boot=200)["ONE_THREE_LEFT"]["by_centre"][24.5]
    assert e2["n_reports_in_gap"] == 0 and e2["n_reports_log_elsewhere"] == 3, e2
    # or on another contact pair of the same lead: not a gap either; on the other lead: a gap
    for side, want in (("Left", (0, 3)), ("Right", (3, 0))):
        o3 = _rec(t[~keep], 50.0 + pain[~keep], np.ones(3), side=side,
                  contacts=[[float(t[~keep][0]) - 1.0, "0-3"]])
        recs3, _ = R.merge_chronic_repeats([_rec(t[keep], 100.0 + 10.0 * pain[keep], np.ones(int(keep.sum()))), o3])
        e3 = CBC.chronic_band_choice(CBC.chronic_samples_by_pair(recs3), {}, rt, pain, centres=CENTRES,
                                     tol_s=900.0, n_boot=200, pairs=["ONE_THREE_LEFT"])["ONE_THREE_LEFT"]["by_centre"][24.5]
        assert (e3["n_reports_in_gap"], e3["n_reports_log_elsewhere"]) == want, (side, e3)
    assert "warning" not in e


def _window_and_covering(rt, pain):
    """Readings every 10 minutes all day; each report's own reading differs from its neighbours."""
    t = np.arange(rt.min() - 3600.0, rt.max() + 3600.0, 600.0)
    rng = np.random.default_rng(3)
    lfp = 200.0 + rng.normal(0, 20, t.size)
    for r, p in zip(rt, pain):
        lfp[np.searchsorted(t, r, side="right") - 1] = 100.0 + 10.0 * p
    recs, _ = R.merge_chronic_repeats([_rec(t, lfp, np.ones(t.size))])
    return CBC.chronic_samples_by_pair(recs)


def test_the_heat_maps_window_does_not_change_the_default():
    rt, pain = _reports()
    S = _window_and_covering(rt, pain)
    a = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=300.0, n_boot=200)
    b = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=3600.0, n_boot=200,
                                match_direction="prior", allow_window_reuse=True)
    ea, eb = a["ONE_THREE_LEFT"]["by_centre"][24.5], b["ONE_THREE_LEFT"]["by_centre"][24.5]
    for k in ea:
        assert (ea[k] == eb[k]) or (ea[k] != ea[k] and eb[k] != eb[k]), (k, ea[k], eb[k])
    assert ea["pearson_r"] > 0.999 and ea["n_reports"] == rt.size


def test_the_override_gives_the_window_numbers_and_carries_the_warning():
    rt, pain = _reports()
    S = _window_and_covering(rt, pain)
    w = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=200,
                                chronic_match="window")["ONE_THREE_LEFT"]
    e = w["by_centre"][24.5]
    # the window's numbers: each report the median of the readings within 15 minutes, by hand
    d = S["ONE_THREE_LEFT"]
    owned = CBC.match_reports(np.sort(rt), d["t"], tol_s=900.0)
    x = np.array([np.median(d["y"][o]) for o in owned])
    assert abs(e["pearson_r"] - float(np.corrcoef(x, pain[np.argsort(rt)])[0, 1])) == 0.0
    assert e["pearson_r"] < 0.999                           # not the covering reading's answer
    words = CBC.non_default_warning("window", 900.0)
    assert w["warning"] == words and e["warning"] == words and "recommended default" in words
    row = CBC.label_rows([{"band_center_hz": 24.5, "pearson_r": 0.0}], w, SW.GRID_SOURCE_TD)[0]
    assert row["chronic"]["warning"] == words
    seen = SW.chronic_decides(row)
    assert seen["chronic_match_warning"] == words and words in seen["why"]
    # the default carries none, on the block, the row or the choosing view
    c = CBC.chronic_band_choice(S, {}, rt, pain, centres=CENTRES, tol_s=900.0, n_boot=200)["ONE_THREE_LEFT"]
    row = CBC.label_rows([{"band_center_hz": 24.5, "pearson_r": 0.0}], c, SW.GRID_SOURCE_TD)[0]
    assert "warning" not in c and "warning" not in row["chronic"]
    assert "chronic_match_warning" not in SW.chronic_decides(row)


def test_the_chronic_match_is_in_the_key_and_only_a_non_default_one_in_the_tag():
    assert SW.chronic_match_param({}) == "covering"
    assert SW.chronic_match_param({"ChronicMatch": "window"}) == "window"
    assert SW.chronic_match_param({"ChronicMatch": "nonsense"}) == "covering"
    default = SW.sweep_settings_tag_from_request({})
    assert "chronic_match" not in default                   # every default tag as before
    assert SW.sweep_settings_tag_from_request({"ChronicMatch": "window"})["chronic_match"] == "window"
    assert SW.sweep_settings_tag_from_request({"ChronicMatch": "window"}) != default
    keys = {m: SW._key_settings_from_sidecar({"sweep_settings": SW.sweep_settings_tag_from_request(
        {"ChronicMatch": m})})["chronic_match"] for m in ("covering", "window")}
    assert keys == {"covering": "covering", "window": "window"}
