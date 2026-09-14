"""The confirmations-and-separation design rule (T3, 2026-09-13; design_rule.py), ported from the
method contest's `kalman_est` entry (decision 150).

Every test checks a VALUE against either a known-by-construction answer or a closed-form analytic
answer -- never a shape, never "it returned a dict", per this project's own rule (CLAUDE.md §10
rule 11).
"""
import numpy as np
import pytest

try:
    from modules.ClosedLoopDeployment import design_rule as DR
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import design_rule as DR


# --------------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------------
def _flat_stretch(n, level, sigma, seed, dt=3.0, t0=0.0):
    rng = np.random.default_rng(seed)
    y = level + rng.normal(0.0, sigma, n)
    t = t0 + np.arange(n) * dt
    a = np.full(n, 3.0)
    return t, y, a


def _two_component_stretch(n, level, *, phi_s, q_s, phi_f, q_f, r0, seed, dt=3.0, t0=0.0):
    rng = np.random.default_rng(seed)
    slow = np.zeros(n)
    fast = np.zeros(n)
    slow[0] = level
    for i in range(1, n):
        slow[i] = level + phi_s * (slow[i - 1] - level) + rng.normal(0.0, np.sqrt(q_s))
        fast[i] = phi_f * fast[i - 1] + rng.normal(0.0, np.sqrt(q_f))
    y = slow + fast + rng.normal(0.0, np.sqrt(r0), n)
    t = t0 + np.arange(n) * dt
    a = np.full(n, 3.0)
    return t, y, a


# --------------------------------------------------------------------------------------------
# the panel
# --------------------------------------------------------------------------------------------
def test_build_panel_drops_leading_missing_readings_and_short_stretches():
    t1, y1, a1 = _flat_stretch(10, 100.0, 5.0, seed=1)
    y1[:3] = np.nan                                    # three leading missing readings
    stretch_short = (np.arange(2) * 3.0, np.array([1.0, np.nan]), np.array([3.0, 3.0]))
    panel = DR.build_panel([(t1, y1, a1), stretch_short], min_len=3)
    # the short stretch (one finite reading) is dropped; the long one keeps 7 readings, the
    # three leading NaNs stripped so column 0 is the first REAL reading.
    assert panel.shape == (1, 7)
    assert np.isfinite(panel[0, 0])
    assert np.array_equal(panel[0], y1[3:])


def test_build_panel_raises_when_nothing_is_usable():
    with pytest.raises(ValueError):
        DR.build_panel([(np.arange(2) * 3.0, np.array([np.nan, np.nan]), np.array([3.0, 3.0]))],
                       min_len=3)


# --------------------------------------------------------------------------------------------
# fitting
# --------------------------------------------------------------------------------------------
def test_fit_local_level_recovers_a_known_noise_level():
    """A flat series with no slow drift at all: the fitted measurement wobble (r0) should land
    close to the TRUE noise variance, and the fitted process noise (q) should be small next to it
    -- there is no real drift to explain, so nothing should be attributed to one."""
    rng = np.random.default_rng(7)
    sigma_true = 40.0
    stretches = [_flat_stretch(500, 500.0, sigma_true, seed=100 + i, t0=i * 100000.0)
                for i in range(8)]
    panel = DR.build_panel(stretches)
    model = DR.fit_local_level(panel, maxfev=600, restarts=1)
    assert model.kind == "1state"
    # within 15% of the true variance -- generous on purpose, this is a stochastic fit on a
    # moderate sample, and the property under test is "recovers the right order of magnitude and
    # sign", not an exact match.
    assert abs(model.r0 - sigma_true ** 2) / (sigma_true ** 2) < 0.15
    assert model.q < 0.25 * model.r0


def test_fit_design_model_falls_back_to_l1_below_the_reading_floor():
    """Fewer readings than `MIN_READINGS_FOR_TWO_COMPONENT`: the two-component fit is never even
    attempted, and the reason says why."""
    stretches = [_flat_stretch(20, 100.0, 10.0, seed=1)]
    assert sum(np.isfinite(p).sum() for _t, p, _a in stretches) < DR.MIN_READINGS_FOR_TWO_COMPONENT
    model, chosen = DR.fit_design_model(stretches, prefer="2comp")
    assert model.kind == "1state"
    assert "L1 local level" in chosen
    assert "fewer than" in chosen


def test_fit_design_model_recovers_two_components_on_a_genuine_two_component_series():
    """The converse: enough data, and a real fast-plus-slow structure, should be fit as L4 and
    should recover phi_f < phi_s, matching how the data were generated."""
    stretches = [_two_component_stretch(700, 200.0, phi_s=0.9995, q_s=15.0, phi_f=0.7, q_f=900.0,
                                        r0=40000.0, seed=200 + i, t0=i * 100000.0)
                for i in range(10)]
    model, chosen = DR.fit_design_model(stretches, prefer="2comp", maxfev_l4=700, restarts=1)
    assert model.kind == "2comp"
    assert chosen == "L4 two components"
    assert model.phi_f < model.phi_s


def test_fit_design_model_requested_l1_never_tries_l4():
    stretches = [_flat_stretch(500, 100.0, 10.0, seed=1)]
    model, chosen = DR.fit_design_model(stretches, prefer="1state")
    assert model.kind == "1state"
    assert "requested" in chosen


# --------------------------------------------------------------------------------------------
# the Riccati steady state
# --------------------------------------------------------------------------------------------
def test_riccati_steady_state_matches_the_scalar_fixed_point_by_hand():
    """A scalar local-level Riccati equation with a known fixed point, computed two ways: this
    file's own iteration, and a direct closed-form solve of the scalar quadratic
    P = phi^2 P + q - (phi^2 P + q)^2 / (phi^2 P + q + r)."""
    phi, q, r = 0.9, 2.0, 5.0
    a = np.array([[phi]])
    c = np.array([[1.0]])
    qm = np.array([[q]])
    ss = DR.riccati_steady_state(a, c, qm, r)
    # the closed-form quadratic in P_pred: let u = P_pred. u = phi^2 * (u - u^2/(u+r)) + q
    # solved by direct iteration to high precision as an independent check (not `riccati_steady_state`)
    u = r
    for _ in range(200000):
        u = phi * phi * (u - u * u / (u + r)) + q
    assert abs(float(ss["P_pred"][0, 0]) - u) < 1e-6
    gain_by_hand = ss["P_pred"][0, 0] / (ss["P_pred"][0, 0] + r)
    assert abs(float(ss["K"][0, 0]) - gain_by_hand) < 1e-9


def test_ctrlsys_cross_check_runs_and_agrees_when_available():
    """`ctrlsys` is a container-only dependency (see the module docstring): on the host test
    environment this must return `{"available": False}` rather than raising, and wherever it IS
    importable the cross-check must agree with `riccati_steady_state`'s own answer to high
    precision -- the property the contest itself proved (about 1e-12 relative)."""
    a = np.diag([0.98, 0.5])
    c = np.array([[1.0, 1.0]])
    q = np.diag([1.0, 3.0])
    r = 20.0
    out = DR.ctrlsys_cross_check(a, c, q, r)
    if not out["available"]:
        pytest.skip("ctrlsys is not installed in this environment (host test env); "
                    "riccati_steady_state's own iteration is what design_rule_for_series uses")
    assert out["ok"] is True
    assert out["relative_difference"] < 1e-6


# --------------------------------------------------------------------------------------------
# the noise-only crossing simulation: counts RUNS, not individual readings
# --------------------------------------------------------------------------------------------
def test_false_crossing_rate_counts_one_per_run_not_one_per_reading():
    """A hand-built noise draw with a KNOWN run structure: two separate runs of 3 consecutive
    above-threshold windows (onset = 3 windows), and no run reaching that length elsewhere. The
    count must be 2 runs, not 6 readings."""
    model = DR.FittedModel(kind="1state", m=0.0, r0=1.0, nll=0.0, k=2, n=1, phi=1.0, q=0.0)

    class _FixedRNG:
        """A stand-in for `np.random.Generator` that returns a fixed sequence rather than random
        noise, so the crossing structure is known exactly rather than merely likely."""
        def __init__(self, seq):
            self._seq = list(seq)

        def normal(self, loc, scale, size):
            assert scale == 1.0        # r0 = 1.0 above, so this is the only draw made
            out = np.array(self._seq[:size], dtype=float)
            assert len(out) == size
            return out

    dt = 3.0
    averaging_s = dt                                  # one native reading per window
    onset_s = 3 * dt                                   # three consecutive windows to confirm
    level = 0.0
    separation = 10.0
    # 12 windows: readings 0-2 above threshold (run of 3, confirms), reading 3 not, readings
    # 4-5 above (run of 2, too short), reading 6 not, readings 7-9 above (run of 3, confirms),
    # readings 10-11 not.
    above = 20.0                                      # well past level + separation
    below = 0.0
    seq = [above, above, above, below, above, above, below, above, above, above, below, below]
    fixed = _FixedRNG(seq)
    r = DR.false_crossing_rate(model, averaging_s=averaging_s, onset_s=onset_s,
                               separation=separation, hours=12 * dt / 3600.0, level=level,
                               rng=fixed, dt_s=dt)
    assert r["above"] == pytest.approx(2.0 / (12 * dt / 3600.0))
    assert r["below"] == 0.0
    assert r["windows_in_onset"] == 3


def test_min_separation_for_rate_returns_none_when_nothing_in_the_grid_is_enough():
    """"Never" (decision-150's own word for it, contest table): a model whose noise is far bigger
    than every separation offered must report `None`, not the largest grid value pretending to be
    an answer."""
    model = DR.FittedModel(kind="1state", m=0.0, r0=1.0e8, nll=0.0, k=2, n=1, phi=1.0, q=0.0)
    rng = np.random.default_rng(1)
    need, sweep = DR.min_separation_for_rate(model, averaging_s=3.0, onset_s=3.0, level=0.0,
                                             rng=rng, dt_s=3.0, hours=5.0,
                                             separations=(5.0, 10.0, 20.0))
    assert need is None
    assert len(sweep) == 3
    assert all(row["total_per_hour"] > 1.0 for row in sweep)


# --------------------------------------------------------------------------------------------
# the white-noise analytic acceptance test (the task's own second acceptance criterion)
# --------------------------------------------------------------------------------------------
def test_white_noise_series_matches_the_analytic_single_reading_answer():
    """A constructed i.i.d. Gaussian series, ONE reading per decision (no averaging beyond the
    native 3 s reading, one confirmation), compared against the closed-form answer.

    TWO-SIDED ACCOUNTING: a reading is tested against both the upper and the lower threshold
    independently, so the total false-crossing rate is
    `N * 2 * (1 - Phi(sep / sigma)) = target_per_hour`, i.e.
    `sep = sigma * Phi^-1(1 - target_per_hour / (2N))` -- `analytic_min_separation`'s own formula,
    stated again here so the test documents what it is checking rather than only calling a
    function that claims to.
    """
    from scipy.stats import norm

    sigma = 20.0
    dt_s = 3.0
    readings_per_hour = 3600.0 / dt_s
    analytic = DR.analytic_min_separation(sigma, readings_per_hour, target_per_hour=1.0)

    # cross-check the closed form directly, independent of DR's own implementation
    hand = sigma * norm.ppf(1.0 - 1.0 / (2.0 * readings_per_hour))
    assert analytic == pytest.approx(hand, rel=1e-9)

    model = DR.FittedModel(kind="1state", m=0.0, r0=sigma * sigma, nll=0.0, k=2, n=1, phi=1.0,
                           q=0.0)
    rng = np.random.default_rng(42)
    # a fine grid straddling the analytic value, with enough simulated hours that Monte Carlo
    # noise is small next to the 1/hour target.
    fine = sorted({round(analytic * f, 3) for f in (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15)})
    need, sweep = DR.min_separation_for_rate(model, averaging_s=dt_s, onset_s=dt_s, level=0.0,
                                             rng=rng, dt_s=dt_s, hours=3000.0,
                                             separations=fine, target_per_hour=1.0)
    # grid granularity plus Monte Carlo noise near the crossing rate's own 1/hour boundary
    # (the rate function is continuous in separation; the grid step here is about 5%) means the
    # smallest GRID point clearing the target can land one step to either side of the exact
    # analytic value -- checked generously at 10% rather than pinned to the grid's own coarseness.
    assert need == pytest.approx(analytic, rel=0.10)
    # and the simulated rate AT the analytic separation is close to the 1/hour target -- the
    # thing the formula claims, checked at the formula's own answer rather than only nearby.
    rng2 = np.random.default_rng(43)
    at_analytic = DR.false_crossing_rate(model, averaging_s=dt_s, onset_s=dt_s,
                                         separation=analytic, hours=5000.0, level=0.0, rng=rng2,
                                         dt_s=dt_s)
    assert at_analytic["total_per_hour"] == pytest.approx(1.0, abs=0.15)


def test_analytic_min_separation_scales_with_sigma():
    a1 = DR.analytic_min_separation(10.0, 1200.0)
    a2 = DR.analytic_min_separation(20.0, 1200.0)
    assert a2 == pytest.approx(2.0 * a1, rel=1e-9)


# --------------------------------------------------------------------------------------------
# lookup, and the end-to-end entry point
# --------------------------------------------------------------------------------------------
def test_lookup_min_separation_finds_the_nearest_grid_point():
    rows = [{"averaging_s": 3.0, "onset_s": 30.0, "min_separation": 25.0},
            {"averaging_s": 30.0, "onset_s": 30.0, "min_separation": None}]
    hit = DR.lookup_min_separation(rows, averaging_ms=3000.0, onset_ms=30000.0)
    assert hit["min_separation"] == 25.0
    assert hit["exact_match"] is True
    near = DR.lookup_min_separation(rows, averaging_ms=2950.0, onset_ms=29800.0)
    assert near["min_separation"] == 25.0
    assert near["exact_match"] is True
    far = DR.lookup_min_separation(rows, averaging_ms=15000.0, onset_ms=60000.0)
    assert far["exact_match"] is False


def test_design_rule_for_series_refuses_on_a_degenerate_time_base():
    out = DR.design_rule_for_series(np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0]),
                                    np.array([1.0, 1.0, 1.0]), upper=10.0, lower=-10.0)
    assert out["refused"] is True
    assert "no positive interval" in out["reason"]


def test_design_rule_for_series_end_to_end_on_a_constructed_two_component_record():
    """The whole pipeline: stretches with real gaps between them (`simulation.regrid_stretches`
    splits and regrids), a two-component generative model, a real table over the device's
    averaging x onset grid, with the KNOWN qualitative pattern the contest itself reports --
    the minimum separation needed FALLS as the onset lengthens at a fixed averaging duration,
    because more confirmations suppress independent noise more effectively."""
    dt = 3.0
    t_all, p_all, a_all = [], [], []
    t0 = 0.0
    for i in range(24):
        t, p, a = _two_component_stretch(500, 200.0, phi_s=0.9995, q_s=20.0, phi_f=0.72,
                                         q_f=1100.0, r0=48000.0, seed=300 + i, t0=t0)
        t_all.append(t)
        p_all.append(p)
        a_all.append(a)
        t0 += 500 * dt + 20000.0                       # a real gap between stretches
    t = np.concatenate(t_all)
    p = np.concatenate(p_all)
    a = np.concatenate(a_all)
    out = DR.design_rule_for_series(t, p, a, upper=230.0, lower=170.0, hours=60.0,
                                    maxfev_l4=700, maxfev_l1=300, restarts=1)
    assert out["refused"] is False
    assert out["model"] in ("L4 two components",) or "L1 local level" in out["model"]
    assert out["n_train_stretches"] == 24
    assert out["level_midpoint"] == pytest.approx(200.0)
    rows = out["table"]
    assert len(rows) == len(DR.AVERAGING_GRID_S) * len(DR.ONSET_GRID_S)
    by_avg = {}
    for row in rows:
        by_avg.setdefault(row["averaging_s"], []).append(row)
    for avg, group in by_avg.items():
        group = sorted(group, key=lambda r: r["onset_s"])
        finite = [(r["onset_s"], r["min_separation"]) for r in group if r["min_separation"] is not None]
        # non-increasing as onset grows, allowing equality (both may bottom out at the grid floor)
        for (o1, s1), (o2, s2) in zip(finite, finite[1:]):
            assert s2 <= s1, (avg, o1, s1, o2, s2)


# --------------------------------------------------------------------------------------------
# wiring into the parameter card (prescription.py)
# --------------------------------------------------------------------------------------------
try:
    from modules.ClosedLoopDeployment import prescription as PR, types as TY
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import prescription as PR, types as TY


def _payload(rows):
    return {"refused": False, "model": "L4 two components", "table": rows}


def test_design_rule_note_is_none_when_the_table_was_refused():
    assert PR.design_rule_note({"refused": True, "reason": "x"}, upper=210.0, lower=160.0,
                               averaging_ms=3000.0, onset_ms=30000.0) is None
    assert PR.design_rule_note(None, upper=210.0, lower=160.0, averaging_ms=3000.0,
                               onset_ms=30000.0) is None


def test_design_rule_note_states_the_stored_and_required_separation():
    rows = [{"averaging_s": 3.0, "onset_s": 30.0, "min_separation": 25.0, "sweep": []}]
    note = PR.design_rule_note(_payload(rows), upper=234.87, lower=186.27, averaging_ms=3000.0,
                               onset_ms=30000.0)
    assert note is not None
    assert "+-24.3" in note                # (234.87-186.27)/2 = 24.30
    assert "+-25" in note
    assert "3 s averaging" in note and "30 s onset" in note


def test_design_rule_note_states_never_when_min_separation_is_none():
    rows = [{"averaging_s": 30.0, "onset_s": 30.0, "min_separation": None, "sweep": []}]
    note = PR.design_rule_note(_payload(rows), upper=220.0, lower=200.0, averaging_ms=30000.0,
                               onset_ms=30000.0)
    assert note is not None
    assert "no separation" in note


def test_design_rule_note_missing_inputs_gives_none():
    rows = [{"averaging_s": 3.0, "onset_s": 30.0, "min_separation": 25.0, "sweep": []}]
    assert PR.design_rule_note(_payload(rows), upper=None, lower=160.0, averaging_ms=3000.0,
                               onset_ms=30000.0) is None
    assert PR.design_rule_note(_payload(rows), upper=210.0, lower=160.0, averaging_ms=None,
                               onset_ms=30000.0) is None


def test_attach_design_rule_only_touches_the_two_threshold_fields():
    plan = TY.ThresholdPlan(upper=234.87, lower=186.27, capture_amp_low=1.0, capture_amp_high=3.0)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    rows = [{"averaging_s": 3.0, "onset_s": 30.0, "min_separation": 25.0, "sweep": []}]
    out = PR.attach_design_rule(prescriptions, _payload(rows), averaging_ms=3000.0,
                                onset_ms=30000.0)
    dual = out["modes"][PR.PA.DUAL]
    touched = {f.name for f in dual.fields if f.design_rule_note is not None}
    assert touched == {"Upper LFP threshold", "Lower LFP threshold"}
    for f in dual.fields:
        if f.name not in touched:
            assert f.design_rule_note is None


def test_attach_design_rule_is_a_no_op_when_nothing_is_stored():
    plan = TY.ThresholdPlan(upper=234.87, lower=186.27, capture_amp_low=1.0, capture_amp_high=3.0)
    cand = {"channel": "ONE_THREE_LEFT", "center_hz": 24.5, "band_width_hz": 5.0}
    prescriptions = PR.prescribe_all_modes(threshold_plan=plan, candidate=cand,
                                           power_series=None, validated_hemispheres=("Left",),
                                           configuring_both_hemispheres=False)
    out = PR.attach_design_rule(prescriptions, None, averaging_ms=3000.0, onset_ms=30000.0)
    dual = out["modes"][PR.PA.DUAL]
    assert all(f.design_rule_note is None for f in dual.fields)
