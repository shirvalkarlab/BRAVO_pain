"""Why a pain map fails its calibration check: thin data, movement between blocks of time, or the
wrong shape (panel C item 3; built 2026-09-23).

The pre-registered check (`OBJECTIVE_SPEC.md` §6, decision 238) says only pass or fail. Panel C made
the reason a condition on changing the model: a boundary-avoiding kernel answers thin data at the
edges, and is useless if the surface moves between blocks of time, or if its intervals are too narrow
everywhere. So each held-out error, in units of the model's own stated uncertainty, is split into
the part its whole block shares (the block moved) and the rest (within the block), and the model's
stated uncertainty is compared with the spread of what it predicts. Beside that, the reference no
model choice can explain away: did pain at the one setting delivered most often move between the
blocks?

Each case below is constructed so its answer is known, and the diagnosis must name it.
"""
import numpy as np
import pandas as pd

from StimOptimizer import stage1_openloop as S1


class _FakeGP:
    """What the diagnosis reads from a fitted surface: the targets, their noise, and held-out
    predictions per group -- set directly, so each case has a known cause."""

    def __init__(self, y, y_var, mu, sd):
        self.y_ = np.asarray(y, float)
        self.y_var_ = np.asarray(y_var, float)
        self._mu, self._sd = np.asarray(mu, float), np.asarray(sd, float)

    def loo_predict(self, groups=None):
        return self._mu.copy(), self._sd.copy()


def _sub(n, *, amps=None, J=None, obs_var=None):
    t0 = pd.date_range("2026-01-01", periods=n, freq="7D", tz="UTC")
    amps = amps if amps is not None else [(1.0 + (i % 4) * 0.5, 2.5) for i in range(n)]
    return pd.DataFrame(dict(t0=t0, amp_mA_Left=[a for a, _ in amps], amp_mA_Right=[b for _, b in amps],
                             J=(J if J is not None else np.zeros(n)),
                             obs_var=(obs_var if obs_var is not None else np.ones(n)), n=5.0))


def _blocks(n):
    return S1._fold_labels_by_time(_sub(n))


def test_a_surface_that_moves_between_blocks_is_named_as_such():
    rng = np.random.default_rng(0)
    n = 30
    b = _blocks(n)
    offset = np.array([2.0, 0.0, -2.0])[b]
    y = 5.0 + offset + rng.normal(0, 0.3, n)
    gp = _FakeGP(y, np.full(n, 0.09), np.full(n, 5.0), np.full(n, 0.3))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["verdict"] == "moves between blocks of time", d
    assert d["between_block_share"] > 0.8
    assert d["between_block_p"] < 0.001


def test_intervals_too_narrow_everywhere_are_named_as_the_shape_or_noise_model():
    rng = np.random.default_rng(1)
    n = 30
    y = 5.0 + rng.normal(0, 2.0, n)                      # scatter the model does not admit
    gp = _FakeGP(y, np.full(n, 0.04), np.full(n, 5.0), np.full(n, 0.2))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["verdict"] == "too confident within blocks: the shape or the noise model", d
    assert d["between_block_share"] < 0.5


def test_wide_honest_intervals_are_named_as_thin_data():
    rng = np.random.default_rng(2)
    n = 30
    y = 5.0 + rng.normal(0, 1.0, n)
    gp = _FakeGP(y, np.full(n, 0.25), np.full(n, 5.0), np.full(n, 1.0))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["coverage95"] >= 0.85
    assert d["verdict"] == "honest but uninformative: thin data", d


def test_pain_at_the_most_delivered_setting_is_checked_across_blocks():
    n = 30
    b = _blocks(n)
    amps = [(2.0, 2.5)] * n                              # one setting throughout
    moved = _sub(n, amps=amps, J=np.array([6.0, 5.0, 4.0])[b], obs_var=np.full(n, 0.25))
    still = _sub(n, amps=amps, J=np.full(n, 5.0) + np.tile([0.1, -0.1], n // 2), obs_var=np.full(n, 0.25))
    gp = _FakeGP(np.full(n, 5.0), np.full(n, 0.25), np.full(n, 5.0), np.full(n, 1.0))
    r1 = S1.calibration_diagnosis(gp, moved)["reference_setting"]
    r2 = S1.calibration_diagnosis(gp, still)["reference_setting"]
    assert r1["setting"] == {"amp_mA_Left": 2.0, "amp_mA_Right": 2.5}
    assert r1["moved"] is True and r1["p"] < 0.001
    assert r2["moved"] is False
    assert len(r1["by_block"]) == 3


def test_fewer_than_two_blocks_with_predictions_is_not_computable_rather_than_a_verdict():
    n = 6
    gp = _FakeGP(np.ones(n), np.ones(n), np.full(n, np.nan), np.full(n, np.nan))
    d = S1.calibration_diagnosis(gp, _sub(n))
    assert d["verdict"] is None and d["reason"]


def test_the_calibration_block_carries_the_diagnosis_and_its_own_numbers_do_not_move():
    """The diagnosis shares the held-out predictions the calibration check already makes, so the
    check's numbers are the same with it as without it."""
    rng = np.random.default_rng(3)
    n = 24
    y = 5.0 + rng.normal(0, 1.0, n)
    gp = _FakeGP(y, np.full(n, 0.25), 5.0 + rng.normal(0, 0.5, n), np.full(n, 0.6))
    out = S1.stratum_calibration(gp, _sub(n))
    assert "diagnosis" in out and out["diagnosis"]["verdict"] is not None
    assert out["blocking"] is False
    assert out["summary"]["loera"]["coverage95"] == out["diagnosis"]["coverage95"]
