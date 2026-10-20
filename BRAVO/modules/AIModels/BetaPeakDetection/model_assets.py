"""Optional, administrator-provisioned beta-peak classifiers.

Pickle files are executable: only provision reviewed trusted models in the private
BRAVO_BETA_PEAK_MODEL_DIR. Repository snapshots are never loaded implicitly.
Restart workers after replacing models. Successful loads are cached per directory.
"""
from functools import lru_cache
import os
from pathlib import Path
import pickle
import warnings


MODEL_FILES = ("BetaPeakDetector.pkl", "BetaPeakIdentifier_Classification.pkl")


class ModelUnavailable(RuntimeError):
    """A requested optional model has not been provisioned compatibly."""


def load_beta_peak_models():
    root = os.environ.get("BRAVO_BETA_PEAK_MODEL_DIR", "").strip()
    if not root:
        raise ModelUnavailable("Beta-peak classifiers are unavailable: trusted model assets are not configured.")
    return _load_models(str(Path(root).expanduser().resolve()))


@lru_cache(maxsize=4)
def _load_models(root):
    try:
        from sklearn.exceptions import InconsistentVersionWarning
        models = []
        with warnings.catch_warnings():
            # Cross-version estimator loading is unsupported and may alter predictions.
            warnings.simplefilter("error", InconsistentVersionWarning)
            for name in MODEL_FILES:
                with (Path(root) / name).open("rb") as stream:
                    model = pickle.load(stream)
                if not callable(getattr(model, "predict_proba", None)):
                    raise ValueError("Classifier does not implement predict_proba")
                models.append(model)
        return tuple(models)
    except Exception as exc:
        # Do not expose host paths or raw pickle exceptions in the public response.
        raise ModelUnavailable(
            "Beta-peak classifiers are unavailable: trusted model assets are missing or incompatible."
        ) from exc
