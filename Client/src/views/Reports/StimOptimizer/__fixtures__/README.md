# Synthetic Stim Optimizer display fixtures

These JSON files were independently authored from the frontend component interfaces and behavioral test assertions. No excluded participant response JSON, participant dataset, device export, or source fixture was read or copied to create them. All observations, counts, uncertainty values, identifiers and times here are artificial. Contact/channel names and device units are schema vocabulary, not participant identity.

- `synthetic_optimizer_basic.json`: older/minimal response shape, two hemisphere settings, separate home/clinic pulse-width groups, small asymmetric current surfaces, unresolved setting choice, one unassessed gate, and a three-cell queue.
- `synthetic_optimizer_cautions.json`: adds an explicit sensing-pair rule, allowed/disallowed rows, an unassessed band response, a two-pair coverage gap, and a moving-across-time caution. It includes the exploratory plan.
- `synthetic_titration_exploratory.json`: independently specified five-step exploratory ladder and three holds; 13 exploratory sheet rows exercise paired ramp/test rows plus hold rows.

Each JSON carries `_fixture_provenance`. The tests use `synthetic-participant` where a request identifier is needed. The small matrices and record excerpts exercise presentation contracts; these are not complete server outputs or usable clinical plans. Tests construct explicit alternative states for recommendations, pooling, unsafe current history, missing evidence and frozen-setting selection.

The tests preserve display behavior, not scientific agreement with an original participant capture. They do not validate backend fitting, device safety, clinical selection, calibration or live deployment. Private-data scientific verification remains a separate integration gate. Previously embedded empirical caveat assertions were replaced with checks that the production text distinguishes observation from causal and predictive evidence.

Checkpoint exception: this shared-checkout subtask is limited to test/fixture files and explicitly requires no commits. The parent owns the next reviewed integration commit after shared validation.
