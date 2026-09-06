"""Compatibility and provenance checks for the bundled beta-peak models."""

from __future__ import annotations

import hashlib
import json
import pickle
import sys
import unittest
import warnings
from pathlib import Path

import numpy as np
import sklearn


MODEL_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "modules"
    / "AIModels"
    / "BetaPeakDetection"
)
TRAINING_SKLEARN_VERSION = "1.6.1"
MODEL_CONTRACTS = {
    "BetaPeakDetector.pkl": {
        "artifact_sha256": "5552f54df8787d27194ed50944c7a390b860ac8e9f2920b9547303d1760d06ef",
        "class": "sklearn.ensemble._forest.RandomForestClassifier",
        "n_features": 40,
        "classes": [False, True],
        "prediction_sha256": "2e05e2eef47c7dcd4d082f2da433454500938a3ad8626d8fee46388f8994b809",
        "probability_sha256_12dp": "984035f428ca37840884ef192cb57fcb74e2756fdf6917f2d7a4af889728531f",
    },
    "BetaPeakIdentifier_Classification.pkl": {
        "artifact_sha256": "badc7ced2f57ad55da6a5db97a2740d96c64bd8dfc1f55f14dae612b9c978e95",
        "class": "sklearn.neural_network._multilayer_perceptron.MLPClassifier",
        "n_features": 20,
        "classes": [0, 1],
        "prediction_sha256": "f593c1404958ba11fbe33ca22850dba36c28b30a57339b392fc5027ae3f15b6c",
        "probability_sha256_12dp": "9d2e400c018e6f60c3f1d102e03f1024c3172f0242d8a1776354e2b5f4cf78ee",
    },
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _probe_matrix(n_features: int) -> np.ndarray:
    """Return deterministic ordinary and edge-case numeric feature vectors."""
    rng = np.random.default_rng(20260901 + n_features)
    fixed = np.vstack(
        [
            np.zeros(n_features),
            np.ones(n_features),
            -np.ones(n_features),
            np.linspace(-1, 1, n_features),
            np.linspace(1, -1, n_features),
        ]
    )
    return np.vstack(
        [
            fixed,
            rng.normal(size=(2048, n_features)),
            rng.uniform(-10, 10, size=(512, n_features)),
        ]
    )


def probe_models() -> dict:
    """Describe artifacts and hash predictions after stable decimal quantization."""
    result = {
        "numpy_version": np.__version__,
        "sklearn_version": sklearn.__version__,
        "models": {},
    }
    for filename, contract in MODEL_CONTRACTS.items():
        model_path = MODEL_DIRECTORY / filename
        artifact_bytes = model_path.read_bytes()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            model = pickle.loads(artifact_bytes)

        inputs = _probe_matrix(contract["n_features"])
        probabilities = model.predict_proba(inputs)
        predictions = model.predict(inputs)
        rounded_probabilities = np.round(probabilities, decimals=12).astype("<f8")
        normalized_predictions = np.asarray(predictions, dtype=np.int8)

        result["models"][filename] = {
            "artifact_sha256": _sha256_bytes(artifact_bytes),
            "class": f"{type(model).__module__}.{type(model).__name__}",
            "n_features": int(model.n_features_in_),
            "classes": model.classes_.tolist(),
            "warning_count": len(captured),
            "warning_types": sorted({type(item.message).__name__ for item in captured}),
            "prediction_sha256": _sha256_bytes(normalized_predictions.tobytes()),
            "probability_sha256_12dp": _sha256_bytes(rounded_probabilities.tobytes()),
            "positive_predictions": int(np.sum(normalized_predictions)),
            "probe_rows": int(inputs.shape[0]),
        }
    return result


class BetaPeakModelContractTests(unittest.TestCase):
    def test_runtime_matches_model_training_version(self) -> None:
        self.assertEqual(sklearn.__version__, TRAINING_SKLEARN_VERSION)

    def test_artifacts_and_estimator_contracts(self) -> None:
        probe = probe_models()
        for filename, expected in MODEL_CONTRACTS.items():
            observed = probe["models"][filename]
            for field in (
                "artifact_sha256",
                "class",
                "n_features",
                "classes",
                "prediction_sha256",
                "probability_sha256_12dp",
            ):
                self.assertEqual(observed[field], expected[field])

    def test_models_load_without_version_warning(self) -> None:
        probe = probe_models()
        for filename, observed in probe["models"].items():
            self.assertEqual(
                observed["warning_count"],
                0,
                f"{filename} emitted {observed['warning_types']}",
            )


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(probe_models(), indent=2, sort_keys=True))
    else:
        unittest.main()
