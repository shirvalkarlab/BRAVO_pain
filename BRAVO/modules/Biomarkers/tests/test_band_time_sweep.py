"""Tests for the band-by-length-of-signal sweep at the bottom of the biomarker exploration page.

Every test here exists because something specific could go wrong silently. In order:

  * the length of signal a row is LABELLED with has to be the length actually delivered, and the
    delivered length is decided by the matcher, so the label is checked against the matcher's own
    reported count rather than against a repeat of the arithmetic;
  * the vectorised outlier rule has to be the same rule as the scalar one it replaced for speed;
  * the relationship between the ordering's area under the curve and a real fitted one-predictor
    logistic regression's own area under the curve has to hold on every cell of a grid, since that
    relationship is what lets 220 cells be filled without 220 model fits;
  * the sweep has to HONOUR THE TOP-OF-PAGE SETTINGS rather than recomputing with its own defaults;
  * an interval that spans 0.5 must NOT read as a negative result anywhere -- not in the word, not
    in the sentence, and not in the figure headline;
  * a colour scale for the high-versus-low-pain grid centred anywhere but 0.5 is wrong;
  * a value that clears its own interval but not the shuffled best-of-ten level must not be reported
    as established, because the reported value was chosen as the best of ten.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_band_time_sweep.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A          # noqa: E402
from Biomarkers.routines import availability as AV      # noqa: E402
from Biomarkers.routines import stats_utils as SU       # noqa: E402


# ---------------------------------------------------------------------------------------------
# helpers that build a grid with a known answer in it
# ---------------------------------------------------------------------------------------------

def _synthetic_grid(seed=0, n_reports=80, planted_col=6, strength=0.9, linear=True):
    """Band powers for every length of signal, with ONE band centre made to track the pain score.

    The planted band is given a real relationship and every other band is noise, so a test can
    assert both that the planted one is found and that the others are not reported as findings.
    """
    rng = np.random.default_rng(seed)
    centers = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
    C = centers.size
    pain = rng.normal(5.0, 2.0, n_reports)
    z = (pain - pain.mean()) / pain.std()
    power = {}
    for s in A.BAND_TIME_SWEEP_SECONDS:
        n_tiles, _ = A.integration_time_tile_count(s)
        m = rng.normal(0, 1, (n_reports, C)) + rng.normal(0, 1.0 / np.sqrt(n_tiles),
                                                          (n_reports, C))
        m[:, planted_col] += strength * z
        power[float(s)] = np.exp(m) if linear else m
    return power, pain, centers


def _pure_noise_grid(seed=1, n_reports=60):
    rng = np.random.default_rng(seed)
    centers = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
    pain = rng.normal(5.0, 2.0, n_reports)
    power = {float(s): np.exp(rng.normal(0, 1, (n_reports, centers.size)))
             for s in A.BAND_TIME_SWEEP_SECONDS}
    return power, pain, centers


def _fake_raw_cache(centers_hz, n_tiles=400, seed=5, t0=1_700_000_000.0, window_s=3.0):
    """A stand-in for `availability.raw_lsb_spectrum_cache`, holding only what the matcher reads."""
    rng = np.random.default_rng(seed)
    t = t0 + np.arange(n_tiles) * window_s
    lsb = np.exp(rng.normal(0, 1, (n_tiles, len(centers_hz))))
    return {
        "channel": "ZERO_THREE_RIGHT",
        "centers_hz": [float(c) for c in centers_hz],
        "window_s": float(window_s),
        "band_half_hz": 2.5,
        "td": {"t": [float(x) for x in t], "lsb": [[float(v) for v in row] for row in lsb],
               "saturated": [False] * n_tiles, "source": ["streaming"] * n_tiles,
               "n_finite_s": [float(window_s)] * n_tiles, "ok": [True] * n_tiles},
        "psd": {"t": [], "lsb": [], "calibrated": [], "source": []},
        "n_td_windows": int(n_tiles), "n_psd_windows": 0,
    }


# ---------------------------------------------------------------------------------------------
# 1. the length of signal a row is labelled with is the length actually delivered
# ---------------------------------------------------------------------------------------------

def test_delivered_length_matches_the_matcher_not_the_request():
    """The label on every row must be the seconds DELIVERED, and the matcher decides that.

    The cache holds whole 3 s pieces, so a request for 1 s is served by one piece and delivers 3 s.
    Labelling such a row "1 s" would misstate the shortest measurement in the whole grid by
    threefold. This asserts the module's own label against the count the REAL matcher reports for
    the same request, so the two cannot drift apart.
    """
    centers = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
    cache = _fake_raw_cache(centers)
    pro = np.asarray([cache["td"]["t"][200]], dtype=float)
    for s in A.BAND_TIME_SWEEP_SECONDS:
        n_tiles, delivered = A.integration_time_tile_count(s, cache["window_s"])
        _, stats = AV.live_lsb_spectrum_match(pro, cache, tol_s=3600.0, td_quantity_s=float(s))
        assert int(stats["td_n_epochs_cap"]) == n_tiles, (
            f"at {s} s the module labels {n_tiles} pieces but the matcher used "
            f"{stats['td_n_epochs_cap']}")
        assert abs(delivered - n_tiles * cache["window_s"]) < 1e-9
    # And the specific consequence a reader has to be told about.
    assert A.integration_time_tile_count(1.0, 3.0) == (1, 3.0)
    assert A.integration_time_tile_count(5.0, 3.0) == (2, 6.0)
    print("OK delivered length: the matcher and the label agree at all "
          f"{len(A.BAND_TIME_SWEEP_SECONDS)} lengths; 1 s is delivered as 3 s")


def test_notes_declare_the_lengths_that_could_not_be_delivered():
    """The panel must SAY which lengths could not be delivered, with both numbers."""
    power, pain, centers = _pure_noise_grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=100, n_boot=200)
    joined = " ".join(sw["notes"])
    assert "could not be delivered exactly" in joined
    assert "1 s asked for, 3 s delivered" in joined
    for row in sw["best_correlation_rows"] + sw["best_auc_rows"]:
        if row.get("integration_seconds_delivered") is None:
            continue
        assert row["integration_seconds_requested"] is not None
    print("OK the notes name every length that could not be delivered, with both numbers")


# ---------------------------------------------------------------------------------------------
# 2. the vectorised outlier rule is the same rule as the scalar one
# ---------------------------------------------------------------------------------------------

def test_vectorised_outlier_rule_matches_the_scalar_one():
    """Same rule, column by column, including the edge cases that make it non-trivial.

    The vectorised version exists only for speed. A faster rule that is a DIFFERENT rule would
    change which measurements the whole grid is computed on, so the columns exercised here include
    a column with no spread (its deviation is zero and nothing may be flagged), a column with too
    few usable values, and a column that is negative throughout (nothing survives the logarithm).
    """
    rng = np.random.default_rng(3)
    X = rng.lognormal(0.0, 1.0, (60, 8))
    X[0, 0] = 1e6                    # a genuine outlier
    X[5, 3] = np.nan
    X[:, 4] = 7.0                    # no spread at all
    X[:, 5] = np.nan
    X[:3, 5] = [1.0, 2.0, 3.0]       # fewer than four usable values
    X[:, 6] = -np.abs(X[:, 6])       # nothing strictly positive
    for scale in ("raw", "log"):
        fast = A.mad_outlier_columns(X, n_mad=5.0, scale=scale)
        slow = np.column_stack([SU.mad_outlier_flags(X[:, c], n_mad=5.0, scale=scale)[0]
                                for c in range(X.shape[1])])
        assert np.array_equal(fast, slow), f"the two rules disagree on the {scale} scale"
        assert not fast[:, 4].any(), "a column with no spread must have nothing flagged"
        assert not fast[:, 5].any(), "a column with too few values must have nothing flagged"
    # And it works on the three-dimensional stack the sweep actually hands it.
    stack = np.stack([X, X * 2.0, X * 3.0], axis=0)
    got = A.mad_outlier_columns(stack, n_mad=5.0, scale="log")
    assert got.shape == stack.shape
    for t in range(3):
        assert np.array_equal(got[t], A.mad_outlier_columns(stack[t], n_mad=5.0, scale="log"))
    print("OK the vectorised outlier rule is identical to the scalar one on every column, "
          "including the no-spread, too-few and non-positive cases")


# ---------------------------------------------------------------------------------------------
# 3. the fitted logistic regression's own number, on every cell of a grid
# ---------------------------------------------------------------------------------------------

def test_fitted_logistic_is_the_ordering_or_one_minus_it_on_every_cell():
    """A real fit at every one of the 220 cells, and the exact relationship checked.

    This is the claim the fast path rests on. A one-predictor logistic regression's own area under
    the curve, scored on the data it was fitted to, is EXACTLY the ordering's area under the curve
    or one minus it, and which of the two is decided by the sign of the fitted slope. If that ever
    stopped holding, the grid the page draws would be a different quantity from the one its own
    documentation claims and nothing would say so.
    """
    power, pain, centers = _synthetic_grid(seed=11)
    y = np.asarray(A._pain_split(pain)[0], dtype=float)
    n_cells = n_exact = n_slope_agrees = 0
    for s in A.BAND_TIME_SWEEP_SECONDS:
        X = power[float(s)]
        unfolded = A.rank_auc_columns(X, y)["auc"]
        got = A.logistic_auc_columns_fitted(X, y, feature_scale="log")
        fitted, slope = got["auc"], got["slope"]
        ok = np.isfinite(fitted) & np.isfinite(unfolded)
        n_cells += int(ok.sum())
        same = np.abs(fitted[ok] - unfolded[ok])
        flip = np.abs(fitted[ok] - (1.0 - unfolded[ok]))
        assert np.all(np.minimum(same, flip) < 1e-9), (
            "a fitted value is neither the ordering's value nor one minus it; "
            f"worst gap {float(np.min([same.max(), flip.max()])):.3g}")
        n_exact += int((np.minimum(same, flip) < 1e-9).sum())
        n_slope_agrees += int(((slope[ok] > 0) == (same < 1e-9)).sum())
    assert n_cells >= 200, f"only {n_cells} cells were fitted; the grid should be about 220"
    assert n_slope_agrees == n_cells, "which of the two it is must follow the fitted slope's sign"
    print(f"OK on all {n_cells} cells the fitted logistic regression's own value is exactly the "
          f"ordering's value or one minus it, and the sign of its slope decides which")


def test_folded_value_is_reported_and_cannot_fall_below_one_half():
    """The folded number is what a fitted regression returns, and 0.5 is a floor for it.

    Reported alongside the unfolded value rather than instead of it, because folding throws the
    direction away and puts a floor at 0.5, which would make 0.5 read as a neutral middle when it
    is not one for that number.
    """
    power, pain, centers = _synthetic_grid(seed=4)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=200, n_boot=300)
    folded = np.asarray([[v for v in row] for row in sw["auc_direction_folded_grid"]], dtype=float)
    fin = np.isfinite(folded)
    assert fin.any()
    assert np.all(folded[fin] >= 0.5 - 1e-12), "the folded value must never fall below 0.5"
    unf = np.asarray([[v for v in row] for row in sw["auc_grid"]], dtype=float)
    assert np.any(unf[np.isfinite(unf)] < 0.5), (
        "the grid the page draws must keep the direction, so some cells must fall below 0.5")
    for row in sw["best_auc_rows"]:
        if row.get("auc") is None:
            continue
        assert abs(row["auc_direction_folded"] - max(row["auc"], 1.0 - row["auc"])) < 1e-12
    print("OK the folded value never falls below 0.5 and the drawn grid keeps both sides of it")


# ---------------------------------------------------------------------------------------------
# 4. THE SWEEP HONOURS THE TOP-OF-PAGE SETTINGS
# ---------------------------------------------------------------------------------------------

def test_sweep_honours_the_top_of_page_settings():
    """Changing a top-of-page setting must change the answer, and by the documented mechanism.

    This is the failure this test exists for: a section that quietly recomputes with its own
    defaults looks right, agrees with nothing above it, and gives no sign of the disagreement. Three
    settings are exercised, each with a consequence that can be checked rather than inspected:

      * how high pain is separated from low, which changes how many reports each side has;
      * the outlier rule, which changes how many measurements were set aside;
      * whether a recording window may serve more than one pain report, which changes how many
        reports get a measurement at all.
    """
    power, pain, centers = _synthetic_grid(seed=7)

    # (a) the split. A median split keeps every report; splitting into thirds drops the middle.
    med = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, strategy="median",
                                       n_perm=100, n_boot=200)
    ter = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, strategy="tertile",
                                       n_perm=100, n_boot=200)
    n_med = max(r["n_pain_reports"] for r in med["best_auc_rows"] if r.get("auc") is not None)
    n_ter = max(r["n_pain_reports"] for r in ter["best_auc_rows"] if r.get("auc") is not None)
    assert n_med > n_ter, (
        f"a median split should keep more reports than splitting into thirds, got {n_med} vs {n_ter}")
    assert "split into thirds" in ter["pain_split_rule"]
    assert "split at" in med["pain_split_rule"]

    # (b) the percentile cuts, when the strategy is the adjustable one.
    wide = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers,
                                        strategy="percentile", low_pct=10.0, high_pct=90.0,
                                        n_perm=100, n_boot=200)
    narrow = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers,
                                          strategy="percentile", low_pct=45.0, high_pct=55.0,
                                          n_perm=100, n_boot=200)
    n_wide = max(r["n_pain_reports"] for r in wide["best_auc_rows"] if r.get("auc") is not None)
    n_narrow = max(r["n_pain_reports"] for r in narrow["best_auc_rows"] if r.get("auc") is not None)
    assert n_narrow > n_wide, (
        f"cuts at 45 and 55 should keep more reports than cuts at 10 and 90, "
        f"got {n_narrow} vs {n_wide}")

    # (c) the outlier rule. Switching it off must set nothing aside and must say so.
    off = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, outlier_n_mad=0.0,
                                       n_perm=100, n_boot=200)
    tight = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, outlier_n_mad=2.0,
                                         n_perm=100, n_boot=200)
    assert off["n_measurements_excluded_as_outliers"] == 0
    assert tight["n_measurements_excluded_as_outliers"] > 0
    assert "switched off" in " ".join(off["notes"])
    assert off["outlier_n_mad"] == 0.0 and tight["outlier_n_mad"] == 2.0

    # (d) the matching controls, checked at the matcher the sweep calls rather than in the abstract.
    cache = _fake_raw_cache(centers, n_tiles=600, seed=9)
    tt = np.asarray(cache["td"]["t"], dtype=float)
    pro = np.asarray([tt[100], tt[101], tt[102]], dtype=float)     # three reports, seconds apart
    strict, s_stats = AV.live_lsb_spectrum_match(pro, cache, tol_s=600.0, td_quantity_s=60.0,
                                                 allow_window_reuse=False)
    reuse, r_stats = AV.live_lsb_spectrum_match(pro, cache, tol_s=600.0, td_quantity_s=60.0,
                                                allow_window_reuse=True)
    assert r_stats["n_td_used"] > s_stats["n_td_used"], (
        "letting a window serve several reports must use more windows than not letting it")
    near, n_stats = AV.live_lsb_spectrum_match(pro, cache, tol_s=3.0, td_quantity_s=300.0)
    far, f_stats = AV.live_lsb_spectrum_match(pro, cache, tol_s=3600.0, td_quantity_s=300.0)
    assert f_stats["n_td_assigned"] > n_stats["n_td_assigned"], (
        "a wider match tolerance must make more windows eligible")
    print(f"OK the settings reach the sweep: median split keeps {n_med} reports against {n_ter} "
          f"for thirds; cuts at 45/55 keep {n_narrow} against {n_wide} for 10/90; the outlier rule "
          f"set aside {tight['n_measurements_excluded_as_outliers']} at 2 deviations and 0 when "
          f"switched off; window reuse used {r_stats['n_td_used']} windows against "
          f"{s_stats['n_td_used']}")


def test_settings_are_echoed_so_a_reader_can_check_them():
    """What the sweep ran under has to be readable off the result, not taken on trust."""
    power, pain, centers = _pure_noise_grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, strategy="percentile",
                                      low_pct=25.0, high_pct=75.0, outlier_n_mad=4.0,
                                      outlier_scale="raw", n_perm=100, n_boot=200)
    assert sw["outlier_n_mad"] == 4.0 and sw["outlier_scale"] == "raw"
    assert "25" in sw["pain_split_rule"] or sw["pain_low_cut"] is not None
    assert "4 median absolute deviations on the raw scale" in " ".join(sw["notes"])
    print("OK the result echoes the settings it ran under")


# ---------------------------------------------------------------------------------------------
# 5. AN INTERVAL SPANNING 0.5 DOES NOT READ AS A NEGATIVE RESULT
# ---------------------------------------------------------------------------------------------

def test_interval_spanning_one_half_reads_as_unsettled_and_never_as_negative():
    """A band whose interval includes 0.5 must be reported as an UNSETTLED question.

    Three surfaces have to agree about it and none of them may read as a negative result: the
    three-word answer, the sentence, and the figure headline. The words that would make it read
    negative are named here explicitly so that a future rewording cannot reintroduce them.
    """
    power, pain, centers = _pure_noise_grid(seed=21, n_reports=40)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=300, n_boot=400)
    spanning = [r for r in sw["best_auc_rows"]
                if r.get("interval_spans_no_discrimination") is True]
    assert spanning, "pure noise at n=40 should leave at least one interval spanning 0.5"

    forbidden = ["no discrimination", "carries nothing", "does not separate", "no relationship",
                 "useless", "no separation", "failed", "negative"]
    for r in spanning:
        assert r["answer"] == A.BAND_PAIN_NOT_RESOLVED, (
            f"an interval spanning 0.5 must be {A.BAND_PAIN_NOT_RESOLVED}, got {r['answer']}")
        assert r["answer"] is not False and r["answer"] is not None
        why = r["why"].lower()
        assert "not settled" in why, f"the sentence must say the question was not settled: {why}"
        assert "not a finding that the band carries nothing" in why
        for bad in forbidden:
            if bad == "carries nothing":
                continue        # appears only inside the sentence that DENIES it, checked above
            assert bad not in why.replace("not a finding that the band carries nothing", ""), (
                f"the sentence for an unsettled row must not contain {bad!r}: {why}")
        assert r["no_relationship_value"] == 0.5
    # The three states stay three states.
    words = {r["answer"] for r in sw["best_auc_rows"]}
    assert words <= {A.BAND_PAIN_ESTABLISHED, A.BAND_PAIN_NOT_RESOLVED, A.BAND_PAIN_NOT_ASSESSED}
    assert True not in words and False not in words and None not in words
    # And the headline, which is the one line a reader might see on its own.
    head = A._sweep_headline_auc(sw).lower()
    assert "0.5" in head
    assert "does not separate" not in head and "no discrimination" not in head
    print(f"OK {len(spanning)} of {len(sw['best_auc_rows'])} band centres have an interval spanning "
          f"0.5; every one is reported as an unsettled question, in the word, the sentence and the "
          f"headline")


def test_not_assessed_is_a_different_state_from_not_settled():
    """A band that produced no number must not be reported as one that produced a weak number."""
    power, pain, centers = _pure_noise_grid(seed=31, n_reports=40)
    for s in power:
        power[s][:, 3] = np.nan          # one band centre with nothing in it at all
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=100, n_boot=200)
    row = sw["best_auc_rows"][3]
    assert row["answer"] == A.BAND_PAIN_NOT_ASSESSED
    assert row.get("auc") is None, "a band with nothing in it must carry no value, not 0.5"
    assert "absent measurement" in row["why"]
    assert "not a measurement showing no discrimination" in row["why"]
    crow = sw["best_correlation_rows"][3]
    assert crow["answer"] == A.BAND_PAIN_NOT_ASSESSED and crow.get("pearson_r") is None
    print("OK a band that produced no number is 'not assessed', carries no value, and says so")


# ---------------------------------------------------------------------------------------------
# 6. the colour scales
# ---------------------------------------------------------------------------------------------

def test_colour_scales_are_centred_on_the_right_no_relationship_value():
    """0.5 for high-versus-low pain, 0 for the correlation, and the figures say so.

    A diverging scale centred anywhere but 0.5 on the high-versus-low-pain grid would make a band
    that discriminates nothing look like a result, which is the specific error this asserts against.
    """
    power, pain, centers = _synthetic_grid(seed=13)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=200, n_boot=300)
    figs = A.band_time_sweep_figures(sw)
    assert set(figs) == {"correlation", "auc"}
    auc = figs["auc"]["data"][0]
    corr = figs["correlation"]["data"][0]
    assert auc["zmid"] == 0.5, f"the high-versus-low-pain scale must be centred on 0.5, got {auc['zmid']}"
    assert corr["zmid"] == 0.0, f"the correlation scale must be centred on 0, got {corr['zmid']}"
    assert auc["zmin"] < 0.5 < auc["zmax"], "0.5 must sit inside the scale, not at one end"
    assert corr["zmin"] < 0.0 < corr["zmax"]
    # The value is printed in every cell while the grid is small enough to read.
    assert "text" in auc and auc.get("texttemplate") == "%{text}"
    assert len(auc["text"]) == len(sw["integration_seconds_delivered"])
    assert len(auc["text"][0]) == len(sw["center_freqs_hz"])
    # The vertical axis is labelled with the length DELIVERED, and says so when it differs.
    ylab = figs["auc"]["layout"]["yaxis"]
    assert "Seconds of recording averaged into one measurement" in ylab["title"]["text"]
    assert any("asked" in str(v) for v in auc["y"]), (
        "a length that could not be delivered exactly must say so on the axis")
    # Both headlines are DERIVED: they carry a number that is in the result.
    for key in ("correlation", "auc"):
        title = figs[key]["layout"]["title"]["text"]
        assert any(ch.isdigit() for ch in title), f"the {key} headline states no number: {title}"
    print("OK the high-versus-low-pain scale is centred on 0.5 and the correlation scale on 0; "
          "every cell prints its value; both headlines carry numbers from the result")


def test_the_optimism_note_is_in_the_panel_not_only_in_a_caption():
    """The best-of-ten warning has to travel with the numbers."""
    power, pain, centers = _synthetic_grid(seed=17)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=200, n_boot=300)
    first_two = " ".join(sw["notes"][:2]).lower()
    assert "largest of the ten lengths" in first_two
    assert "optimistic" in first_two or "larger than" in first_two
    assert "0.5, not 0" in " ".join(sw["notes"])
    # And it is welded into both figures, so a screenshot of one carries it.
    figs = A.band_time_sweep_figures(sw)
    for key in ("correlation", "auc"):
        foot = figs[key]["layout"]["annotations"][0]["text"].lower()
        assert "largest of the ten lengths" in foot and "0.5, not 0" in foot
    print("OK the best-of-ten warning and the 0.5 note are in the notes and welded into both figures")


# ---------------------------------------------------------------------------------------------
# 7. the reported maximum is judged against the shuffled best of ten
# ---------------------------------------------------------------------------------------------

def test_a_value_that_does_not_beat_the_shuffled_best_of_ten_is_not_established():
    """A selected maximum must clear the distribution of selected maxima, not of single values.

    Without this gate the panel contradicted itself on the live record: a row read "established"
    because its own interval excluded the no-relationship value, while its own figure headline said
    the value does not clear what the same best-of-ten choice reaches on shuffled pain scores. Both
    statements were about one number.
    """
    power, pain, centers = _pure_noise_grid(seed=41, n_reports=50)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=500, n_boot=500)
    gated = 0
    for r in sw["best_auc_rows"] + sw["best_correlation_rows"]:
        null_v = r["no_relationship_value"]
        obs = r.get("auc", r.get("pearson_r"))
        p95 = r.get("shuffled_best_of_windows_p95")
        if obs is None or p95 is None:
            continue
        if abs(obs - null_v) <= abs(p95 - null_v):
            assert r["answer"] != A.BAND_PAIN_ESTABLISHED, (
                f"a value {obs} no further from {null_v} than the shuffled {p95} must not be "
                f"established")
            gated += 1
        if r["answer"] == A.BAND_PAIN_ESTABLISHED:
            assert abs(obs - null_v) > abs(p95 - null_v)
    assert gated > 0, "on pure noise some rows must be held back by the shuffled reference"
    # The shuffled reference itself has to be above the no-relationship value, since the choice it
    # models is a maximum over ten lengths AND over both directions.
    for r in sw["best_auc_rows"]:
        if r.get("shuffled_best_of_windows_p95") is not None:
            assert r["shuffled_best_of_windows_p95"] > 0.5
    for r in sw["best_correlation_rows"]:
        if r.get("shuffled_best_of_windows_p95") is not None:
            assert r["shuffled_best_of_windows_p95"] > 0.0
    print(f"OK {gated} rows on pure noise are held back by the shuffled best-of-ten reference "
          f"despite their own intervals; no row is established without clearing it")


def test_a_planted_relationship_is_found_at_the_right_band():
    """The sweep has to find a relationship that is really there, or the honesty gates are just
    a machine for saying nothing."""
    power, pain, centers = _synthetic_grid(seed=23, planted_col=6, strength=1.1)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=500, n_boot=500)
    rows = [r for r in sw["best_correlation_rows"] if r.get("pearson_r") is not None]
    top = max(rows, key=lambda r: abs(r["pearson_r"]))
    assert abs(top["band_center_hz"] - float(centers[6])) < 1e-9, (
        f"the planted band is at {centers[6]} Hz but the strongest is at {top['band_center_hz']}")
    assert top["answer"] == A.BAND_PAIN_ESTABLISHED
    assert top["p_selection_aware"] is not None and top["p_selection_aware"] < 0.05
    arows = [r for r in sw["best_auc_rows"] if r.get("auc") is not None]
    atop = max(arows, key=lambda r: abs(r["auc"] - 0.5))
    assert abs(atop["band_center_hz"] - float(centers[6])) < 1e-9
    assert atop["answer"] == A.BAND_PAIN_ESTABLISHED
    print(f"OK the planted band at {centers[6]:g} Hz is found by both numbers "
          f"(r={top['pearson_r']:+.3f}, high-vs-low {atop['auc']:.3f}) and clears the shuffled "
          f"reference")


# ---------------------------------------------------------------------------------------------
# 8. the two matrices and the full grid
# ---------------------------------------------------------------------------------------------

def test_the_two_matrices_and_the_full_grid_come_out_readable():
    """One row per band centre in each matrix, one row per cell in the grid, and the columns a
    reader needs in order to interpret a row present on every row."""
    power, pain, centers = _synthetic_grid(seed=29)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=200, n_boot=300)
    corr, auc, grid = A.band_time_sweep_tables(sw)
    n_c = len(centers)
    n_t = len(sw["integration_seconds_delivered"])
    assert len(corr) == n_c and len(auc) == n_c
    assert len(grid) == n_c * n_t, f"the grid should have {n_c * n_t} rows, got {len(grid)}"
    for need in ("band_center_hz", "integration_seconds_delivered", "integration_seconds_requested",
                 "no_relationship_value", "answer", "why", "n_pain_reports",
                 "shuffled_best_of_windows_p95", "chosen_as_best_of_n_windows"):
        assert need in corr.columns, f"the correlation matrix is missing {need}"
        assert need in auc.columns, f"the high-versus-low-pain matrix is missing {need}"
    assert set(auc["no_relationship_value"].dropna().unique()) == {0.5}
    assert set(corr["no_relationship_value"].dropna().unique()) == {0.0}
    for need in ("pearson_r", "auc", "auc_direction_folded", "integration_seconds_delivered",
                 "band_fully_inside_8_to_30_hz", "auc_no_relationship_value"):
        assert need in grid.columns, f"the full grid is missing {need}"
    assert not any(c.startswith("_") for c in auc.columns), (
        "no private bookkeeping column may reach a saved file")
    # The band flag is arithmetic and has to be right: a 5 Hz band centred on 10.5 Hz runs 8 to 13.
    inside = grid[grid["band_center_hz"] == 10.5]["band_fully_inside_8_to_30_hz"]
    assert bool(inside.iloc[0]) is True
    outside = grid[grid["band_center_hz"] == 8.5]["band_fully_inside_8_to_30_hz"]
    assert bool(outside.iloc[0]) is False, "a band centred on 8.5 Hz runs down to 6 Hz"
    print(f"OK the two matrices have {n_c} rows each, the full grid {len(grid)}, and every row "
          f"carries the value that means no relationship for its own quantity")


def test_an_empty_input_is_a_reason_not_a_crash():
    """Missing inputs come back as a stated reason with no numbers, never as a value near the
    no-relationship point."""
    centers = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
    empty = A.band_time_sweep_from_power({}, np.asarray([1.0, 2.0, 3.0]), center_freqs_hz=centers)
    assert empty["answer"] == A.BAND_PAIN_NOT_ASSESSED and empty["why"]
    assert empty["correlation_grid"] == [] and empty["auc_grid"] == []
    no_bands = A.band_time_sweep_from_power({1.0: np.zeros((3, 0))}, np.asarray([1.0, 2.0, 3.0]),
                                            center_freqs_hz=np.asarray([]))
    assert no_bands["answer"] == A.BAND_PAIN_NOT_ASSESSED and "nothing to sweep" in no_bands["why"]
    assert A.band_time_sweep_figures(empty) == {}
    print("OK a missing input is reported as a reason with no numbers")


def test_band_centres_come_from_the_cache_grid_not_from_a_wish():
    """The sweep covers the band centres the cached spectra actually hold inside 8 to 30 Hz.

    Asking for whole-hertz centres when the cache holds half-hertz ones would silently return
    nothing, so the span is intersected with the cache's own list and the list used is reported.
    """
    cache_grid = np.arange(2.5, 100.0, 1.0)
    got = A.sweep_center_freqs(cache_grid)
    assert got.size == 22, f"expected 22 centres between 8 and 30 Hz, got {got.size}"
    assert abs(got[0] - 8.5) < 1e-9 and abs(got[-1] - 29.5) < 1e-9
    assert np.all(np.diff(got) == 1.0)
    # A different cache grid gives different centres, rather than the same wished-for list.
    whole = A.sweep_center_freqs(np.arange(1.0, 100.0, 1.0))
    assert abs(whole[0] - 8.0) < 1e-9 and abs(whole[-1] - 30.0) < 1e-9 and whole.size == 23
    assert A.sweep_center_freqs(np.asarray([50.0, 60.0])).size == 0
    print(f"OK the sweep takes its band centres from the cache: {got.size} centres from "
          f"{got[0]:g} to {got[-1]:g} Hz on the module's own grid, {whole.size} on a whole-hertz one")


if __name__ == "__main__":
    test_delivered_length_matches_the_matcher_not_the_request()
    test_notes_declare_the_lengths_that_could_not_be_delivered()
    test_vectorised_outlier_rule_matches_the_scalar_one()
    test_fitted_logistic_is_the_ordering_or_one_minus_it_on_every_cell()
    test_folded_value_is_reported_and_cannot_fall_below_one_half()
    test_sweep_honours_the_top_of_page_settings()
    test_settings_are_echoed_so_a_reader_can_check_them()
    test_interval_spanning_one_half_reads_as_unsettled_and_never_as_negative()
    test_not_assessed_is_a_different_state_from_not_settled()
    test_colour_scales_are_centred_on_the_right_no_relationship_value()
    test_the_optimism_note_is_in_the_panel_not_only_in_a_caption()
    test_a_value_that_does_not_beat_the_shuffled_best_of_ten_is_not_established()
    test_a_planted_relationship_is_found_at_the_right_band()
    test_the_two_matrices_and_the_full_grid_come_out_readable()
    test_an_empty_input_is_a_reason_not_a_crash()
    test_band_centres_come_from_the_cache_grid_not_from_a_wish()
    print("All band-by-length-of-signal sweep tests passed.")
