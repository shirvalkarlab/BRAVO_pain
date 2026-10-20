"""Synthetic tests for optional model provisioning; never read repository pickles."""
import pickle
import warnings

import pytest
from sklearn.exceptions import InconsistentVersionWarning
from modules.AIModels.BetaPeakDetection import model_assets


class SyntheticClassifier:
    def predict_proba(self, values):
        return [[0.25, 0.75] for _ in values]


@pytest.fixture(autouse=True)
def isolated_models(monkeypatch):
    monkeypatch.delenv("BRAVO_BETA_PEAK_MODEL_DIR", raising=False)
    model_assets._load_models.cache_clear()
    yield
    model_assets._load_models.cache_clear()


@pytest.mark.parametrize("setting", [None, "", "  "])
def test_unconfigured_models_are_explicitly_unavailable(monkeypatch, setting):
    if setting is not None:
        monkeypatch.setenv("BRAVO_BETA_PEAK_MODEL_DIR", setting)
    with pytest.raises(model_assets.ModelUnavailable, match="not configured"):
        model_assets.load_beta_peak_models()


def provision(tmp_path, monkeypatch, model):
    monkeypatch.setenv("BRAVO_BETA_PEAK_MODEL_DIR", str(tmp_path))
    for name in model_assets.MODEL_FILES:
        (tmp_path / name).write_bytes(pickle.dumps(model))


def test_reviewed_configured_models_load_once(tmp_path, monkeypatch):
    provision(tmp_path, monkeypatch, SyntheticClassifier())
    result = model_assets.load_beta_peak_models()
    assert len(result) == 2
    assert result[0].predict_proba([[0]]) == [[0.25, 0.75]]
    assert result is model_assets.load_beta_peak_models()
    assert model_assets._load_models.cache_info().hits == 1


@pytest.mark.parametrize("invalid", ["missing", "broken", "not_a_classifier"])
def test_invalid_assets_fail_without_disclosing_paths(tmp_path, monkeypatch, invalid):
    monkeypatch.setenv("BRAVO_BETA_PEAK_MODEL_DIR", str(tmp_path))
    if invalid == "not_a_classifier":
        provision(tmp_path, monkeypatch, {})
    elif invalid == "broken":
        for name in model_assets.MODEL_FILES:
            (tmp_path / name).write_bytes(b"invalid pickle")
    with pytest.raises(model_assets.ModelUnavailable, match="missing or incompatible") as caught:
        model_assets.load_beta_peak_models()
    assert str(tmp_path) not in str(caught.value)
    assert model_assets._load_models.cache_info().currsize == 0


def test_mismatched_sklearn_model_is_rejected(tmp_path, monkeypatch):
    provision(tmp_path, monkeypatch, SyntheticClassifier())

    def incompatible(_):
        warnings.warn(InconsistentVersionWarning(
            estimator_name="SyntheticClassifier", current_sklearn_version="1.5.2",
            original_sklearn_version="1.6.1"))
        return SyntheticClassifier()

    monkeypatch.setattr(model_assets.pickle, "load", incompatible)
    with pytest.raises(model_assets.ModelUnavailable) as caught:
        model_assets.load_beta_peak_models()
    assert isinstance(caught.value.__cause__, InconsistentVersionWarning)
