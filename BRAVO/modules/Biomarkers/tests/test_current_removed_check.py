"""The current-removed check: always worked out, shown as a WARNING only (decision 484; the PI,
2026-10-18: "do all", change 1 second part, then "Same with the band that loses link to pain after
current is removed - warning only").

For the chosen cell of every band row on the heat map, and for the band on the sign-off card: the
link to pain once the stimulation current (on the band's own side, at the report's own recording,
decision 483) is taken out as a straight line (decisions 241, 242), with its interval and a
rotation p. It warns when the interval is not wholly on the plain value's side of zero, or the
rotation p is above 0.05, or it could not be assessed (no settings stream, decision 9). It never
moves an answer, a gate, a verdict or ready_to_program.

Run:  python3 modules/Biomarkers/tests/test_current_removed_check.py   (R needed for the last two)
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from modules.Biomarkers.routines import analytics as A, sweep_settings as SW
except ImportError:                                            # pragma: no cover - host spelling
    from Biomarkers.routines import analytics as A, sweep_settings as SW

LENGTHS = [3.0, 30.0]
CENTERS = [10.5, 20.5]


def _record(kind, n=120, seed=3):
    """Band power and pain over n reports. kind "current": both follow the current alone;
    "pain": the band follows pain, the current wanders independently of both."""
    rng = np.random.default_rng(seed)
    current = np.repeat(rng.uniform(1.0, 4.0, n // 10), 10)
    if kind == "current":
        pain = 2.0 * current + rng.normal(0, 0.6, n)
        band = 50.0 + 20.0 * current + rng.normal(0, 4.0, n)
    else:
        pain = rng.normal(5, 2, n)
        band = 50.0 + 6.0 * pain + rng.normal(0, 4.0, n)
    other = rng.normal(100, 10, n)
    power = {s: np.column_stack([band, other]) for s in LENGTHS}
    return power, pain, current


def _grid(power, pain, cov, check):
    return A.band_time_sweep_from_power(
        power, pain, center_freqs_hz=CENTERS, requested_seconds=LENGTHS, n_perm=200, n_boot=200,
        seed=0, chunk_exclusion={"n_chunk_band_values_excluded": 0}, covariate=cov,
        covariate_label="current", current_removed_check=check)


def _row(g):
    return g["best_correlation_rows"][0]


def test_a_band_that_follows_the_current_alone_warns_and_keeps_its_answer():
    power, pain, cur = _record("current")
    g, g0 = _grid(power, pain, cur, True), _grid(power, pain, cur, False)
    chk = _row(g)["current_removed_check"]
    assert _row(g)["pearson_r"] > 0.8                          # strong plain link
    assert chk["warning"] is True and chk["status"] == "warning", chk
    assert abs(chk["partial_r"]) < 0.3
    # warning only: every field the neutral grid has is the same
    for k, v in _row(g0).items():
        assert _row(g)[k] == v or (v != v and _row(g)[k] != _row(g)[k]), k
    assert g["answer"] == g0["answer"]
    assert "current_removed_check" not in _row(g0)


def test_a_band_linked_to_pain_holds():
    power, pain, cur = _record("pain")
    chk = _row(_grid(power, pain, cur, True))["current_removed_check"]
    assert chk["warning"] is False and chk["status"] == "holds", chk
    assert chk["partial_r_low"] > 0 and chk["p_rotation"] <= 0.05


def test_a_constant_current_holds_and_says_so():
    power, pain, _ = _record("pain")
    chk = _row(_grid(power, pain, np.full(pain.size, 2.0), True))["current_removed_check"]
    assert chk["status"] == "constant current" and chk["warning"] is False
    assert "constant" in chk["words"]


def test_no_current_at_all_is_not_assessed_and_warns():
    power, pain, _ = _record("pain")
    for cov in (None, np.full(pain.size, np.nan)):
        chk = _row(_grid(power, pain, cov, True))["current_removed_check"]
        assert chk["status"] == "not assessed" and chk["warning"] is True, chk
        assert chk["partial_r"] is None and chk["p_rotation"] is None


def test_the_rotation_p_matches_a_written_out_version():
    power, pain, cur = _record("current", seed=11)
    row = _row(_grid(power, pain, cur, True))
    t = LENGTHS.index(row["integration_seconds_requested"])
    x = power[LENGTHS[t]][:, 0]
    D = np.column_stack([np.ones_like(cur), cur])
    xr = x - D @ np.linalg.lstsq(D, x, rcond=None)[0]
    yr = pain - D @ np.linalg.lstsq(D, pain, rcond=None)[0]
    r0 = np.corrcoef(xr, yr)[0, 1]
    n = x.size
    rk = [np.corrcoef(xr, np.roll(yr, k))[0, 1] for k in range(1, n)]
    p = (sum(abs(v) >= abs(r0) - 1e-12 for v in rk) + 1) / n
    chk = row["current_removed_check"]
    assert abs(chk["partial_r"] - r0) < 1e-12 and abs(chk["p_rotation"] - p) < 1e-12, (chk, r0, p)
    assert chk["n_rotations"] == n - 1


def test_the_setting_builds_the_adjusted_grid_always_and_the_neutral_setting_only_on_request():
    assert SW.CURRENT_REMOVED_CHECK is True
    assert SW.adjust_for_stim_current_param({}) is True
    keep = SW.CURRENT_REMOVED_CHECK
    try:
        SW.CURRENT_REMOVED_CHECK = False
        assert SW.adjust_for_stim_current_param({}) is False
        assert SW.adjust_for_stim_current_param({"AdjustForStimCurrent": "1"}) is True
    finally:
        SW.CURRENT_REMOVED_CHECK = keep


def test_the_daily_default_grid_keeps_one_group_per_score_now_every_grid_is_adjusted():
    tag = SW.sweep_settings_tag_from_request({"SweepMetric": "nrs"})
    assert SW.default_settings_keep_group(tag, SW.adjust_for_stim_current_param({})) == "default_settings:nrs"
    keep = SW.CURRENT_REMOVED_CHECK
    try:
        SW.CURRENT_REMOVED_CHECK = False
        assert SW.default_settings_keep_group(tag, True) == "default_settings:nrs:current_adjusted"
        assert SW.default_settings_keep_group(tag, False) == "default_settings:nrs"
    finally:
        SW.CURRENT_REMOVED_CHECK = keep


# ---- the sign-off card: the band's rotation test with the current as a covariate (needs R) ----

def _frame(seed=0, n_weeks=12, per_week=8, follow_current=False):
    import pandas as pd
    rng = np.random.default_rng(seed)
    cl = np.repeat(np.arange(n_weeks), per_week)
    cur = np.repeat(rng.uniform(1, 4, n_weeks), per_week)
    x = rng.normal(size=cl.size) + (2.0 * cur if follow_current else 0)
    y = (rng.random(cl.size) < 1 / (1 + np.exp(-(cur - 2.5) * (2 if follow_current else 0)))).astype(int)
    t = np.arange(cl.size) * 3600.0 + cl * 7 * 86400.0
    return pd.DataFrame({"pain_high": y, "band_power": (x - x.mean()) / x.std(), "cluster": cl}), t, cur


def test_the_sign_off_rotation_with_the_current_matches_the_module_written_out():
    pytest.importorskip("pymer4", reason="Requires production pymer4/rpy2/R stack")
    pytest.importorskip("rpy2", reason="Requires production pymer4/rpy2/R stack")
    try:
        from modules.Biomarkers.routines import mixed_model_shuffle as M
    except ImportError:                                        # pragma: no cover
        from Biomarkers.routines import mixed_model_shuffle as M
    df, t, cur = _frame(follow_current=True)
    out = A._band_rotation_current_removed(df, t, cur)
    assert out["available"] is True and out["status"] in ("holds", "warning"), out
    null, ok, _ = M.null_fit_lme4(df.pain_high.to_numpy(float), df.cluster.to_numpy(),
                                  X0=cur[:, None], names=["current"])
    assert null.X0.shape[1] == 2                      # intercept and the current, both in the model
    assert ok and out["p"] == M.shuffle_test(null, df.band_power.to_numpy(float), order=t)["p"]
    assert out["warning"] == (out["p"] > 0.05)
    # the current really is in it: a band that follows the current alone loses its small p
    plain = A._band_rotation_test(df, t)
    assert plain["p"] <= 0.05 < out["p"], (plain["p"], out["p"])


def test_the_sign_off_check_without_a_current_is_not_assessed_and_constant_holds():
    df, t, cur = _frame()
    out = A._band_rotation_current_removed(df, t, np.full(len(df), np.nan))
    assert out["status"] == "not assessed" and out["warning"] is True and out["p"] is None
    out = A._band_rotation_current_removed(df, t, np.full(len(df), 2.0))
    assert out["status"] == "constant current" and out["warning"] is False




def test_optional_warning_guards_bad_times_settings_and_current(monkeypatch):
    from modules.Biomarkers.routines import stim_current as sc
    df, t, cur = _frame()
    mask = np.ones(len(df), dtype=bool)
    for times in (None, t[:-1], [['invalid']]):
        out = A._band_current_removed_for_rows(df, times, mask, {})
        assert out['warning'] and not out['available'] and out['p'] is None
    monkeypatch.setattr(sc, 'current_in_force_at', lambda *a, **k: cur)
    out = A._band_current_removed_for_rows(df, t, mask, None)
    assert out['warning'] and not out['available']
    monkeypatch.setattr(A, '_band_rotation_current_removed', lambda d, ts, c: {'checked': len(ts)})
    assert A._band_current_removed_for_rows(df, t, mask, {}) == {'checked': len(df)}


@pytest.mark.parametrize('kind', ['invalid', 'short', 'matrix', 'missing_time', 'one_week',
                                  'missing_column', 'not_converged', 'incomplete', 'nonfinite',
                                  'holds', 'warning', 'raised'])
def test_current_rotation_failure_and_success_contract(monkeypatch, kind):
    from types import SimpleNamespace
    from modules.Biomarkers.routines import mixed_model_shuffle as M
    df, t, cur = _frame()
    if kind == 'invalid':
        cur = ['invalid']
    elif kind == 'short':
        cur = cur[:-1]
    elif kind == 'matrix':
        t = t[:, None]
    elif kind == 'missing_time':
        t[0] = np.nan
    elif kind == 'one_week':
        df = df.assign(cluster=0)
    def fit(*args, **kwargs):
        if kind == 'raised':
            raise ValueError('synthetic fitting failure')
        return SimpleNamespace(X0=np.ones((len(df), 1 if kind == 'missing_column' else 2))), kind != 'not_converged', ['synthetic']
    def shuffle(*args, **kwargs):
        return {'p': np.nan if kind == 'nonfinite' else (0.2 if kind == 'warning' else 0.01),
                'z': 1.0, 'n_orders': len(df), 'p_floor': 1 / len(df),
                'n_unusable': int(kind == 'incomplete')}
    monkeypatch.setattr(M, 'null_fit_lme4', fit)
    monkeypatch.setattr(M, 'shuffle_test', shuffle)
    out = A._band_rotation_current_removed(df, t, cur)
    if kind in ('holds', 'warning'):
        assert out['available'] and out['status'] == kind
        assert out['warning'] == (kind == 'warning')
    else:
        assert not out['available'] and out['warning'] and out['p'] is None


def test_current_warning_small_degenerate_and_interval_cases(monkeypatch):
    rng = np.random.default_rng(141)
    x, y, c = rng.normal(size=(3, 12))
    def call(n=12, **kw):
        return A._current_removed_check(x[:n], y[:n], c[:n], r_plain=kw.get('r_plain', 1),
                                        n_boot=kw.get('n_boot', 20), rng=np.random.default_rng(22))
    assert 'fewer than 8' in call(7)['words']
    saved = x.copy()
    x[:] = 0
    assert 'nothing of band power' in call()['words']
    x[:] = saved
    monkeypatch.setattr(A, '_percentile_interval', lambda *a: (None, None, 0))
    out = call()
    assert out['warning'] and 'no interval' in out['words']
    monkeypatch.setattr(A, '_percentile_interval', lambda *a: (-1.0, -0.5, 20))
    out = call(r_plain=-1)
    assert out['partial_r_high'] == -0.5


def test_constant_current_reports_known_subset_and_candidate_scope():
    df, t, cur = _frame()
    cur[:] = np.nan
    cur[:2] = 2.0
    out = A._band_rotation_current_removed(df, t, cur)
    assert out['status'] == 'constant current'
    assert out['n_samples_without_current'] == len(df) - 2
    assert 'known current' in out['words'] and 'every sample' not in out['words']
    grid = A._current_removed_check(df.band_power.to_numpy(), df.pain_high.to_numpy(), cur,
                                    r_plain=0.5, n_boot=20, rng=np.random.default_rng(0))
    assert grid['status'] == 'constant current'
    assert grid['n_reports_without_current'] == len(df) - 2
    assert 'longest requested window' in grid['current_scope']
    assert 'before per-band artifact rejection' in grid['current_scope']
    assert 'known current' in grid['words'] and 'every report' not in grid['words']


def test_optional_current_lookup_failure_does_not_break_the_main_fit(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import pandas as pd
    from modules.Biomarkers.routines import stim_current as sc
    class Model:
        def __init__(self, *args, **kwargs):
            self.coefs = pd.DataFrame({'Estimate': [0.2], 'P-val': [0.3], 'Z-stat': [1.0]},
                                     index=['band_power'])
            self.ranef_var = pd.DataFrame({'Var': [0.5]})
        def fit(self, **kwargs):
            pass
    monkeypatch.setitem(sys.modules, 'pymer4.models', SimpleNamespace(Lmer=Model))
    monkeypatch.setattr(A, '_rpy2_converter_ctx', nullcontext)
    monkeypatch.setattr(A, '_band_feature_from_detail', lambda *a: (np.arange(40, dtype=float),))
    monkeypatch.setattr(A, '_band_rotation_test', lambda *a, **k: {'available': False, 'reason': 'synthetic'})
    monkeypatch.setattr(sc, 'current_in_force_at', lambda *a, **k: (_ for _ in ()).throw(ValueError('synthetic missing settings')))
    detail = {'labels': np.arange(40, dtype=float),
              'times': pd.date_range('2020-01-01', periods=40, freq='D').astype(str).tolist()}
    plain = A.band_mixedmodel_inference(detail, 'ONE_THREE_LEFT', 15.0)
    warned = A.band_mixedmodel_inference(detail, 'ONE_THREE_LEFT', 15.0, current_removed={})
    assert plain['available'] and warned['available'] and warned['converged']
    warning = warned.pop('rotation_current_removed')
    assert warning['warning'] and not warning['available'] and warning['p'] is None
    assert plain == warned


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("PASS", name)
            except Exception as exc:                            # noqa: BLE001
                fails += 1; print("FAIL", name, repr(exc))
    sys.exit(1 if fails else 0)
