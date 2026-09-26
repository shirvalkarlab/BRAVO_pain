"""The research band detector, both versions (the PI's rulings 5a-5c, 2026-09-25), on constructed
records whose answer is known. Plain asserts, no fixtures; both suites run it."""
import numpy as np

try:
    from modules.ControlAnalyses import band_detector as BD
    from modules.ControlAnalyses import registry as RG
except ImportError:                                            # host spelling
    from ControlAnalyses import band_detector as BD
    from ControlAnalyses import registry as RG


def _days(n, per_day=3):
    return np.array([f"2026-01-{1 + i // per_day:02d}" if i // per_day < 28 else
                     f"2026-02-{1 + i // per_day - 28:02d}" for i in range(n)])


def _record(n=180, *, signal=0.0, confound=0.0, seed=0, n_bands=6, flip_half=False):
    """Pain, a current on seven settings, and bands. ``signal``: band 0 carries pain beyond the
    current. ``confound``: the current moves every band and the pain together."""
    rng = np.random.default_rng(seed)
    cur = np.repeat(np.linspace(0.5, 3.5, 7), int(np.ceil(n / 7)))[:n]
    rng.shuffle(cur)
    pain_own = rng.normal(0, 1, n)
    pain = pain_own + confound * (cur - cur.mean())
    X = rng.normal(0, 1, (n, n_bands)) + 100.0
    X[:, :] += confound * (cur - cur.mean())[:, None]
    sign = np.ones(n)
    if flip_half:
        sign[n // 2:] = -1.0
    X[:, 0] += signal * sign * pain_own
    return X, pain, cur, _days(n)


# ---- the research version: pain as a number --------------------------------------------------

def test_research_finds_a_planted_band_and_beats_its_rotations():
    X, y, c, d = _record(signal=1.5, seed=1)
    r = BD.research_reading(X, y, c, d, n_perm=60, n_boot=300)
    assert r["reason"] is None and r["folded"] is False
    assert r["bands"]["rho"] > 0.4, r["bands"]
    assert r["bands"]["p"] < 0.05
    assert r["bands"]["lo"] > 0.0
    assert r["bands"]["r2"] > 0.1


def test_research_with_nothing_planted_stays_inside_its_rotations():
    X, y, c, d = _record(signal=0.0, seed=2)
    r = BD.research_reading(X, y, c, d, n_perm=60, n_boot=300)
    assert r["bands"]["p"] > 0.05, r["bands"]
    assert r["bands"]["lo"] < 0.0 < r["bands"]["hi"] or r["bands"]["rho"] <= 0.0


def test_research_current_taken_out_of_bands_and_pain_removes_a_pure_confound():
    X, y, c, d = _record(signal=0.0, confound=2.0, seed=3)
    r = BD.research_reading(X, y, c, d, n_perm=60, n_boot=300)
    assert r["bands"]["rho"] > 0.5                                 # the plain reading finds the current
    assert r["current_alone"]["rho"] > 0.5
    adj = r["bands_without_current"]
    assert abs(adj["rho"]) < 0.25, adj
    assert adj["p"] > 0.05                                         # against ITS OWN rotations
    assert "spline" in r["shape"]


def test_research_keeps_a_real_band_once_the_current_is_out():
    X, y, c, d = _record(signal=1.5, confound=2.0, seed=4)
    r = BD.research_reading(X, y, c, d, n_perm=60, n_boot=300)
    assert r["bands_without_current"]["rho"] > 0.3
    assert r["bands_without_current"]["p"] < 0.05


def test_the_adjusted_reading_is_judged_against_its_own_rotations():
    # decision 276: the reading with the current taken out gets a null that refits THAT pipeline on
    # each rotation, never the plain reading's null. One rotation, so its score is the null median.
    SU = BD.SU
    X, y, c, d = _record(signal=0.8, confound=1.5, seed=7)
    r = BD.research_reading(X, y, c, d, n_perm=1, n_boot=50, seed=3)
    rot = BD.rotations(len(y), SU.block_length_for(y, len(y)), 1, np.random.default_rng(3))
    folds, _e = BD._rows_and_folds(y, 5, None)
    sh = SU.CovariateShape(c, shape=BD.DEFAULT_SHAPE)
    own = BD._research_score(X, y[rot[0]], folds, sh)[0]
    plain = BD._research_score(X, y[rot[0]], folds)[0]
    assert abs(own - plain) > 1e-6
    assert abs(r["bands_without_current"]["null_p50"] - own) < 1e-12
    assert abs(r["bands"]["null_p50"] - plain) < 1e-12


def test_research_score_is_never_folded():
    # the band's relationship with pain reverses halfway: a model trained on one half predicts the
    # other half the wrong way round, and that must read as a NEGATIVE score, not a positive one
    X, y, c, d = _record(n=200, signal=3.0, seed=5, flip_half=True, n_bands=1)
    r = BD.research_reading(X, y, c, d, n_folds=2, n_perm=0, n_boot=200, adjust=False)
    assert r["bands"]["rho"] < -0.2, r["bands"]


def _drifting_record(n=200, seed=21):
    """Pain falls steadily over the record; the band carries nothing. Each held-out block's
    training rows then have a different average pain from the block itself."""
    rng = np.random.default_rng(seed)
    y = np.linspace(8.0, 3.0, n) + rng.normal(0, 0.7, n)
    X = rng.normal(100, 1, (n, 3))
    c = np.repeat(np.linspace(0.5, 3.5, 7), int(np.ceil(n / 7)))[:n]
    rng.shuffle(c)
    return X, y, c, _days(n)


def test_research_a_drifting_pain_score_does_not_read_as_a_backwards_band():
    # Pooling held-out predictions across blocks mixes each block's own training mean into the
    # ranking: an early (high-pain) block is predicted from later, lower-pain rows and vice versa,
    # so a band with no relationship ranks pain BACKWARDS. The score is taken within each block.
    X, y, c, d = _drifting_record()
    r = BD.research_reading(X, y, c, d, n_perm=0, n_boot=200, adjust=False)
    assert abs(r["bands"]["rho"]) < 0.25, r["bands"]


def test_device_a_drifting_pain_score_does_not_read_as_a_backwards_band():
    X, y, c, d = _drifting_record()
    lo_c, hi_c = np.percentile(y, [100 / 3, 200 / 3])
    y01 = np.where(y <= lo_c, 0.0, np.where(y >= hi_c, 1.0, np.nan))
    r = BD.device_reading(X[:, 0] - 0.5, X[:, 0] + 0.5, X[:, 0], y01, c, d, n_perm=0, n_boot=200,
                          adjust=False)
    assert r["band"]["auc"] is None or abs(r["band"]["auc"] - 0.5) < 0.2, r["band"]


def test_research_too_few_rows_is_a_reason_not_a_number():
    X, y, c, d = _record(n=30, seed=6)
    r = BD.research_reading(X, y, c, d, n_perm=10, n_boot=50)
    assert r["bands"] is None and "40 are needed" in r["reason"]


# ---- the device-shaped version: two groups, logistic regression ------------------------------

def _device_record(n=180, *, signal=0.0, confound=0.0, falls=False, seed=0):
    X, y, c, d = _record(n=n, signal=signal, confound=confound, seed=seed, n_bands=1)
    lo, hi = np.percentile(y, [100 / 3, 200 / 3])
    y01 = np.where(y <= lo, 0.0, np.where(y >= hi, 1.0, np.nan))
    band = X[:, 0] if not falls else 200.0 - X[:, 0]
    return band - 0.5, band + 0.5, band, y01, c, d


def test_logistic_regression_learns_the_sign_and_ranks_like_the_feature():
    rng = np.random.default_rng(0)
    x = rng.normal(0, 1, 300)
    y = (x + rng.normal(0, 1, 300) > 0).astype(float)
    fit = BD.logistic_fit(x, y)
    assert fit[0][1] > 0.5
    p = BD.logistic_predict(fit, x)
    assert abs(BD.auc_signed(p, y) - BD.auc_signed(x, y)) < 1e-12
    fit_sep = BD.logistic_fit(np.r_[np.zeros(20), np.ones(20)], np.r_[np.zeros(20), np.ones(20)])
    assert np.all(np.isfinite(fit_sep[0]))                        # a separable block stays finite


def test_device_finds_a_rising_band_by_logistic_regression():
    lo, hi, mid, y01, c, d = _device_record(signal=1.5, seed=11)
    r = BD.device_reading(lo, hi, mid, y01, c, d, n_perm=60, n_boot=300)
    assert r["reason"] is None and r["folded"] is False
    assert r["band"]["auc"] > 0.7 and r["band"]["lo"] > 0.5
    assert r["band"]["p"] < 0.05
    assert r["band"]["direction"] == "rises with pain"


def test_device_learns_a_falling_band_rather_than_folding_it():
    lo, hi, mid, y01, c, d = _device_record(signal=1.5, falls=True, seed=12)
    r = BD.device_reading(lo, hi, mid, y01, c, d, n_perm=40, n_boot=300)
    assert r["band"]["direction"] == "falls with pain"
    assert r["band"]["auc"] > 0.7


def test_device_current_taken_out_removes_a_pure_confound():
    lo, hi, mid, y01, c, d = _device_record(confound=2.0, seed=13)
    r = BD.device_reading(lo, hi, mid, y01, c, d, n_perm=60, n_boot=300)
    assert r["band"]["auc"] > 0.75 and r["current_alone"]["auc"] > 0.75
    adj = r["band_without_current"]
    assert abs(adj["auc"] - 0.5) < 0.15, adj
    assert adj["p"] > 0.05


def test_device_score_is_never_folded():
    X, y, c, d = _record(n=200, signal=3.0, seed=14, flip_half=True, n_bands=1)
    lo_c, hi_c = np.percentile(y, [100 / 3, 200 / 3])
    y01 = np.where(y <= lo_c, 0.0, np.where(y >= hi_c, 1.0, np.nan))
    r = BD.device_reading(X[:, 0] - 0.5, X[:, 0] + 0.5, X[:, 0], y01, c, d, n_folds=2, n_perm=0,
                          n_boot=200, adjust=False)
    assert r["band"]["auc"] < 0.4, r["band"]


# ---- the device's own timing ------------------------------------------------------------------

def _pieces(starts, n_each, piece_s=3.0, bands=2, seed=0):
    rng = np.random.default_rng(seed)
    t = np.concatenate([s + piece_s * np.arange(n) for s, n in zip(starts, n_each)])
    v = rng.normal(100, 10, (t.size, bands))
    return t, np.ones(t.size, bool), v


def test_device_window_skips_the_startup_and_holds_the_onset():
    t, ok, v = _pieces([1000.0], [30])
    lo, hi, mid, st, info = BD.device_windows(t, ok, v, [990.0], piece_s=3.0, averaging_s=3.0,
                                              onset_s=30.0, startup_s=15.0, tol_s=3600.0)
    assert info["readings_per_decision"] == 10 and info["startup_pieces"] == 5
    w = v[5:15]                                                    # 5 start-up pieces skipped
    assert np.allclose(lo[0], w.min(axis=0)) and np.allclose(hi[0], w.max(axis=0))
    assert np.allclose(mid[0], np.median(w, axis=0))
    assert st[0] == t[5]


def test_device_window_direction_and_the_match_window():
    t, ok, v = _pieces([0.0, 5000.0], [20, 20])
    rating = [2500.0]
    lo_after, *_rest, st_after, _ = BD.device_windows(t, ok, v, rating, piece_s=3.0, averaging_s=3.0,
                                                      onset_s=30.0, startup_s=15.0, tol_s=3600.0)
    assert st_after[0] == 5000.0 + 15.0                            # report first: the run after
    lo_b, hi_b, mid_b, st_b, _ = BD.device_windows(t, ok, v, rating, piece_s=3.0, averaging_s=3.0,
                                                   onset_s=30.0, startup_s=15.0, tol_s=3600.0,
                                                   direction="prior")
    assert np.allclose(lo_b[0], v[10:20].min(axis=0))            # the last window before it
    far = BD.device_windows(t, ok, v, [2500.0], piece_s=3.0, averaging_s=3.0, onset_s=30.0,
                            startup_s=15.0, tol_s=600.0)
    assert np.isnan(far[3][0])                                     # nothing within 10 minutes


def test_device_window_is_broken_by_a_gap_or_a_failed_piece():
    t, ok, v = _pieces([0.0], [30])
    ok[18] = False                                                 # a failed piece mid-run
    lo, hi, mid, st, info = BD.device_windows(t, ok, v, [0.0], piece_s=3.0, averaging_s=3.0,
                                              onset_s=30.0, startup_s=15.0, tol_s=3600.0)
    assert info["n_runs"] == 2
    assert st[0] == t[5]                                           # pieces 5..14 still hold 10
    lo2, *_r, st2, _i = BD.device_windows(t[:14], ok[:14], v[:14], [0.0], piece_s=3.0,
                                          averaging_s=3.0, onset_s=30.0, startup_s=15.0, tol_s=3600.0)
    assert np.isnan(st2[0])                                        # 14 pieces: 5 start-up + 9 < 10


def test_device_window_averages_whole_readings_when_averaging_is_longer_than_a_piece():
    t, ok, v = _pieces([0.0], [40], bands=1)
    lo, hi, mid, st, info = BD.device_windows(t, ok, v, [0.0], piece_s=3.0, averaging_s=6.0,
                                              onset_s=30.0, startup_s=15.0, tol_s=3600.0)
    assert info["pieces_per_reading"] == 2 and info["readings_per_decision"] == 5
    readings = v[5:15, 0].reshape(5, 2).mean(axis=1)
    assert np.isclose(lo[0, 0], readings.min()) and np.isclose(hi[0, 0], readings.max())


def test_timing_outside_the_device_range_is_named():
    assert BD.check_timing({"averaging_ms": 3000.0}, {"averaging_ms": (0.0, 30000.0)}) == []
    assert BD.check_timing({"onset_ms": 60000.0}, {"onset_ms": (0.0, 30000.0)}) == ["onset_ms"]


# ---- the unchanged-current stretch, the corrections, the registry -----------------------------

def test_longest_same_current_run():
    c = np.array([1.0, 1.0, 2.0, 2.0, 2.0, np.nan, 2.0, 1.0, 1.0])
    assert BD.longest_same_current_run(c).tolist() == [2, 3, 4]


def test_rotations_never_include_the_observed_order():
    rot = BD.rotations(120, 1, 60, np.random.default_rng(0))       # seed 0 draws shift 0 three times
    assert rot.shape == (60, 120)
    assert not any(np.array_equal(r, np.arange(120)) for r in rot)


def test_q_values_over_one_family():
    rows = [{"p": 0.01}, {"p": 0.04}, {"p": None}, {"p": 0.5}]
    BD.add_q(rows, "p", "q")
    assert np.isclose(rows[0]["q"], 0.04) and "q" not in rows[2]


def test_both_versions_are_registered_on_the_biomarkers_page():
    for k in ("band_detector_research", "band_detector_device"):
        assert RG.ANALYSES[k]["page"] == "biomarkers"
        assert "clinic-sheet" in RG.ANALYSES[k]["what"]
