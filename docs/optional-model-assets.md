# Optional beta-peak classifiers

The application can start without beta-peak classifier files. Requests for this optional prediction return HTTP 503 with `code: model_unavailable` until a trusted, compatible model pair is configured. Other model methods remain available.

Set `BRAVO_BETA_PEAK_MODEL_DIR` privately to a directory containing:

- `BetaPeakDetector.pkl`
- `BetaPeakIdentifier_Classification.pkl`

Pickle deserialization executes code. Only an administrator should provision models whose origin and contents have been reviewed; never accept model uploads from an application request. Keep the directory private and out of Git. Both classifiers must implement `predict_proba` and match the installed scikit-learn version. A version warning rejects the pair. Workers cache a successful load, so restart them after replacing assets.

The integrated numerical stack pins scikit-learn 1.5.2. Provision an independently
reviewed compatible pair; this repository does not ship model weights or claim
that an unconfigured installation has model coverage. Keep provisioning manifests
and their private source identities outside Git.

Portable synthetic loader tests exercise configured loading, caching, missing/malformed assets, incompatible interfaces and version mismatch. The optional private version gate is `modules/DecodeCommon/tests/test_beta_peak_classifiers_match_installed_sklearn.py`; it skips explicitly when the private directory is not configured. A portable test pass does not certify unprovisioned model assets.
