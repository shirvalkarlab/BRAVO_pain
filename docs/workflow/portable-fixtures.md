# Portable fixtures and private calibration acceptance

The portable backend gate must run without participant calibration JSON or
reviewed participant CSV files. These tests construct temporary, invented inputs:

- PSD-to-LSB utility tests use `SYNTHETIC08`, with `80 * sqrt(power)` at 26.4 Hz,
  `40 * sqrt(power)` at 8.8 Hz, and a separate pooled gain of 10. Assertions check
  numerical values, fallback selection, provenance flags and output shape.
- Oura QC tests use a temporary two-row policy. Its day and timestamp boundaries
  deliberately differ so summary exclusions, retained samples, gaps and zero
  values can be checked independently. Its dates are test inputs, not validation
  of the real participant exclusion calendar. `RCS08` is required by the policy
  schema; no participant measurements are in this fixture.
- REDCap correction tests use three invented survey identities and timestamps.
  They check exact identity matching, duplicate rejection and input preservation.

The two real RCS08 model checks remain separate: the reviewed 8.8 Hz fitting
regime and the rejection of an impedance gain term. By default these tests report
an explicit skip. Portable CI passing does not establish private calibration
acceptance or deployment readiness.

On the authorized local host, with the reviewed model mounted read-only at its
normal runtime path, run from the backend directory inside the validation runtime:

```sh
BRAVO_RUN_PRIVATE_MODEL_TESTS=1 python3 -m pytest -q \
  modules/Biomarkers/tests/test_psd_lsb_model.py \
  -k '8p8hz_cut or no_impedance_gain'
```

An opted-in run fails if the model is missing or invalid. It never substitutes the
synthetic model for the scientific acceptance checks. Keep the real model out of
GitHub CI and Git; record the reviewed asset identity and local result separately
when preparing a release. These two regression checks preserve specific reviewed
decisions; they do not establish validity for new inputs or clinical deployment.
