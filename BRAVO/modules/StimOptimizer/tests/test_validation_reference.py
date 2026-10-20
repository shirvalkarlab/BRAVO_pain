"""Reference selection is explicit and independent of former participant epochs."""
import numpy as np
import pandas as pd
import pytest
from StimOptimizer.routines import validation as V


def test_warm_start_requires_an_explicit_reference():
    with pytest.raises(ValueError, match="incumbent_epoch"):
        V.fit_warm_start(pd.DataFrame(), V.build_grid())


def test_plateau_uses_the_passed_reference_not_a_historical_epoch(monkeypatch):
    class GP:
        y_ = np.array([-1., 0.])
        length_scale = np.array([0.823, 2.])
        def predict_grid(self):
            return np.arange(len(grid), dtype=float), np.ones(len(grid))
        def predict(self, x):
            assert x.tolist() == [[20., 1.]]
            return np.array([0.]), np.array([1.])
    grid = V.SUR.ParameterGrid([10., 20.], [1., 2.])
    data = pd.DataFrame({"epoch": [4., 9.], "freq_hz": [10., 20.], "amp_mA_Left": [1., 1.], "n": [3., 3.]})
    data.attrs["incumbent_epoch"] = 9.
    # The predictor assertion runs before secondary diagnostics need a fitted surrogate.
    def stop(*args, **kwargs):
        raise RuntimeError("reference verified")
    monkeypatch.setattr(V.ACQ, "expected_improvement", stop)
    with pytest.raises(RuntimeError, match="reference verified"):
        V.plateau(GP(), grid, data, data_horizon="synthetic")
