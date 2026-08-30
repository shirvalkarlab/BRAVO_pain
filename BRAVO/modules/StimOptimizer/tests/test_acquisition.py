"""Regression tests for acquisition, batching and the dual stopping rule."""
import numpy as np
import pytest

from StimOptimizer.routines import acquisition as ACQ
from StimOptimizer.routines.surrogate import ObjectiveGP, ParameterGrid

FREQS = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165]
AMPS = np.round(np.arange(0.8, 4.01, 0.1), 2)
LS = [0.823, 0.72]


@pytest.fixture
def grid():
    return ParameterGrid(FREQS, AMPS)


@pytest.fixture
def gp(grid):
    X = np.array([[55.0, 1.6], [55.0, 1.8], [10.0, 1.6], [110.0, 4.0],
                  [130.0, 2.9], [55.0, 1.4], [110.0, 3.3]])
    y = np.array([0.0, -0.68, -0.21, 0.53, 1.30, 0.07, 0.19])
    v = np.array([0.03, 0.06, 0.07, 0.15, 0.21, 0.10, 0.11])
    return ObjectiveGP(grid, fixed_length_scale=LS).fit(X, y, v)


# --- acquisition functions --------------------------------------------------------------
def test_ei_is_zero_where_certain_and_worse():
    ei = ACQ.expected_improvement(mu=np.array([1.0]), sd=np.array([1e-12]), best=0.0)
    assert ei[0] == pytest.approx(0.0, abs=1e-9)


def test_ei_rewards_both_promise_and_uncertainty():
    promise = ACQ.expected_improvement(np.array([-1.0]), np.array([0.1]), best=0.0)[0]
    baseline = ACQ.expected_improvement(np.array([0.0]), np.array([0.1]), best=0.0)[0]
    uncertain = ACQ.expected_improvement(np.array([0.0]), np.array([1.0]), best=0.0)[0]
    assert promise > baseline and uncertain > baseline


def test_lcb_is_more_optimistic_with_larger_eta():
    mu, sd = np.array([0.0]), np.array([0.5])
    assert ACQ.lower_confidence_bound(mu, sd, t=5, eta=4.0)[0] < \
           ACQ.lower_confidence_bound(mu, sd, t=5, eta=1.0)[0]


def test_exploration_fraction_is_bounded_and_ordered():
    f_hi = ACQ.exploration_fraction(np.array([1.0]), t=3, mu=np.array([0.05]))[0]
    f_lo = ACQ.exploration_fraction(np.array([0.01]), t=3, mu=np.array([2.0]))[0]
    assert 0.0 <= f_lo < f_hi <= 1.0


# --- batch selection ---------------------------------------------------------------------
def test_within_visit_batch_does_not_repeat_cells(gp, grid):
    b = ACQ.select_batch_within_visit(gp, grid, q=5, incumbent_mu=0.0)
    idx = [m.index for m in b]
    assert len(b) == 5 and len(set(idx)) == 5


def test_rank_and_select_excludes_tested_cells(gp, grid):
    """Regression: argmax on a discrete grid otherwise re-proposes the incumbent every time."""
    n_rep = np.zeros(len(grid))
    n_rep[grid.index_of(gp.X_)] = 50
    b = ACQ.select_batch_within_visit(gp, grid, q=3, n_reports=n_rep, incumbent_mu=0.0)
    tested = set(grid.index_of(gp.X_).tolist())
    assert not (set(m.index for m in b) & tested)


def test_between_visit_batch_respects_separation(gp, grid):
    sep = 0.6
    b = ACQ.select_batch_between_visit(gp, grid, q=4, min_separation=sep, incumbent_mu=0.0)
    Z = grid.transform(np.array([[m.freq_hz, m.amp_mA] for m in b]))
    for i in range(len(Z)):
        for j in range(i + 1, len(Z)):
            assert np.linalg.norm(Z[i] - Z[j]) >= sep - 1e-9


def test_between_visit_is_more_spread_than_within_visit(gp, grid):
    wv = ACQ.select_batch_within_visit(gp, grid, q=4, incumbent_mu=0.0)
    bv = ACQ.select_batch_between_visit(gp, grid, q=4, min_separation=0.8, incumbent_mu=0.0)

    def spread(b):
        Z = grid.transform(np.array([[m.freq_hz, m.amp_mA] for m in b]))
        return float(np.mean([np.linalg.norm(Z[i] - Z[j])
                              for i in range(len(Z)) for j in range(i + 1, len(Z))]))
    assert spread(bv) > spread(wv)


def test_empty_safe_set_raises_rather_than_returning_nothing(gp, grid):
    with pytest.raises(ValueError, match="no eligible candidates"):
        ACQ.select_batch_within_visit(gp, grid, q=2, safe_mask=np.zeros(len(grid), bool))


def test_safe_mask_is_honoured(gp, grid):
    safe = grid.grid_X()[:, 1] <= 2.0
    b = ACQ.select_batch_within_visit(gp, grid, q=4, safe_mask=safe, incumbent_mu=0.0)
    assert all(m.amp_mA <= 2.0 for m in b)


# --- exploration queue -------------------------------------------------------------------
def test_queue_membership_is_independent_of_ordering(gp, grid):
    mu, sd = gp.predict_grid()
    n_rep = np.zeros(len(grid))
    n_rep[grid.index_of(gp.X_)] = 50
    a, _ = ACQ.exploration_queue(mu, sd, n_rep, 0.0, order_by="ei")
    b, _ = ACQ.exploration_queue(mu, sd, n_rep, 0.0, order_by="optimistic")
    assert set(a.tolist()) == set(b.tolist())
    with pytest.raises(ValueError):
        ACQ.exploration_queue(mu, sd, n_rep, 0.0, order_by="whim")


def test_queue_empties_when_nothing_beats_the_incumbent():
    mu = np.full(20, 5.0)
    sd = np.full(20, 0.01)
    idx, meta = ACQ.exploration_queue(mu, sd, np.zeros(20), incumbent_mu=-1.0)
    assert idx.size == 0


# --- stopping rule -----------------------------------------------------------------------
def _certain_grid(n=50, best=-1.0):
    return np.full(n, 0.0), np.full(n, 1e-6), np.full(n, 10.0), best


def test_plateau_alone_does_not_stop():
    """The whole point of the dual rule: a flat history is not a global optimum."""
    mu, sd, n_rep, _ = np.full(50, 0.0), np.full(50, 1.0), np.zeros(50), None
    d = ACQ.check_stopping([0.0, 0.0, 0.0, 0.0], mu, sd, n_rep, incumbent_mu=0.0)
    assert d.plateau_met and not d.coverage_met and not d.stop
    assert d.binding == "coverage"


def test_coverage_alone_does_not_stop():
    mu, sd, n_rep, inc = _certain_grid()
    d = ACQ.check_stopping([5.0, 3.0, 1.0, -1.0], mu, sd, n_rep, incumbent_mu=inc)
    assert d.coverage_met and not d.plateau_met and not d.stop
    assert d.binding == "plateau"


def test_both_conditions_stop():
    mu, sd, n_rep, inc = _certain_grid()
    d = ACQ.check_stopping([-1.0, -1.0, -1.0, -1.0], mu, sd, n_rep, incumbent_mu=inc)
    assert d.stop and d.binding == "plateau and coverage"


def test_ceiling_reports_truncated_not_converged():
    mu, sd, n_rep = np.full(50, 0.0), np.full(50, 1.0), np.zeros(50)
    cfg = ACQ.StoppingConfig(max_batches=3)
    d = ACQ.check_stopping([1.0, 0.9, 0.8], mu, sd, n_rep, incumbent_mu=0.0, cfg=cfg)
    assert d.truncated and not d.stop and d.binding == "hard ceiling"
    assert "NOT found the optimum" in d.describe()


def test_plateau_needs_k_plus_one_batches():
    mu, sd, n_rep, inc = _certain_grid()
    d = ACQ.check_stopping([-1.0, -1.0], mu, sd, n_rep, incumbent_mu=inc)
    assert not d.plateau_met
