# Findings — outstanding items sweep

## §1 Item 1, figure snapshots
- Audit item [49] (AUDIT_TRIAGE_v3): "Embed Plotly PNG snapshots of the 4 figures into the deploy
  export / printed sheet". The Closed-Loop page's Plotly figures, by section id: `#cl-roc`
  (DeploymentRocPanel: ROC curve, histogram, forward-validation — three divs), `#cl-lsb`
  (LsbPowerPanel: two divs), `#cl-era` (EraRefitPanel: one), `#cl-three-source` (two). The first
  three sit inside the collapsed "analyst" fold and exist only once it has been opened.
- The print stylesheet shows `.cl-signoff-card *`, so images inside the card print with no CSS change.
- `exportJson` builds the file from state; snapshots can be added as base64 PNG data URLs.

## §2 Two defects found while watching item 1 live (2026-09-10)
- **The grid and the report shared one cache slot.** `useCachedResult` keeps ONE answer per module
  slot per participant and answers a different settings key with the held entry marked stale (the
  Recompute behaviour the PI chose, decision 82). `useBandSweepGrid` and `useDeploymentReport`
  both used `CL.report`; the grid's empty-candidate reply filled the slot, and choosing a band then
  showed "no candidate configuration was supplied" on the evidence panel with a band plainly chosen.
  No report request with the candidate ever fired. The grid hook's own comment claimed the two
  could not collide. Fixed: `CL.grid` slot. After the fix the candidate request fires on load.
- **Two of the four gunicorn workers were running old code.** One threw
  `AttributeError: reliable_change has no attribute pooled_same_condition_sd` (deleted in decision
  111) from a line number that no longer matches the file; another answered "No module named
  'ClosedLoopDeployment'" (the import root `settings.py` added on 2026-09-09). A fresh process
  imports everything cleanly. Worker ages were 1 day, 7 h, 5 h, 5 h under a 2.5-day-old master;
  `--reload --reload-engine poll` did not recycle them. Remedy as decisions 86/87/92: `kill -HUP 1`.
- Seen and not changed: the reliable-change panel defaults to Left Leg VAS (first assessed score in
  `items_order`), not NRS; and after the ROC panel sets an operating point the summary reads
  `inputs_stale: true` in the export, which is decision 82's chosen behaviour.

## §3 THE PI'S BRIEF FOR THE NEXT SESSION — Closed-Loop Deployment page redesign (2026-09-10)
Verbatim where it matters. "The CL module page is way too long, so we need to distill it down and
make it much slimmer."
- "The calibrated grid at the top is really ugly and takes up too much space. We should have a
  visual depiction similar to the heat map from the biomarkers module, flipped 90 degrees so that
  the band centers are oriented vertically. Then you can put maybe correlation high versus low.
  Instead of high versus low, it should be called AUC, and we can have a symbol for family-wise
  correlation. If it doesn't clear, you get a little X; if it does clear, you get a checkmark. For
  cross-setting stability, it can be a yellow circle for when it can't tell, a red cross if it
  behaves differently, and a green checkmark if it's good. It can be a tick mark or a box that
  needs to be clicked or checked instead of writing 'use this band' a million times. Write it once
  on top, and then again for all the tabs you select for which contact."
- Contacts: "they should be in standard Medtronic notation, left 1-3+, left 0-3+, ordered left to
  right as in biomarkers thumbnails."
- "load your scientific visualization skills as well as other UI/UX skills."
- "Text everywhere makes it really verbose, so maybe it should be a dropdown like reveal this,
  don't reveal this panel. The device rule ledger should also be a panel that can be expanded or
  contracted because it's too verbose."
- "SIGN COHERENT should be called SIGN agreement, SIGN concordance, or something similar."
- "This is really critical and important": rename "how stimulation current [moved] band power
  measured three ways" to "stimulation amplitude effects on band power measured three ways".
- The three source titles inside that panel, his exact words: "instead of 'from the voltage trace',
  'from the device's own spectrum', 'from the device's own band power', it should be rephrased to
  'Time domain derived LSB', 'PSD derived LSB', and then finally 'Direct LSB recording'. Those should
  be the three titles. In the text below, it should be significantly made much more concise with
  the scientific visualization skill."
- Three-source panel: "you basically don't want separate visits with separate tabs because you
  pool across all visits for right side and left side. Maybe it's just two tabs for right side
  amplitude change and left side amplitude change pooled across all visits. Then we'll have to
  adjust or massage exactly what calculation goes into the evidence triangle from there, which
  remains to be determined."

## §4 Item 2 — the "spectral point" is on no page (2026-09-10)
`availability.per_pro_lsb_spectrum` has zero production callers: the live per-rating spectrum was
retired on 2026-06-28 when tile-cache matching replaced it (bravo_service.py's own comment near
`_live_pro_lsb_spectrum`: "the legacy real-time per_pro_lsb_spectrum recompute is retired"). The
timeline circle (`per_pro_lsb`, av.pro_lsb) IS on the Biomarkers page. So open item 13 pinned a
live number against a function nothing reads. Measured anyway: 240/240 equal (TD 15-16 per
contact, bridge 105 on ZERO_THREE_RIGHT, 29 on ONE_THREE_LEFT, 4 on ZERO_TWO_LEFT); native-tier
circles (25, 74, 6) are excluded because the spectrum has no native tier. Probe:
`_agent_bridge/_probe_tl/probe_circle_vs_spectrum.py` (disposable). The live test costs ~16 s.
**Candidate for the PI**: `per_pro_lsb_spectrum` is a zero-caller function, the same class
decision 110 deleted (`per_pro_lsb_overlay`); if it goes, the live test goes with it and the
constructed one becomes moot.

## §5 Item 5 (B4) — found while capturing (2026-09-10)
- `build_pooled_detail_from_matrix(aggregate="one_per_rating")` crashes: `Xabs` is read at line ~913
  but was removed on 2026-06-27 with the Welch-density path. Unreachable: `_compute_analytics` and
  `_band_validation_setup` both hard-code `aggregate="all"`. Dead and broken; left for the PI.
- Capture and compare probes: `_agent_bridge/_probe_tl/probe_b4_capture.py` / `probe_b4_compare.py`
  (pickles of before/after on the container, disposable).
