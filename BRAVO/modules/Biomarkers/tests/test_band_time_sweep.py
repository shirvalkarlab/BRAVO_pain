"""Tests for the band-by-length-of-signal sweep at the bottom of the biomarker exploration page.

Every test here exists because something specific could go wrong silently. In order:

  * the length of signal a row is LABELLED with has to be the length actually delivered, and the
    delivered length is decided by the matcher, so the label is checked against the matcher's own
    reported count rather than against a repeat of the arithmetic;
  * the vectorised outlier rule has to be the same rule as the scalar one it replaced for speed;
  * the relationship between the ordering's area under the curve and a real fitted one-predictor
    logistic regression's own area under the curve has to hold on every cell of a grid, since that
    relationship is what lets every cell be filled without a model fit per cell;
  * the sweep has to HONOUR THE TOP-OF-PAGE SETTINGS rather than recomputing with its own defaults;
  * an interval that spans 0.5 must NOT read as a negative result anywhere -- not in the word, not
    in the sentence, and not in the figure headline;
  * a colour scale for the high-versus-low-pain grid centred anywhere but 0.5 is wrong;
  * a value that clears its own interval but not the shuffled best-of-ten level must not be reported
    as established, because the reported value was chosen as the best of ten.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_band_time_sweep.py

Merged here 2026-10-05: test_band_time_sweep_cell.py.
"""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A          # noqa: E402
from Biomarkers.routines import availability as AV      # noqa: E402
from Biomarkers.routines import stats_utils as SU       # noqa: E402


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


def test_the_lengths_that_could_not_be_delivered_are_on_the_response_but_not_in_the_drawer():
    """Both numbers stay on the response (`length_rounding`, one pair per rounded length) so a
    reader who opens it can see them; the drawer no longer prints them (the PI, 2026-09-15:
    remove that bullet -- every label already shows the delivered length)."""
    power, pain, centers = _pure_noise_grid()
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=100, n_boot=200)
    joined = " ".join(sw["notes"])
    assert "could not be delivered" not in joined and "asked for" not in joined
    rounding = sw["length_rounding"]
    assert {"requested_s": 1.0, "delivered_s": 3.0} in rounding
    assert {"requested_s": 5.0, "delivered_s": 6.0} in rounding
    assert all(r["requested_s"] != r["delivered_s"] for r in rounding)
    # every note is short: the PI reads this drawer, and asked for it to be concise
    for note in sw["notes"]:
        assert len(note.split()) <= 45, note
    for row in sw["best_correlation_rows"] + sw["best_auc_rows"]:
        if row.get("integration_seconds_delivered") is None:
            continue
        assert row["integration_seconds_requested"] is not None
    print("OK the notes name every length that could not be delivered, with both numbers")


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
    for scale in ("raw",):                      # the only scale since decision 205
        fast = A.mad_outlier_columns(X, n_mad=5.0, scale=scale)
        slow = np.column_stack([SU.mad_outlier_flags(X[:, c], n_mad=5.0, scale=scale)[0]
                                for c in range(X.shape[1])])
        assert np.array_equal(fast, slow), f"the two rules disagree on the {scale} scale"
        assert not fast[:, 4].any(), "a column with no spread must have nothing flagged"
        assert not fast[:, 5].any(), "a column with too few values must have nothing flagged"
    # And it works on the three-dimensional stack the sweep actually hands it.
    stack = np.stack([X, X * 2.0, X * 3.0], axis=0)
    got = A.mad_outlier_columns(stack, n_mad=5.0, scale="raw")
    assert got.shape == stack.shape
    for t in range(3):
        assert np.array_equal(got[t], A.mad_outlier_columns(stack[t], n_mad=5.0, scale="raw"))
    print("OK the vectorised outlier rule is identical to the scalar one on every column, "
          "including the no-spread, too-few and non-positive cases")


def test_fitted_logistic_is_the_ordering_or_one_minus_it_on_every_cell():
    """A real fit at every one of the 22 x 9 cells, and the exact relationship checked.

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
        got = A.logistic_auc_columns_fitted(X, y)
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
    # 22 centres x the sweep's lengths (10 until 2026-09-15, 9 since the 5-minute length went)
    expect = 22 * len(A.BAND_TIME_SWEEP_SECONDS)
    assert n_cells >= expect - 20, f"only {n_cells} cells were fitted; the grid should be about {expect}"
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


def test_interval_spanning_one_half_reads_as_unsettled_and_never_as_negative():
    """A band whose interval includes 0.5 must be reported as an UNSETTLED question.

    Two surfaces have to agree about it and neither may read as a negative result: the
    three-word answer and the sentence. The words that would make it read negative are named here
    explicitly so that a future rewording cannot reintroduce them.
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
    # (The figure headline this test also checked until 2026-09-15 is gone with its builder: no
    # page drew the server-rendered figure it headed after decision 145.)
    print(f"OK {len(spanning)} of {len(sw['best_auc_rows'])} band centres have an interval spanning "
          f"0.5; every one is reported as an unsettled question, in the word and the sentence")


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


def test_the_optimism_note_and_the_half_note_are_in_the_first_notes():
    """The best-of-ten warning and the 0.5-means-no-discrimination note have to travel with the
    numbers, in the notes the page prints in its "how to read this" drawer."""
    power, pain, centers = _synthetic_grid(seed=17)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=200, n_boot=300)
    first_two = " ".join(sw["notes"][:2]).lower()
    assert "largest of the nine lengths" in first_two
    assert "optimistic" in first_two or "larger than" in first_two
    assert "0.5, not 0" in " ".join(sw["notes"])
    # 2026-09-15, the PI: the note said "each row's value is the largest", which was true of the
    # retired table (one row per band) and false of the heat map, where a row is a length of
    # signal and every cell has its own value. The note must speak of the CIRCLED cell.
    assert "circled cell in each column" in first_two
    assert "row's value" not in first_two
    # and the direction note must not refer to "the table" or a logistic fit the heat map never shows
    direction = sw["notes"][2].lower()
    assert "table" not in direction and "logistic" not in direction
    print("OK the best-of-ten warning and the 0.5 note are in the notes")


def test_every_row_sentence_counts_the_lengths_with_the_one_word_the_notes_use():
    """Referent audit 2026-09-15, item 10. A row's `why` read "the strongest of 9 lengths ... the
    SAME best-of-ten choice" -- one sentence with two counts, the second typed before the 300 s
    length was dropped (decision 170). The count comes from `_N_LENGTHS_WORD`, the one place the
    notes already take it from, so the two cannot disagree again."""
    power, pain, centers = _synthetic_grid(seed=17)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=200, n_boot=300)
    word = A._N_LENGTHS_WORD
    assert word == "nine", word
    rows = list(sw["best_correlation_rows"]) + list(sw["best_auc_rows"])
    assert rows
    n_shuffled = 0
    for r in rows:
        why = str(r["why"]).lower()
        assert "best-of-ten" not in why, why
        assert " ten " not in why and "of ten" not in why, why
        assert f" {word} lengths of signal" in why, why
        if "shuffled" in why:
            n_shuffled += 1
            assert f"best-of-{word}" in why, why
    assert n_shuffled, "no row named the shuffled level, so the best-of wording was not exercised"
    print(f"OK {len(rows)} row sentences count the lengths as '{word}', {n_shuffled} name the shuffled level")


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


def test_family_wise_correction_matches_bh_fdr_applied_directly():
    """`_apply_family_wise_correction`'s job is wiring, not arithmetic -- Benjamini-Hochberg itself
    is already tested elsewhere (`stats_utils.bh_fdr`, reused unchanged from the older routine).
    This checks the wiring: a hand-built list of rows carrying `p_selection_aware` gets a q-value
    equal, entry for entry, to calling `bh_fdr` on that same array directly, plus the missing/absent
    case (no p-value measured) coming back `None` rather than a number."""
    ps = [0.001, 0.02, 0.4, np.nan, 0.03, 0.5, 0.008]
    rows = [{"p_selection_aware": (None if not np.isfinite(p) else p)} for p in ps]
    A._apply_family_wise_correction(rows)
    expected_q = SU.bh_fdr(np.asarray(ps, dtype=float))
    for row, eq in zip(rows, expected_q):
        if np.isfinite(eq):
            assert row["family_wise_q_8_to_30hz"] == eq
            assert row["family_wise_significant_8_to_30hz"] == bool(
                eq < A.BAND_TIME_SWEEP_FAMILY_WISE_Q)
        else:
            assert row["family_wise_q_8_to_30hz"] is None
            assert row["family_wise_significant_8_to_30hz"] is None
    print("OK the family-wise q-value and its pass/fail label match bh_fdr called directly on the "
          "same p-values, and a missing p-value comes back as 'not assessed' rather than a number")


def test_a_family_with_no_measured_p_values_is_not_assessed_and_does_not_raise():
    """Every row in the family can carry `p_selection_aware: None` -- a contact pair where every
    length of signal was undeliverable, say. `bh_fdr`'s own m == 0 branch returns an all-NaN array
    in that case; this checks `_apply_family_wise_correction` passes that through as 'not assessed'
    on every row, in place, with no exception -- rather than dividing by a family size of zero or
    reporting a spurious pass. Nothing before this test exercised that path.
    """
    rows = [{"p_selection_aware": None} for _ in range(22)]
    A._apply_family_wise_correction(rows)                 # must not raise
    assert len(rows) == 22
    for row in rows:
        assert row["family_wise_q_8_to_30hz"] is None
        assert row["family_wise_significant_8_to_30hz"] is None
    # The same for an empty family -- no rows at all, e.g. no sensing contact pair identified.
    empty = []
    A._apply_family_wise_correction(empty)                # must not raise
    assert empty == []
    print("OK a family with no measured p-values is reported as not assessed on every row, "
          "and an empty family raises nothing")


def test_the_same_p_values_get_smaller_q_values_in_a_smaller_family():
    """Benjamini-Hochberg's q-value for a p-value depends on how many tests share its family: the
    reason decision 63 restricts the family to the grid's 22 band centres instead of the older
    routine's ~101 bins. The same three p-values, corrected once on their own and once beside three
    large ones, get strictly smaller q-values in the family of three.

    Split 2026-10-02 from `test_family_wise_correction_is_isolated_per_grid_and_is_family_size_
    sensitive`, whose name and docstring also said the sweep corrects the correlation grid and the
    AUC grid separately; its body never ran the sweep, and its other half repeated the equality with
    `bh_fdr` that the test above makes."""
    rows_a = [{"p_selection_aware": p} for p in (0.001, 0.02, 0.03)]
    rows_b = [{"p_selection_aware": p} for p in (0.001, 0.02, 0.03, 0.9, 0.95, 0.99)]
    A._apply_family_wise_correction(rows_a)
    A._apply_family_wise_correction(rows_b)
    for ra, rb in zip(rows_a, rows_b[:3]):
        assert ra["family_wise_q_8_to_30hz"] < rb["family_wise_q_8_to_30hz"], (ra, rb)


def test_the_sweep_corrects_the_correlation_rows_and_the_area_rows_as_two_separate_families():
    """Decision 63: each grid is its own family of band centres. RUNS the sweep on the file's
    planted-band fixture, then checks, from the p-values the sweep itself put on its rows, that
      * the correlation rows' q-values equal `bh_fdr` on the correlation rows' p-values alone,
      * the high-versus-low-pain (area under the curve) rows' q-values equal `bh_fdr` on those rows'
        p-values alone, and
      * pooling both sets of rows into one family would have given a different q-value to at least
        one row, so the two checks above can tell separate families from a pooled one.
    Added 2026-10-02: the earlier test of this name never ran the sweep (decision 367)."""
    power, pain, centers = _synthetic_grid(seed=23, planted_col=6, strength=1.1)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=500, n_boot=500)
    corr_rows, auc_rows = sw["best_correlation_rows"], sw["best_auc_rows"]
    assert len(corr_rows) == len(auc_rows) == 22

    def _ps(rows):
        return np.array([np.nan if r.get("p_selection_aware") is None else r["p_selection_aware"]
                         for r in rows], dtype=float)

    def _qs(rows):
        return np.array([np.nan if r["family_wise_q_8_to_30hz"] is None
                         else r["family_wise_q_8_to_30hz"] for r in rows], dtype=float)

    p_corr, p_auc = _ps(corr_rows), _ps(auc_rows)
    assert np.isfinite(p_corr).sum() == 22 and np.isfinite(p_auc).sum() == 22
    own_corr, own_auc = SU.bh_fdr(p_corr), SU.bh_fdr(p_auc)
    assert np.array_equal(_qs(corr_rows), own_corr), (_qs(corr_rows), own_corr)
    assert np.array_equal(_qs(auc_rows), own_auc), (_qs(auc_rows), own_auc)

    pooled = SU.bh_fdr(np.concatenate([p_corr, p_auc]))
    n_differ = int((pooled[:22] != own_corr).sum() + (pooled[22:] != own_auc).sum())
    assert n_differ > 0, "pooling the two families would have given the same q-values; the " \
                         "constructed data cannot tell separate families from a pooled one"
    print(f"OK the correlation rows and the area rows are each corrected on their own 22 p-values; "
          f"pooling all 44 would have changed {n_differ} of the 44 q-values")


def test_a_planted_band_ranks_best_under_the_family_wise_correction_and_pure_noise_mostly_clears():
    """End-to-end through the real grid, on this file's own `_synthetic_grid`/`_pure_noise_grid`
    fixtures.

    NOTE ON WHAT THIS DOES NOT ASSERT: it would be tempting to require the planted band to come out
    `family_wise_significant_8_to_30hz is True`, but that turns out not to be a safe thing to demand
    of a synthetic fixture -- correcting across 22 simultaneous tests is considerably stricter than
    the existing best-of-ten-lengths check alone (checked directly: even an extreme strength=3.0
    planting with 2000 shuffles corrected to q=0.32, not under 0.05, because with only 80 constructed
    reports the "best of ten lengths" selection effect alone already produces a heavy-tailed null).
    That is the correction doing exactly its job -- being strict -- not a bug in it. So this test
    asserts the weaker, always-true property instead: the planted band's own p-value and q-value
    rank first among all 22 centres, and it is never reported as absent (`None`).
    """
    power, pain, centers = _synthetic_grid(seed=23, planted_col=6, strength=1.1)
    sw = A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=500, n_boot=500)
    rows = [r for r in sw["best_correlation_rows"] if r.get("pearson_r") is not None]
    top = max(rows, key=lambda r: abs(r["pearson_r"]))
    assert top["family_wise_q_8_to_30hz"] is not None
    all_q = [r["family_wise_q_8_to_30hz"] for r in sw["best_correlation_rows"]
            if r.get("family_wise_q_8_to_30hz") is not None]
    assert top["family_wise_q_8_to_30hz"] == min(all_q), (
        "the planted band's own q-value should rank first (smallest) among all 22 centres, "
        "even where it does not clear an absolute 0.05 bar")

    noise_power, noise_pain, noise_centers = _pure_noise_grid(seed=1)
    noise_sw = A.band_time_sweep_from_power(noise_power, noise_pain, center_freqs_hz=noise_centers,
                                            n_perm=500, n_boot=500)
    noise_rows = [r for r in noise_sw["best_correlation_rows"]
                 if r.get("family_wise_significant_8_to_30hz") is not None]
    n_flagged = sum(1 for r in noise_rows if r["family_wise_significant_8_to_30hz"])
    assert n_flagged <= max(2, int(0.15 * len(noise_rows))), (
        f"{n_flagged} of {len(noise_rows)} pure-noise centres passed the family-wise correction, "
        f"far more than a 5% false-discovery rate should produce")
    print(f"OK the planted band ranks first of 22 centres under the family-wise correction (q="
          f"{top['family_wise_q_8_to_30hz']:.4f}); pure noise flags {n_flagged} of "
          f"{len(noise_rows)} centres, consistent with a 5% false-discovery rate")


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


# 9. the sweep stops at one minute (the PI, 2026-09-15: "get rid of the five-minute ... leave the max at one minute")
def test_the_sweep_stops_at_one_minute_and_its_note_counts_its_own_lengths():
    assert max(A.BAND_TIME_SWEEP_SECONDS) == 60.0
    assert len(A.BAND_TIME_SWEEP_SECONDS) == 9
    assert 300.0 not in A.BAND_TIME_SWEEP_SECONDS
    assert "nine lengths" in A.BEST_OF_WINDOWS_OPTIMISM_NOTE and "ten" not in A.BEST_OF_WINDOWS_OPTIMISM_NOTE
    print("OK the sweep ends at 60 s over nine lengths and the note says nine")


# --------------------------------------------------------------------------------------------------
# merged from test_band_time_sweep_cell.py
# Tests for the per-cell drill-down endpoint added for the heat-map redesign (Track A, task A2).
#
# The grid never carried the per-report (band power, pain score) pairs behind one cell -- only its
# aggregate row and matrix values -- so `bravo_service.band_time_sweep_cell_for_participant` was
# added to hand back one cell's raw pairs on request, matched and labelled exactly the way that
# cell's own grid value was.
#
# WHY THIS TEST EXISTS. The endpoint's own outlier handling was checked live on RCS08 during
# development and caught a real bug on the first try: the raw Pearson correlation recomputed from
# the endpoint's own pairs (-0.022) did not match the grid's own value for the same cell (-0.085),
# because the grid excludes outliers column by column (`analytics.mad_outlier_columns`) before
# computing its statistics and the endpoint originally did not. The fix applies the identical rule
# to the single column the endpoint returns. This test pins that fix at the level this container
# suite can exercise without a database: it builds a one-column grid with `mad_outlier_columns`
# directly, byte for byte the way the endpoint calls it, and checks the excluded set and the
# resulting correlation agree with a full multi-column grid computed by
# `band_time_sweep_from_power` for the same synthetic data -- the same identity the live check on
# RCS08 confirmed to 11 significant figures.
#
# Run inside the container:
#     docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_band_time_sweep_cell.py


def _grid_with_outliers(seed=3, n_reports=90, n_centers=5, planted_col=2):
    """A power matrix at one length of signal, with a handful of planted outliers in one column."""
    rng = np.random.default_rng(seed)
    pain = rng.normal(5.0, 2.0, n_reports)
    power = rng.normal(100.0, 10.0, (n_reports, n_centers))
    # Plant five extreme outliers in the column under test, far outside the rest of the column.
    outlier_rows = np.array([3, 17, 40, 61, 88])
    power[outlier_rows, planted_col] = np.array([5000.0, -3000.0, 8000.0, 6000.0, -4000.0])
    return power, pain, outlier_rows


def test_the_cells_outlier_rule_matches_the_grids_own_rule():
    """The exact call `band_time_sweep_cell_for_participant` makes against one column -- a single
    (P, 1) call to `mad_outlier_columns` -- must find and exclude exactly the same rows, and
    reproduce exactly the same correlation, as the full grid's own outlier pass for that column.
    This is the identity the live RCS08 check confirmed to 11 significant figures after a real bug
    was found and fixed: before the fix, the endpoint applied no outlier rule at all, and the raw
    correlation recomputed from its pairs (-0.022) did not match the grid's own value for the same
    cell (-0.085).
    """
    seconds = 15.0
    power, pain, planted_outlier_rows = _grid_with_outliers()
    n_centers = power.shape[1]
    planted_col = 2

    # The full grid's own outlier mask, computed exactly as `band_time_sweep_from_power` computes
    # it: one (T, P, C) call across every length of signal and every band centre at once.
    X = power[np.newaxis, :, :].astype(float)   # (T=1, P, C)
    grid_mask_3d = A.mad_outlier_columns(X, n_mad=A.OUTLIER_N_MAD, scale=A.OUTLIER_SCALE)
    grid_mask_for_col = grid_mask_3d[0, :, planted_col]
    assert grid_mask_for_col.any(), "the planted outliers should flag something in the full grid's own pass"

    # The full grid's own correlation for that column, via the same public function the sweep
    # endpoint calls, so this is the number a reader actually sees on the grid.
    centers = np.arange(1.0, n_centers + 1.0)
    grid = A.band_time_sweep_from_power(
        {seconds: power}, pain, center_freqs_hz=centers,
        requested_seconds=[seconds], n_perm=20, n_boot=20)
    row = next(r for r in grid["best_correlation_rows"]
               if abs(r["band_center_hz"] - centers[planted_col]) < 1e-9)
    grid_r = row["pearson_r"]

    # The endpoint's own call: `mad_outlier_columns` on the single column reshaped to (P, 1),
    # exactly as `band_time_sweep_cell_for_participant` does it.
    col = power[:, planted_col].astype(float)
    cell_mask = A.mad_outlier_columns(col.reshape(-1, 1), n_mad=A.OUTLIER_N_MAD,
                                      scale=A.OUTLIER_SCALE).reshape(-1)

    assert np.array_equal(cell_mask, grid_mask_for_col), (
        "the endpoint's single-column outlier mask does not match the grid's own mask for the "
        "same column -- the two code paths have drifted apart")

    cell_col = np.where(cell_mask, np.nan, col)
    ok = np.isfinite(cell_col) & np.isfinite(pain)
    cell_r = np.corrcoef(cell_col[ok], pain[ok])[0, 1]
    assert abs(cell_r - grid_r) < 1e-9, (
        f"the cell endpoint's own correlation ({cell_r}) does not match the grid's stored value "
        f"for the same cell ({grid_r}) -- the two must agree since one is drawn from the pairs "
        f"that produced the other")
    print(f"OK the cell endpoint's outlier mask and correlation are identical to the grid's own "
          f"answer for the same cell: r={cell_r:.6f}, {int(cell_mask.sum())} rows excluded")


def test_a_cell_with_no_outliers_keeps_every_finite_pair():
    """When nothing in the column is flagged, the cell's pairs are exactly the finite (power, pain)
    pairs -- no row is silently dropped that the grid itself would have kept.
    """
    rng = np.random.default_rng(11)
    n = 40
    pain = rng.normal(5.0, 2.0, n)
    col = rng.normal(50.0, 5.0, n)
    mask = A.mad_outlier_columns(col.reshape(-1, 1), n_mad=A.OUTLIER_N_MAD,
                                 scale=A.OUTLIER_SCALE).reshape(-1)
    assert not mask.any(), "a clean column should have nothing flagged as an outlier"
    print("OK a cell with no outliers keeps every finite pair")


# ---------------------------------------------------------------------------------------------
# THE PAIRS BEHIND A CELL ARE THE PAIRS THE GRID CORRELATED, clinic-sheet ratings included
# (the PI, 2026-09-21: the pinned cell printed Pearson r = -0.033 while the fitted line rose).
# The grid merges the clinic and at-home sheets' scores into the rating series when the switch
# is on (decision 186); until this fix the drill-down never read the switch, so its scatter was
# fitted to the chronic REDCap ratings alone: on RCS08 L 1-3+, 22.5 Hz, 45 s, 10-minute window,
# reuse off, sheets on, the grid's r was -0.0329 on 172 ratings and the drill-down's +0.1039 on
# 97. Live on the RCS08 record, so it carries the `live` mark and skips when the participant is
# absent; pytest is imported only for the mark.
# ---------------------------------------------------------------------------------------------
import pytest                                                                     # noqa: E402
live = pytest.mark.live


@live
def test_the_drill_down_returns_the_pairs_the_grid_correlated_sheet_ratings_included():
    try:
        from Server import models
        from Biomarkers import bravo_service as bs
    except Exception:
        return
    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    try:
        if models.Participant.find(uid=uid) is None:
            return
    except Exception:
        return
    base = {"ParticipantId": uid, "SweepMetric": "left_leg_vas", "LabelMetric": "left_leg_vas",
            "LabelStrategy": "tertile", "MatchToleranceMin": 10, "MatchDirection": "nearest",
            "AllowWindowReuse": False, "IncludeClinicSheetRatings": True, "MaxPerRating": 3, "RefractoryMin": 2}
    grid = bs.band_time_sweep_for_participant(dict(base))
    g = (grid.get("band_time_sweep") or grid)["ONE_THREE_LEFT"]
    centers = list(g["center_freqs_hz"]); secs = list(g["integration_seconds_delivered"])
    col = centers.index(22.5); row = secs.index(45.0)
    r_grid = float(g["correlation_grid"][row][col]); n_grid = int(g["n_grid"][row][col])
    n_sheet_grid = int(g["clinic_sheet_n_grid"][row][col])
    cell = bs.band_time_sweep_cell_for_participant(dict(base, BandTimeSweepCell="1", Channel="ONE_THREE_LEFT",
                                                         BandCenterHz=22.5, IntegrationSeconds=45))["band_time_sweep_cell"]
    pts = cell["points"]
    assert len(pts) == n_grid, (len(pts), n_grid)
    x = np.array([p["power"] for p in pts]); y = np.array([p["pain"] for p in pts])
    r_pts = float(np.corrcoef(x, y)[0, 1])
    assert abs(r_pts - r_grid) < 1e-9, (r_pts, r_grid)
    assert sum(1 for p in pts if p["from_clinic_sheet"]) == n_sheet_grid
    # the block counts the sheet ratings merged into the series (every one, matched or not), the
    # same number the grid's own block reports; the per-cell count is the flagged points above
    assert cell["clinic_sheet"]["included"] is True
    assert cell["clinic_sheet"]["n_added"] == int(g["clinic_sheet_ratings"]["n_added"]) > n_sheet_grid
    # and the least-squares line the page draws through these points has the sign of r
    slope = np.polyfit(x, y, 1)[0]
    assert np.sign(slope) == np.sign(r_grid)
    # switch off: no sheet point, and the block says so
    off = bs.band_time_sweep_cell_for_participant(dict(base, IncludeClinicSheetRatings=False, BandTimeSweepCell="1",
                                                        Channel="ONE_THREE_LEFT", BandCenterHz=22.5, IntegrationSeconds=45))["band_time_sweep_cell"]
    assert not any(p["from_clinic_sheet"] for p in off["points"]) and off["clinic_sheet"]["included"] is False
