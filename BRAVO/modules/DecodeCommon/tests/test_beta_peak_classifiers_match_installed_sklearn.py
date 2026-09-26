"""The beta-peak detector's two saved classifiers (`AIModels/BetaPeakDetection`, a random forest and a
small neural network) were saved under the scikit-learn version `BRAVO/requirements.txt` pins, the one
the server runs (handoff item P-20, 2026-09-25). They had been saved under 1.6.1 and loaded under the
pinned 1.5.2, a skew scikit-learn warns can give wrong predictions. Measured before re-saving them:
under 1.6.1 and 1.5.2 the two files give the same predicted probabilities on 29,897 forest inputs
(every split value, just either side of it, and uniform draws) and 25,000 network inputs, 0 of 109,794
values differing bit for bit; re-saved under 1.5.2, again 0. If the pin moves, this fails until they
are compared and re-saved.

The version each estimator was saved under is read from the file's own bytes, not by loading it, so
the answer does not depend on which scikit-learn (if any) the machine running the test has installed.
Lives here because DecodeCommon's tests run on both suites, so no test takes arguments."""
import os
import pickletools
import re

_HERE = os.path.dirname(__file__)
_DIR = os.path.join(_HERE, "..", "..", "AIModels", "BetaPeakDetection")
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
    pinned = _pinned_version()
    for name in _FILES:
        found = _saved_versions(os.path.join(_DIR, name))
        assert found == {pinned}, f"{name}: saved under {sorted(found)}, requirements pin {pinned}"
