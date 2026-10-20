"""Private model provisioning gate; no estimator pickle is executed by this check.

Set BRAVO_BETA_PEAK_MODEL_DIR to reviewed trusted assets to run this gate.
Portable synthetic loader tests cover the fresh-install unavailable behavior.
"""
import os
import pickletools
import re

import pytest

_HERE = os.path.dirname(__file__)
_DIR = os.environ.get("BRAVO_BETA_PEAK_MODEL_DIR")
_REQUIREMENTS = os.path.join(_HERE, "..", "..", "..", "requirements.txt")
_FILES = ("BetaPeakDetector.pkl", "BetaPeakIdentifier_Classification.pkl")


def _pinned_version():
    with open(_REQUIREMENTS) as f:
        for line in f:
            m = re.match(r"\s*scikit-learn==([0-9][0-9A-Za-z.]*)", line)
            if m:
                return m.group(1)
    raise AssertionError("requirements.txt pins no scikit-learn version")


def _saved_versions(path):
    """Every value stored under `_sklearn_version` in the pickle, read from its opcodes."""
    with open(path, "rb") as f:
        raw = f.read()
    versions, take_next = set(), False
    for op, arg, _ in pickletools.genops(raw):
        if not isinstance(arg, str):
            continue
        if take_next:
            versions.add(arg)
            take_next = False
        elif arg == "_sklearn_version":
            take_next = True
    return versions


def test_the_beta_peak_classifiers_were_saved_under_the_pinned_scikit_learn():
    if not _DIR:
        pytest.skip("Private reviewed beta-peak models are not provisioned")
    pinned = _pinned_version()
    for name in _FILES:
        found = _saved_versions(os.path.join(_DIR, name))
        assert found == {pinned}, f"{name}: saved under {sorted(found)}, requirements pin {pinned}"
