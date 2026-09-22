"""The heat map's correlation with the stimulation current in force taken out of it.

WHY THIS EXISTS. The grid correlates a band's power against a pain score and nothing else. On
RCS08's left lead both of those fall as the stimulation current rises, so a band can look as though
it tracks pain when what it tracks is the current that was running at the time (measured 2026-09-22:
on L 1-3+ every 21.5-26.5 Hz cell the exploratory search called "supported" loses its wholly
positive interval once the current in force at each rating is taken out of it). The older
per-session search has carried that adjustment for a long time (`pipeline.py`, `partial_corr`); the
grid never has.

WHAT IS ASSERTED, in order:

  * the adjustment does what it says: on data where the current drives BOTH the band power and the
    pain score and nothing else connects them, the plain correlation is large and the adjusted one
    is not;
  * a real relationship that does not come from the current survives the adjustment (the control:
    an adjustment that flattens everything is useless);
  * THE RAW SIDE DOES NOT MOVE. Every number the page already shows is identical whether or not the
    covariate is supplied. The adjusted value rides beside the plain one; it never replaces it and
    never re-selects a band;
  * a covariate that is missing, constant, or too short to regress out is REFUSED with a reason,
    never silently treated as an adjustment that found nothing;
  * the column-wise partial correlation equals the one-column-at-a-time function it is built on;
  * the current in force at a moment is the newest programmed setting at or before it, per side,
    and is unknown (not zero) before the first setting on record.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_current_adjusted_correlation.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics as A          # noqa: E402
from Biomarkers.routines import stats_utils as SU       # noqa: E402
from Biomarkers.routines import stim_current as SC      # noqa: E402


# ---------------------------------------------------------------------------------------------
# helpers: a grid whose only connection between power and pain is the current in force
# ---------------------------------------------------------------------------------------------

def _grid_driven_by_current(seed=0, n_reports=90, confounded_col=6, honest_col=11):
    """Band powers, pain scores and the current in force at each rating.

    Two bands are planted. The CONFOUNDED one has no relationship with pain at all except through
    the current: the current pushes its power down and pushes the pain score down, which leaves the
    two correlated with each other. The HONEST one tracks pain directly and does not see the
    current. Everything else is noise.
    """
    rng = np.random.default_rng(seed)
    centers = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
    C = centers.size
    amp = rng.choice([0.0, 1.0, 1.6, 2.5, 3.5, 4.5], size=n_reports)      # mA in force at the rating
    za = (amp - amp.mean()) / amp.std()
    own = rng.normal(0.0, 1.0, n_reports)                                 # pain that is not the current
    pain = 50.0 - 8.0 * za + 6.0 * own
    power = {}
    for s in A.BAND_TIME_SWEEP_SECONDS:
        m = rng.normal(0.0, 1.0, (n_reports, C))
        m[:, confounded_col] -= 1.6 * za                                  # falls with current only
        m[:, honest_col] += 1.6 * own                                     # tracks pain only
        power[float(s)] = np.exp(m)
    return power, pain, amp, centers, confounded_col, honest_col


def _sweep(power, pain, centers, **kw):
    return A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=60, n_boot=60,
                                        seed=3, channel="ONE_THREE_LEFT", metric_key="left_leg_vas",
                                        metric_label="Left Leg VAS", **kw)


def _row_at(out, centre_hz):
    for r in out.get("best_correlation_rows") or []:
        if abs(float(r["band_center_hz"]) - float(centre_hz)) < 1e-9:
            return r
    raise AssertionError(f"no best row at {centre_hz} Hz")


# ---------------------------------------------------------------------------------------------
# 1. the adjustment removes a relationship that is only the current
# ---------------------------------------------------------------------------------------------

def test_a_band_that_only_follows_the_current_loses_its_correlation_when_the_current_is_taken_out():
    power, pain, amp, centers, conf_col, _ = _grid_driven_by_current()
    out = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    row = _row_at(out, centers[conf_col])
    raw, adj = float(row["pearson_r"]), float(row["pearson_r_adjusted"])
    assert abs(raw) > 0.35, f"the planted confounded band should correlate plainly, got r={raw:.3f}"
    assert abs(adj) < 0.15, f"taking the current out should leave nothing, got r={adj:.3f}"
    assert abs(adj) < abs(raw) / 2.0
    assert np.isclose(float(row["pearson_r_adjustment"]), adj - raw, atol=1e-12)
    grid = out["adjusted_correlation_grid"]
    assert np.asarray(grid, dtype=float).shape == np.asarray(out["correlation_grid"], dtype=float).shape
    print(f"OK a current-driven band reads r={raw:.3f} plainly and r={adj:.3f} adjusted")


# ---------------------------------------------------------------------------------------------
# 2. the control: a real relationship survives the adjustment
# ---------------------------------------------------------------------------------------------

def test_a_band_that_tracks_pain_on_its_own_keeps_its_correlation():
    power, pain, amp, centers, _, honest_col = _grid_driven_by_current()
    out = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    row = _row_at(out, centers[honest_col])
    raw, adj = float(row["pearson_r"]), float(row["pearson_r_adjusted"])
    assert abs(raw) > 0.3 and abs(adj) > 0.3, f"raw {raw:.3f}, adjusted {adj:.3f}"
    assert abs(adj - raw) < 0.2, "a band that does not follow the current should barely move"
    print(f"OK a genuinely pain-tracking band reads r={raw:.3f} plainly and r={adj:.3f} adjusted")


# ---------------------------------------------------------------------------------------------
# 3. the numbers the page already shows do not move
# ---------------------------------------------------------------------------------------------

def test_supplying_the_covariate_changes_nothing_about_the_plain_answer():
    power, pain, amp, centers, _, _ = _grid_driven_by_current()
    plain = _sweep(power, pain, centers)
    adjusted = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    assert "adjusted_correlation_grid" not in plain, "no covariate means no adjusted grid at all"
    a = np.asarray(plain["correlation_grid"], dtype=float)
    b = np.asarray(adjusted["correlation_grid"], dtype=float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    assert np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], rtol=0, atol=0), "the plain grid moved"
    for key in ("best_correlation_rows", "best_auc_rows"):
        for r0, r1 in zip(plain[key], adjusted[key]):
            for field in ("band_center_hz", "pearson_r", "integration_seconds_delivered",
                          "n_pain_reports", "family_wise_q_8_to_30hz", "answer"):
                if field in r0:
                    v0, v1 = r0[field], r1[field]
                    same = (v0 == v1) or (isinstance(v0, float) and isinstance(v1, float)
                                          and np.isnan(v0) and np.isnan(v1))
                    assert same, f"{key}.{field} moved: {v0!r} -> {v1!r}"
    print("OK the plain grid and every selected row are identical with and without the covariate")


# ---------------------------------------------------------------------------------------------
# 4. a covariate that cannot adjust anything is refused with a reason
# ---------------------------------------------------------------------------------------------

def test_a_constant_or_absent_covariate_is_refused_and_says_why():
    power, pain, amp, centers, _, _ = _grid_driven_by_current()
    flat = _sweep(power, pain, centers, covariate=np.full(pain.size, 2.5),
                  covariate_label="the current in force (mA)")
    block = flat["covariate_adjustment"]
    assert block["applied"] is False
    assert "constant" in (block["reason"] or "").lower()
    assert "adjusted_correlation_grid" not in flat

    missing = _sweep(power, pain, centers, covariate=np.full(pain.size, np.nan),
                     covariate_label="the current in force (mA)")
    assert missing["covariate_adjustment"]["applied"] is False
    assert "no" in (missing["covariate_adjustment"]["reason"] or "").lower()

    ok = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    b = ok["covariate_adjustment"]
    assert b["applied"] is True and b["label"] == "the current in force (mA)"
    assert b["n_with_covariate"] == int(pain.size) and b["n_distinct_values"] == 6
    print("OK a constant, absent or unusable covariate is refused with a reason")


# ---------------------------------------------------------------------------------------------
# 5. the column-wise partial correlation is the same arithmetic as the scalar one
# ---------------------------------------------------------------------------------------------

def test_the_column_wise_partial_correlation_matches_the_one_column_function():
    rng = np.random.default_rng(7)
    n, C = 70, 5
    covar = rng.normal(0, 1, n)
    X = rng.normal(0, 1, (n, C)) + covar[:, None]
    y = rng.normal(0, 1, n) + 2.0 * covar
    X[3, 2] = np.nan
    y[9] = np.nan
    got = SU.partial_corr_columns(X, y, covar)
    for c in range(C):
        one = SU.partial_corr(X[:, c], y, covar)
        assert np.isclose(got["r"][c], one, rtol=0, atol=1e-12, equal_nan=True), c
    assert got["n"][2] == n - 2 and got["n"][0] == n - 1
    print("OK the column-wise partial correlation equals the scalar one, column for column")


# ---------------------------------------------------------------------------------------------
# 6. the current in force at a moment
# ---------------------------------------------------------------------------------------------

def test_the_current_in_force_is_the_newest_setting_at_or_before_the_moment_per_side():
    hour = 3600.0
    t0 = 1_700_000_000.0
    stream = {
        "t_s": np.array([t0, t0, t0 + 10 * hour, t0 + 10 * hour]),
        "hemi": np.array(["Left", "Right", "Left", "Right"]),
        "amp_mA": np.array([1.6, 2.5, 4.0, 2.5]),
    }
    times = np.array([t0 - hour, t0 + hour, t0 + 11 * hour])
    left = SC.current_in_force_at(times, stream, hemisphere="Left")
    right = SC.current_in_force_at(times, stream, hemisphere="Right")
    assert np.isnan(left[0]), "before the first setting on record the current is unknown, not zero"
    assert left[1] == 1.6 and left[2] == 4.0
    assert np.isnan(right[0]) and right[1] == 2.5 and right[2] == 2.5
    assert SC.hemisphere_of_channel("ONE_THREE_LEFT") == "Left"
    assert SC.hemisphere_of_channel("ZERO_THREE_RIGHT") == "Right"
    assert SC.hemisphere_of_channel("nonsense") is None
    print("OK the current in force is the newest setting at or before each moment, per side")


if __name__ == "__main__":
    test_a_band_that_only_follows_the_current_loses_its_correlation_when_the_current_is_taken_out()
    test_a_band_that_tracks_pain_on_its_own_keeps_its_correlation()
    test_supplying_the_covariate_changes_nothing_about_the_plain_answer()
    test_a_constant_or_absent_covariate_is_refused_and_says_why()
    test_the_column_wise_partial_correlation_matches_the_one_column_function()
    test_the_current_in_force_is_the_newest_setting_at_or_before_the_moment_per_side()
    print("All current-adjusted correlation tests passed.")
