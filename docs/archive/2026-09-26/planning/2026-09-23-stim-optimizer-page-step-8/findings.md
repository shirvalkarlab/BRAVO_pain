# Findings

- `acquisition.check_stopping` runs on the live path (`stage1_openloop._fit_joint_stratum`) and its
  `stop` / `stop_binding` fields reach the response; no card reads them. Panel C item 8 listed it as
  unreached, which is wrong.
- The Stim Optimizer README said an age term down-weighting old ratings was "in place"; it was
  removed (decisions 193-196, and `routines/objective.py`'s own comment). It also said "no Django
  endpoint and no React view yet" and carried a test count. All three corrected.
- The readiness table's fold said the pain leg needs "a positive, established correlation"; decision
  210 made it "supported" (interval wholly above zero). Corrected.
- The grid's cross-page settings tag does not carry decision 234's switch, so the plain-grid reader
  (`band_sweep_grid_for_closed_loop`) serves whichever of the plain and adjusted grids under one tag
  is newer. The plain values are identical in both, so nothing read today changes; the sidecar now
  records the switch so the adjusted one can be found.
- The frequency pin (0.823) acts only on the joint rate-by-currents surface; the per-rate current
  surfaces the current map draws have no rate axis, so no current the page could recommend rests on it.
- This session again had no container, database or bridge: no live proof could be run from here.
