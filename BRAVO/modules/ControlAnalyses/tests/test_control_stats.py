"""The statistics behind the saved control analyses (the PI, 2026-09-24), each on constructed data
whose answer is known. Plain asserts and no arguments: this file runs in both suites."""
import numpy as np

try:
    from modules.ControlAnalyses import stats as ST
except ImportError:
    from ControlAnalyses import stats as ST

H = 3600.0


def test_ranks_are_taken_inside_each_stretch_so_a_shift_between_stretches_is_not_a_correlation():
    rng = np.random.default_rng(0)
    x = np.concatenate([rng.normal(0, 1, 40), rng.normal(10, 1, 40)])
    y = np.concatenate([rng.normal(0, 1, 40), rng.normal(10, 1, 40)])   # two stretches, no coupling
    s = np.repeat(["a", "b"], 40)
    assert ST.spearman_within(x, y) > 0.7                               # pooled: the shift reads as a correlation
    assert abs(ST.spearman_within(x, y, s)) < 0.25                      # within: it does not


def test_the_interval_resamples_whole_days_and_holds_the_point():
    rng = np.random.default_rng(1)
    days = np.repeat(np.arange(25), 3).astype(str)
    x = rng.normal(0, 1, 75); y = x * 0.6 + rng.normal(0, 1, 75)
    r, lo, hi, p = ST.day_resampled_rho(x, y, days, n_boot=500, seed=0)
    assert lo < r < hi and p < 0.05
    assert ST.day_resampled_rho(x, y, days, n_boot=500, seed=0) == (r, lo, hi, p)   # same seed, same answer


def test_too_few_usable_resamples_is_an_answer_not_a_crash():
    r, lo, hi, p = ST.day_resampled_rho(np.array([1.0, 1, 1]), np.array([1.0, 2, 3]), np.array(["a", "a", "b"]), n_boot=50)
    assert np.isnan(lo) and np.isnan(p)


def test_benjamini_hochberg_matches_the_textbook_values():
    q = ST.bh_q([0.01, 0.04, 0.03, 0.005, np.nan])            # a missing p counts as 1, in the family
    assert np.allclose(q, [0.025, 0.05, 0.05, 0.025, 1.0])


def test_a_current_with_no_memory_is_the_current_in_force_and_a_held_current_is_itself():
    steps_t = np.array([0.0, 100 * H]); steps_a = np.array([2.0, 4.0])
    t = np.array([50 * H, 150 * H, 1000 * H])
    assert ST.dose_history(t, steps_t, steps_a, 0).tolist() == [2.0, 4.0, 4.0]
    d = ST.dose_history(t, steps_t, steps_a, 24)
    assert abs(d[2] - 4.0) < 1e-6                                       # long after the change
    one_tau = ST.dose_history(np.array([100 * H + 24 * H]), steps_t, steps_a, 24)[0]
    # nothing before the first step; 2 mA for 100 h, then 4 mA for one tau (24 h)
    exact = 2.0 * (np.exp(-1) - np.exp(-124 / 24)) + 4.0 * (1 - np.exp(-1))
    assert abs(one_tau - exact) < 1e-9


def test_the_tau_curve_finds_the_memory_a_planted_record_has():
    rng = np.random.default_rng(2)
    steps_t = np.arange(0, 60 * 24 * H, 5 * 24 * H)                    # a change every 5 days for 60 days
    steps_a = rng.choice([0.0, 1.0, 2.0, 3.0], steps_t.size)
    t = np.sort(rng.uniform(0, 60 * 24 * H, 600))
    y = 5 - 1.5 * ST.dose_history(t, steps_t, steps_a, 24) + rng.normal(0, 0.3, t.size)
    folds = [(np.setdiff1d(np.arange(600), np.arange(k * 120, (k + 1) * 120)), np.arange(k * 120, (k + 1) * 120))
             for k in range(5)]
    curve = ST.tau_curve(t, y, {"one": (steps_t, steps_a)}, [0, 6, 24, 168], folds, n_boot=200)
    best = max(curve, key=lambda row: row["r2"])
    assert best["tau_h"] == 24 and curve[0]["tau_h"] == 0 and curve[0]["change_vs_now"] == 0.0


def test_stretches_with_a_side_off_are_read_from_the_settings_stream_alone():
    try:
        from modules.ControlAnalyses import runners as RN
    except ImportError:
        from ControlAnalyses import runners as RN
    D = 86400.0
    stream = {"t_s": np.array([0, 0, 10 * D, 10 * D, 20 * D, 21 * D, 30 * D]),
              "hemi": np.array(["Left", "Right", "Left", "Right", "Right", "Left", "Left"], dtype=object),
              "amp_mA": np.array([0.0, 0.0, 0.0, 2.0, 2.5, 1.0, 1.5])}
    got = [(s["kind"], s["start_s"] / D, s["end_s"] / D) for s in RN.stretches(stream, until_s=40 * D)]
    # both off 0-10; left off, right on 10-21 (the right changing within it); both on after: not a stretch
    assert got == [("both off", 0.0, 10.0), ("left off, right on", 10.0, 21.0)]
    assert RN.stretches(stream, min_days=12, until_s=40 * D) == []


def test_switches_come_from_the_off_stretches_and_pain_is_read_in_windows_around_them():
    try:
        from modules.ControlAnalyses import runners as RN
    except ImportError:
        from ControlAnalyses import runners as RN
    D = 86400.0
    stream = {"t_s": np.array([0, 0, 20 * D, 20 * D]), "hemi": np.array(["Left", "Right", "Left", "Right"], dtype=object),
              "amp_mA": np.array([2.0, 2.0, 0.0, 0.0])}
    stream["t_s"] = np.append(stream["t_s"], [40 * D, 40 * D]); stream["hemi"] = np.append(stream["hemi"], ["Left", "Right"])
    stream["amp_mA"] = np.append(stream["amp_mA"], [2.0, 2.0])
    ev = RN.switches(stream)
    assert [(e["direction"], e["t_s"] / D) for e in ev] == [("off", 20.0), ("on", 40.0)]
    t = np.arange(0, 60, 0.5) * D
    v = np.where((t >= 20 * D) & (t < 40 * D), 8.0, 6.0)
    rows = RN.pain_around(ev, t, v)
    assert rows[0]["before"]["mean"] == 6.0 and rows[0]["after"][0]["mean"] == 8.0
    assert rows[1]["before"]["mean"] == 8.0 and rows[1]["after"][1]["mean"] == 6.0


def test_a_clinic_visit_inside_a_stretch_does_not_split_it():
    try:
        from modules.ControlAnalyses import runners as RN
    except ImportError:
        from ControlAnalyses import runners as RN
    D, H = 86400.0, 3600.0
    # left off throughout; right on 10-40 d, with a 2-hour visit at day 25 that steps the right to 0
    stream = {"t_s": np.array([0, 0, 10 * D, 25 * D, 25 * D + 2 * H, 40 * D, 40 * D]),
              "hemi": np.array(["Left", "Right", "Right", "Right", "Right", "Right", "Left"], dtype=object),
              "amp_mA": np.array([0.0, 0.0, 2.0, 0.0, 2.0, 0.0, 1.0])}
    got = [(s["kind"], round(s["start_s"] / D, 2), round(s["end_s"] / D, 2)) for s in RN.stretches(stream, until_s=50 * D)]
    assert ("left off, right on", 10.0, 40.0) in got


def test_pairs_are_named_as_the_pages_name_them():
    try:
        from modules.ControlAnalyses import runners as RN
    except ImportError:
        from ControlAnalyses import runners as RN
    assert RN.pair_name("ONE_THREE_LEFT") == "L 1-3+" and RN.pair_name("ZERO_THREE_RIGHT") == "R 0-3+"
    assert RN.pair_name("LeftHemisphere") == "LeftHemisphere"


def test_a_switch_says_which_side_changed_when_one_stretch_runs_into_another():
    try:
        from modules.ControlAnalyses import runners as RN
    except ImportError:
        from ControlAnalyses import runners as RN
    D = 86400.0
    # both off 0-10 d, then the right comes on (left stays off) 10-20 d, then the left comes on
    stream = {"t_s": np.array([0, 0, 10 * D, 20 * D]), "hemi": np.array(["Left", "Right", "Right", "Left"], dtype=object),
              "amp_mA": np.array([0.0, 0.0, 2.0, 1.0])}
    ev = [(round(e["t_s"] / D), e["label"].split(",")[0]) for e in RN.switches(stream)]
    assert ev == [(0, "both sides off"), (10, "the right side on"), (20, "the left side on")]
