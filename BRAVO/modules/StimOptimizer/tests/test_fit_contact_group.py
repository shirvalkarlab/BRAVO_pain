"""Stage 1 fits each (Left pulse width, Right pulse width, Left contact) group through one function,
`_fit_contact_group` (speed-up item B1, step one, 2026-10-01: a refactor with no change in any
number; step two runs the groups in parallel processes, which needs the fit as a function of its
own arguments only).

Values, not shapes: the function is called once per group large enough to fit, its answers are the
groups run_stage1 reports, and a group whose surface cannot be fitted is reported as skipped with
the exception's own text, exactly as the loop did.
"""
import pytest

from StimOptimizer import stage1_openloop as S1
from StimOptimizer.tests.test_left_contact_groups import _record


def test_each_fitted_group_comes_from_one_call_of_the_group_function(monkeypatch):
    calls = []
    real = S1._fit_contact_group

    def spy(pwl, pwr, contact, sub, **kw):
        out = real(pwl, pwr, contact, sub, **kw)
        calls.append(((pwl, pwr, contact), len(sub), out))
        return out

    monkeypatch.setattr(S1, "_fit_contact_group", spy)
    res = S1.run_stage1(_record(), data_horizon="test", washin_min=1.0)
    assert len(res.slices) == 2
    assert [k for k, _n, _o in calls] == list(res.slices)
    for key, n, (sl, reason) in calls:
        assert reason is None
        assert res.slices[key] is sl
        assert sl.left_contact == key[2]
        assert sl.n_epochs == n
        assert sl.rate_strata and all(rs.left_contact == key[2] for rs in sl.rate_strata.values())


def test_a_group_that_cannot_be_fitted_is_skipped_with_the_exceptions_text(monkeypatch):
    def refuse(*a, **k):
        raise RuntimeError("no surface here")

    monkeypatch.setattr(S1, "_fit_joint_stratum", refuse)
    sl, reason = S1._fit_contact_group(60.0, 160.0, "L C+1-", _record().iloc[:8], grid=None,
                                       sgp_left=None, sgp_right=None, incumbent_xyz=None,
                                       fixed_length_scale=None, kappa=1.0, q=4, eta=1.0, beta=1.0,
                                       constraint=None, ceiling_mA=None, amp_grid=None,
                                       calibration_check=False, resolution_k=2.0)
    assert sl is None and reason == "RuntimeError: no surface here"
    res = S1.run_stage1(_record(), data_horizon="test", washin_min=1.0)
    assert res.slices == {}
    assert sorted(res.skipped.values()) == ["RuntimeError: no surface here"] * 2
