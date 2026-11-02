# Synthetic ClosedLoopSim responses

These six small response fixtures are independently authored from frontend field contracts. They contain no copied participant response data and are not evidence of measured performance, backend numerical parity, or clinical readiness.

The allowed-left and refused-right cases exercise transcription, withholding, read-back reset, and side identity. The provisional grid exercises band selection, request reuse, and uncertainty wording. The blocked-rules case exercises distinct refusal, unavailable, advisory and recorded-value states. Summary cases exercise evaluated-versus-indeterminate gates. Contacts, mode names and parameter counts represent interface/device schema; all numerical observations and identities are synthetic.

- `synthetic_november_contracts.js`: independently authored minimal response
  examples built on the existing synthetic report/summary contracts and synthetic
  source grids. Exercises deciding-p labels, current/recent/home-swing warnings,
  separate correlation/AUC family values, negative thresholds, advisory-only D53,
  and four programmed/candidate comparison rows. All values/dates are invented;
  these fixtures verify display contracts, not empirical numerical agreement.
