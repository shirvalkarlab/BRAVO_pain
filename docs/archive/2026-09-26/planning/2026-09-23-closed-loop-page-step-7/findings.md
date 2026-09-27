# Findings

- This session runs in a cloud container with no live server, no MySQL, no Redis and no bridge
  (`bridge_client.py --status`: no heartbeat). The live before/after proof on RCS08 that this
  project requires for a change to how a number is produced CANNOT be run from here. The host
  suite runs in a virtual environment built for this session (pandas, scipy, scikit-learn,
  statsmodels, pytest); the container suite cannot run at all.
- Panel D's item 5 has two halves. The page half is already true: `BandStabilityPanel` is a
  full-width card (`Grid item xs={12} id="cl-stability"`) sitting directly after the evidence
  triangle in `index.js`, not nested. Only the coherence-note half is outstanding.
- The stability answer is assembled in `adapter.report_for_participant`, AFTER `report_to_dict`
  has already serialised the coherence note that pipeline.py built. So the note cannot be written
  with the stability answer in `pipeline.run`.
- `state_edge` has two routes: the exported table from the biomarker page (the intended one) and
  this module's own per-sample table. The per-sample current column only exists on the second
  route, so the adjusted reading can only be computed there; the exported route has to say so.
