# Closed-Loop Deployment page: rebuild report

Prepared 2026-09-04 against branch `PS_closedloop_deployment`. Scope was
`Client/src/views/Reports/ClosedLoopSim/` only. Nothing outside that directory was edited;
`Client/src/routes.js` was not touched, and neither `Reports/Biomarkers/` nor
`Reports/StimOptimizer/` was written to.

## Skills loaded, and what each one changed

`ps-scientific-visualization`, `ps-plotly` and `figure-style` were all loaded before any code was
written. Three decisions changed as a result rather than being settled by preference.

The evidence triangle got **three separate axes sharing only an aligned zero** instead of one shared
numeric axis. The three edges are measured in LFP power per milliamp, pain points per unit of LFP
power, and pain points per milliamp. Putting non-comparable quantities on one axis invites a
magnitude comparison that has no meaning, whereas aligning only zero makes the sign comparison — the
question the coherence test actually asks — readable by eye. This is the visualization guidance's
rule about not implying comparability between different measurement scales.

The duty-cycle state split got a **single-hue sequential ramp** rather than three categorical hues.
Below the lower threshold, between the two, and above the upper threshold are ordinally related, and
a sequential ramp encodes that order where three hues would assert the three states are unrelated
kinds. Same source: encode the data's own structure, do not decorate it.

The decision inks were checked for **colour-vision separability and contrast**, which changed two
things. The pass and fail roles are bluish-green against vermillion rather than green against red,
and every state on the page carries a redundant non-colour encoding — a distinct glyph shape in the
rule ledger, and position along the track in the state tracks — so the page survives greyscale
printing. White text on the warn amber measures 2.25:1, below every WCAG threshold, so warn-role
cells take near-black text; that pairing is keyed on the same role the fill is keyed on so the two
cannot drift apart.

No charting dependency was added. The triangle, the three axes, the four rule glyphs and the duty
bar are hand-written SVG and styled divs, as the brief permitted.

## Components added

| File | Lines | What it is |
|---|---|---|
| `deployFormat.js` | 201 | Pure payload readers and the transcription formatting rules, in one place |
| `stateTracks.js` | 165 | The N-valued answers as data, plus the two-part coherence reading |
| `StateTrack.js` | 83 | Renders a track of N cells with exactly one filled |
| `StateTrack.fixture.test.js` | 144 | Plan item 8's fixture test — the cell-coverage assertion |
| `DeploymentDecisionHeader.js` | 248 | One reconciled verdict (plan item 5) |
| `WhatWouldChangeThis.js` | 281 | The ranked outstanding-work band, actor per row |
| `DeviceRuleLedger.js` | 369 | Plan items 3 and 4: nine outcome kinds, four advisory kinds |
| `EvidenceTrianglePanel.js` | 502 | Plan items 9 and 10: the triangle graph and three signed axes |
| `PrescriptionPanel.js` | 713 | Plan items 6 and 12, plus the PI's mode toggle |
| `DutyCyclePanel.js` | 436 | Plan item 7 |
| `panels.payload.test.js` | 302 | 21 assertions against the real RCS08 response |
| `__fixtures__/rcs08_deployment_payload.json` | — | The saved 152 KB response, test-only |

## Components modified

`palette.js` gained three semantic axes (value provenance, deferral, the ordinal duty ramp), a
shared hatch helper reserved as the page's single caveat channel, and a monospaced stack for
transcribed digits. `index.js` was rewritten to the six-band route. `DeploySignoffCard.js` lost its
own headline verdict and its threshold display entirely, and its frame now keys on the device answer
rather than the statistical one. `deployPrint.css` opts the prescription table into printing **by
class and only in its authorised state**, so the watermarked planning view cannot reach paper, and
its absolute positioning was replaced with document-order layout now that three blocks print.

## Panels no longer rendered on this route

All files are left in place and still export working components.

**Cut entirely** — `PsdLsbPanel.js` (power spectrum) and `ConversionModelPanel.js` (microvolt to
least-significant-bit conversion) are methods artefacts whose reader is the analyst before the band
is chosen; by the time anyone opens this page the band is committed. The raw BandCandidate JSON
inspector is also gone, being a dump of an internal schema with no clinical reader.
**Superseded** — `DeploymentVerdictStrip.js` by `DeploymentDecisionHeader.js`, and
`DeploymentEvidencePanel.js` by `DeviceRuleLedger.js` and `EvidenceTrianglePanel.js` together.
**Demoted, not cut** — `DeploymentRocPanel.js`, `LsbPowerPanel.js` and `EraRefitPanel.js` are behind
one fold below the prescription. All three are real evidence and none is the first question at a
programming visit.

The BandCandidate identity card keeps its device-identity column and folds its discovery-stage
statistics behind a click, per the critique, rather than dropping them.

## Departures from the plan and the critique, with reasons

**Threshold values are shown to four decimal places, not as integers.** The critique's mock-up
formats LFP thresholds as integers with no decimal part, which suits values in the thousands. The
live payload's thresholds are 0.3956 and 0.1820, so integer formatting would render both as `0` and
destroy the value. Four places is a display choice and the panel says so in one sentence beneath the
table; the module deliberately does not round these values because no supplied document publishes a
resolution grid for them.

**The quantity is labelled "LFP power", the payload's own wording, not "LSB".** The critique argues
for one name page-wide, and that argument is right about the hazard. I kept the payload's name
because it is the authority on its own fields and because the brief says so, and removed the
ambiguity a different way: one sentence beneath the table states that the module labels this
quantity LFP power and the device Timeline reports the same quantity as LSB.

**The value column is headed "Value", not "Value to enter".** This is a departure from the mock-up
and it is a safety measure, explained under the payload discrepancies below.

**The satisfied-rule count is derived by subtraction and labelled as derived.** The payload does not
enumerate rules that passed without being pinned, so the ledger shows `checked` minus everything
reported and says where the number came from, rather than implying a list a reader could open.

**The onset-coupling finding appears twice** — on the prescription panel as the full-width banner
plan item 12 specifies, and again in the duty-cycle panel. That is deliberate duplication, not an
oversight: a reader who came to the duty panel for the state-change rate cannot read that rate
correctly without knowing the persistence requirement is inoperative.

## What was expected in the payload and not found

**The duty-cycle block is not at the top level.** The brief and the plan refer to `duty.*`. It is
actually at `prescriptions.modes.<mode>.duty`, with a copy at `prescription.duty`. The panel prefers
the per-mode block and falls back to the top-level copy.

**No field names which inference estimator produced each edge.** Plan item 10 asked for the
frontend to stop duplicating `MIN_RELIABLE_CLUSTERS = 40`. Reading `edges.py` settled the ambiguity
the brief flagged: that constant is no longer a disqualification floor but a **switch** — at or above
forty clusters the cluster-robust (CR0) interval is reported directly, and below it the interval and
the p-value come from a wild cluster bootstrap-t with Rademacher weights imposed under the null. So
the JavaScript comment claiming to mirror `edges.py` was wrong twice over, as the brief said. There
is no structured field naming the estimator, and the manifest key the plan asked for was never
added. What the payload does carry is each edge's own `note`, which states the estimator, the
cluster unit and the count in words. The panel prints that sentence verbatim beside each edge and
recomputes no threshold. The `resolved*` asterisk and its hover tooltip are gone; a tooltip was the
wrong home regardless, because this page prints.

**The two sign-pattern fields are Python dictionary reprs, not JSON.** `coherence.expected_pattern`
and `observed_pattern` arrive as, for example, `{'E1': -1, 'E2': 1, 'E3': -1, 'why': '...'}` —
single-quoted keys, with apostrophes inside the nested prose. `JSON.parse` cannot read them.
`parseSignPattern` extracts the three signs with a narrow expression, falls back to null signs
rather than throwing if the shape changes, and also accepts a real object in case the backend starts
sending JSON. Both real strings are in the test suite verbatim, so a serialisation change surfaces
as a failure rather than as three silently absent signs.

**One row is mislabelled in a way that runs toward a transcription error.** In Single Threshold the
`Single LFP threshold` row arrives with `confirm: "enterable"` while its own `why` says the opposite:
the value is not typed in, because the device computes it as `0.75 × (Upper − Lower) + Lower` under
rule D20, and the number is shown only so a clinician can verify it against the programmer. This is
the one field where the error runs in the direction of entering something that should not be entered.
Two responses, and I would like the second reviewed. First, the value column is headed "Value" and
what to do with a row lives in its own column read from the payload, so a mislabelled `confirm` axis
cannot be promoted into an instruction by a column heading. Second, a deliberately narrow predicate
detects this row from its `why` text and prints `THE DEVICE COMPUTES THIS — DO NOT TYPE IT`. Prose
matching is not a good permanent answer and the code says so: **the right fix is a `confirm` value of
its own from the backend**, and the predicate should be removed when that exists.

**`single_inverse.duty` is null**, which the panel's fallback then satisfied from the top-level dual
duty cycle — see the defects below.

## Defects the payload-backed test suite caught

Three things a compiling build would not have caught.

The duty-cycle panel **reported a full duty cycle under a heading naming Single Threshold Inverse**.
That mode's own `duty` is null, correctly, and the fallback reached the Dual Threshold duty cycle and
rendered its three band-power fractions as if they belonged to a mode with no programmable fields
that cannot drive therapy. A reader comparing modes would have seen three plausible percentages and
concluded the mode does something. The panel now tests the field count, because that is what
determines whether there is a controller to model.

The prescription panel **printed the mode note twice** on the non-driving mode, which reads as two
separate findings about the mode rather than one.

Unicode escape sequences do not process in JSX text children or in JSX attribute string literals.
Twelve occurrences would have rendered as literal `\u2014` on screen. I wrote a scanner, fixed the
genuine cases, and confirmed none remain in attribute position.

## One behaviour change beyond the brief, for review

The read-only planning view now **closes when the mode changes**, so opening it is a deliberate act
once per mode rather than once per page. Without that, a reader who opened it for Dual Threshold and
switched to Single Threshold would find fourteen new parameter values on screen having taken no
action that acknowledged the device still refuses the configuration. The read-back ticks were already
cleared on a mode change for the same reason.

## Items completed, and the one I could not

Plan items 3, 4, 5, 6, 7, 8, 9, 10, 11 and 12 are implemented, together with the PI's mode toggle in
full: three modes, the recommendation beside the toggle and visible on a non-recommended mode, a
selection that never snaps back, a table that remounts per mode, the inverse mode rendered as its
`note` rather than an empty table, and each mode's `not_applicable` list struck through under its own
heading.

**Plan item 1 and item 2 I did not attempt**, because they are not frontend work: item 1 is the
backend's threshold-provenance field and item 2 is the eligibility rule table's own page citations,
both of which the payload already supplies and this page now renders. If those numbers were meant to
be items I owned, I have missed them and they remain open.

## Verification

`eslint` is clean on all 24 JavaScript files in the directory (the glob `ClosedLoopSim/*.js`). All 30 tests pass across the two
suites. The production build result, verbatim:

```
Compiled with warnings.
Failed to parse source map from '/Users/pshirvalkar/dev/BRAVO_pain/Client/node_modules/@mediapipe/tasks-vision/vision_bundle_mjs.js.map' file: Error: ENOENT: no such file or directory, open '/Users/pshirvalkar/dev/BRAVO_pain/Client/node_modules/@mediapipe/tasks-vision/vision_bundle_mjs.js.map'
```

That is the pre-existing `@mediapipe` source-map warning the brief documents as acceptable. No other
warning and no error.

The safety-critical behaviours are asserted against the real RCS08 response rather than trusted to
review: no parameter value on screen while the device refuses, including neither `150 000` nor
`2 min 30 s`; no read-back checkbox existing at all while values are withheld; all sixteen disabled
in the watermarked planning view; the Paused amplitude blank with no suggestion; the coupling banner
carrying both fields, both values and `ceil(2000 / 4096) = 1 controller step`; and the duty panel
never printing a percentage of the day while `fractions_are_of_observed_samples` is true.
