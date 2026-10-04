"""The noise model is fitted once per series, and the separation sweep runs vectorised (the PI,
2026-10-04, decisions 420 and 421).

1. The record pair's design rule and the band's own onset (decision 417) each fitted the same
   noise model to the same series in one report: about 3 s twice, plus the Riccati step twice. The
   fit is now kept, keyed on the exact contents of the series and the fit settings, so the second
   asks nothing new; any other series is fitted afresh.
2. The separation sweep drew a fresh noise series per separation tried, one after another. The same
   draws, in the same order from the same generator, now come in one call and every separation is
   judged at once. The answers are bit for bit the same, checked against the loop kept as the
   reference (`_min_separation_for_rate_loop`).
"""
import numpy as np

try:
    from modules.ClosedLoopDeployment import design_rule as DR
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import design_rule as DR


def _series(seed=0, n=4000):
    rng = np.random.default_rng(seed)
    t = 1_750_000_000.0 + 3.0 * np.arange(n)
    t[n // 2:] += 5000.0
    p = 200.0 + np.cumsum(rng.normal(0, 0.8, n)) + rng.normal(0, 20, n)
    return t, p, np.full(n, 2.0)


def test_the_same_series_is_fitted_once_and_answers_the_same():
    DR.clear_fit_memo()
    calls = []
    real = DR.fit_design_model

    def counted(*a, **k):
        calls.append(1)
        return real(*a, **k)
    DR.fit_design_model = counted
    try:
        t, p, a = _series()
        one = DR.design_rule_for_series(t, p, a, upper=210.0, lower=190.0, hours=5.0)
        two = DR.design_rule_for_series(t, p, a, upper=200.0, lower=200.0, hours=5.0,
                                        averaging_grid=(3.0,), onset_grid=(3.0, 15.0, 30.0))
        DR.clear_fit_memo()
        fresh = DR.design_rule_for_series(t, p, a, upper=200.0, lower=200.0, hours=5.0,
                                          averaging_grid=(3.0,), onset_grid=(3.0, 15.0, 30.0))
    finally:
        DR.fit_design_model = real
    assert len(calls) == 2, "fitted once for the two calls, once more after the memo was cleared"
    assert two == fresh, "a kept fit answers exactly as a fresh one"
    assert one["fitted"] == two["fitted"]


def test_another_series_is_fitted_afresh():
    DR.clear_fit_memo()
    t, p, a = _series(seed=0)
    t2, p2, a2 = _series(seed=1)
    x = DR.design_rule_for_series(t, p, a, upper=210.0, lower=190.0, hours=5.0)
    y = DR.design_rule_for_series(t2, p2, a2, upper=210.0, lower=190.0, hours=5.0)
    assert x["fitted"] != y["fitted"]


def _model():
    t, p, a = _series()
    DR.clear_fit_memo()
    return DR.design_rule_for_series(t, p, a, upper=200.0, lower=200.0, hours=5.0)


def test_the_vectorised_sweep_is_bit_for_bit_the_loop():
    t, p, a = _series()
    from ClosedLoopDeployment import simulation as SIM
    stretches, *_ = SIM.regrid_stretches(t, p, a, 3.0)
    for prefer in ("2comp", "1state"):
        model, _ = DR.fit_design_model(stretches, prefer=prefer)
        for avg, onset in ((3.0, 3.0), (3.0, 15.0), (6.0, 30.0), (30.0, 30.0)):
            r1 = np.random.default_rng(7)
            r2 = np.random.default_rng(7)
            want = DR._min_separation_for_rate_loop(model, averaging_s=avg, onset_s=onset,
                                                     level=200.0, rng=r1, dt_s=3.0, hours=20.0)
            got = DR.min_separation_for_rate(model, averaging_s=avg, onset_s=onset, level=200.0,
                                             rng=r2, dt_s=3.0, hours=20.0)
            assert got == want, (prefer, avg, onset)
            assert r1.random() == r2.random(), "the generator is left at the same place"


def test_the_whole_table_is_unchanged():
    t, p, a = _series()
    from ClosedLoopDeployment import simulation as SIM
    stretches, *_ = SIM.regrid_stretches(t, p, a, 3.0)
    model, _ = DR.fit_design_model(stretches)
    real = DR.min_separation_for_rate
    DR.min_separation_for_rate = DR._min_separation_for_rate_loop
    try:
        want = DR.separation_table(model, level=200.0, hours=10.0)
    finally:
        DR.min_separation_for_rate = real
    assert DR.separation_table(model, level=200.0, hours=10.0) == want
