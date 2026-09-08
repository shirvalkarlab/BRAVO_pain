# Plan — Biomarkers heat-map headline redesign, broken into independent tracks

**Written 2026-09-08.** Companion documents: `prd_2026-09-08_biomarkers_heatmap_headline.md` (the
three page-design options and the requirements), `adr_2026-09-08_biomarkers_sweep_family_wise_correction.md`,
`adr_2026-09-08_biomarkers_closedloop_matrix_export.md`.

**This is a plan, not authorization.** Per CLAUDE.md §10 rule 8, the PI gives a separate, explicit
go-ahead before any track below starts, and per §4 this branch is `PS_closedloop_deployment` — there
is no `main` here and nothing in this plan should be read as calling for one. Each task below is
sized to land as its own commit on that branch, mergeable in the order the dependency graph states,
not as a stack.

## Tracks, and why they can run mostly independently

- **Track A — page layout and interaction (frontend).** Builds whichever design option is chosen
  (PRD §4). Depends on nothing else in this plan to *start*, but its final polish (the match-direction
  badge, the family-wise label, the Closed-Loop export button) depends on Tracks B, C and D landing
  their server-side fields first.
- **Track B — wiring match-direction into the calibrated grid (backend).** Self-contained: one
  matching function, one new parameter, one call chain. No dependency on the other tracks.
- **Track C — the family-wise correction (backend, statistics).** Self-contained: one new function
  call added to the grid's existing per-cell answer. No dependency on the other tracks, but needs the
  PI's sign-off on the open ADR question before it starts.
- **Track D — the Closed-Loop matrix export (backend, cross-module).** Depends on Track C only in
  the sense that the exported grid should probably carry the family-wise label if Track C has
  landed — sequence Track D after Track C, or ship Track D first without that field and add it later
  as a small follow-up; either order works, stated so the choice is explicit rather than accidental.

## Track A — page layout and interaction

**Resolved 2026-09-08: building Option 2 (search-first, minimal chrome).** No PI-decision blocker
remains for this track.

| Task | What it does | Acceptance criteria | Depends on |
|---|---|---|---|
| A1 | Reorder the page to the fixed order (PRD §2): timeline, binarization controls, calibrated grids, drill-down, calibration panels — with the grid section running on page load rather than gated behind the older routine. | The calibrated grid's request fires without the older routine having run first; the older routine's section renders below the drill-down, not above the grids. | none |
| A2 | Make grid cells interactive: hover preview, click to pin. No auto-selection on load — the grids start empty of any pinned cell. | Clicking any cell fills a detail panel with that cell's scatter, fitted line, and both violin plots; the same cell is outlined in both the correlation and AUC grids at once; on load, no cell is pre-selected. | A1 |
| A3 | One shared page-level selection (contact pair + frequency point + length of signal) driving every plot that depends on it, replacing the scan's and the sweep's separate selections, chosen via the small-multiples contact strip rather than a dropdown. | Changing contact pair or cell in any one place updates every other plot that shows a selection-dependent value; no two plots on the page disagree about which selection is active; the contact strip, not a dropdown, drives contact choice. | A2 |
| A4 | Show the correlation/binarization asymmetry (PRD §3) as a visible, not merely captioned, behaviour: the correlation grid's frame stays static on a binarization edit, the AUC grid's frame flashes and redraws. | Editing the binarization cuts visibly changes only the AUC grid (a redraw or highlight); the correlation grid's own frame or note stays static across that edit. | A1 |
| A5 | Collapse nearly all of today's captions into a single closed-by-default "how to read this" panel. | The printed word count of always-visible captions on the page (excluding numeric results) is measured before and after and materially reduced; nothing the reader needs to interpret a number is removed, only moved into the on-demand panel. | A2 |
| A7 | Add the match-direction badge and the family-wise-correction label to the grid section once Tracks B and C expose the fields. | The badge names "prior" or "prospective" and matches what the request actually used; a cell's label visibly changes when the family-wise field is present versus absent. | A1, B2, C2 |
| A8 | Add the "export full grid to Closed-Loop" action once Track D exposes the field. | Triggering the action and opening Closed-Loop Deployment for the same participant shows the same grid, not a recomputed one, confirmed by matching a few point values by hand. | A2, D3 |

**Task A6 (Option 1's guided-walk stepper) is out of scope** — dropped, not deferred, since Option 2
has no guided walk.

## Track B — match-direction wiring

**Done 2026-09-08.** All three tasks complete, tested, and proven live.

| Task | What it does | Acceptance criteria | Status |
|---|---|---|---|
| B1 | Add the one-directional ("prior") neighbour search to the calibrated matcher, alongside its existing symmetric search, and thread a new direction argument through the matcher's call chain down from the sweep's own request handler. | Given a constructed set of recordings and pain reports with a known correct answer under each of the three directions, the matcher returns that answer for all three; the existing symmetric behaviour is unchanged when no direction is given, proven by re-running the existing test suite with zero new failures. | **Done.** `_pad_windows_in_extent` and `_nearest_pro` (`availability.py`) both take a direction; "prior" restricts eligibility to a window at or before the rating for both the strict and window-reuse matching paths. "pro_first" is deliberately treated the same as "nearest" since this matcher is window-first, not PRO-first, and has no equivalent framing to switch to. 5 new tests in `tests/test_match_direction.py`, hand-computed expected values, all passing on first run. Container suite 544 -> 549 (+5), host suite unaffected (940/41, Biomarkers not in its list). |
| B2 | Report which direction was actually used in the grid's response, once per contact pair. | The response carries a plain field naming "prior" or "prospective" (or the third setting, if it is kept) matching the request's own setting; a written-down rule states what each label means so Track A's badge text is traceable, not invented at display time. | **Done.** `sweep["match_direction"]` is `"prior"` or `"prospective"`, read back from the matcher's own stats rather than re-derived, so the two can never disagree. `MatchDirection` is also folded into the sweep's store-key settings dict, so a direction change cannot be served a stale answer computed under a different one. |
| B3 | Prove the wiring live on RCS08: does changing the setting change the matched counts and the resulting grid values the way the new logic says it should. | Field count and difference count reported for all three settings against the current response, on the live participant, through the bridge — not asserted, measured — per `ARCHITECTURE_cache_store.md` §7. | **Done.** 27,337 fields per response. Default vs "nearest": 22 differing, all timing fields, the (correctly distinct) store key, or the label itself -- zero scientific values moved. Default vs "pro_first": 19 differing, same three harmless categories. Default vs "prior": 20,229 differing -- a real, substantial, expected difference. |

## Track C — the family-wise correction

**Resolved 2026-09-08: Benjamini-Hochberg, with no autocorrelation adjustment folded in.** No
PI-decision blocker remains for this track.

| Task | What it does | Acceptance criteria | Depends on |
|---|---|---|---|
| C1 | Apply the project's existing Benjamini-Hochberg function across the calibrated grid's 22 frequency points, per sensing contact pair, on top of its existing best-of-ten-lengths answer, computed from the grid's p-values as they stand today (no autocorrelation adjustment). | A new field reports pass/fail (or a corrected value) for the 22-point family, computed only from that grid's own 22 points, never pooled with the older routine's range; a constructed test with a known number of true and false signals recovers the expected corrected count. | none |
| C2 | Surface the new field in the grid's stored response and confirm it is a label, never a gate — nothing about export or selection changes when a point fails it. | A point that fails the correction remains selectable in Track A's UI and exportable in Track D; a test asserts this explicitly (a failing point can still be read back through the same paths a passing one can). | C1 |
| C3 | Prove it live on RCS08: field count and difference count on the grid's response before and after this field is added, confirming no existing value moved. | Reported per `ARCHITECTURE_cache_store.md` §7's discipline, on the live participant, through the bridge. | C1, C2 |

## Track D — the Closed-Loop matrix export

**Blocked on:** nothing to start the storage-side work; the two new fast columns (device-rules
verdict, cross-setting stability) can be built and proven independently of Tracks A-C.

| Task | What it does | Acceptance criteria | Depends on |
|---|---|---|---|
| D1 | Extend the calibrated grid's existing stored entry to carry the full grid (every point, every length, every contact pair), reusing its existing key and provenance chain. | The entry's provenance chain is unchanged in shape (still names only its raw inputs), confirmed by a test that a Closed-Loop-Deployment read of this entry does not trigger the self-derived-product refusal (decision 31), and a control test confirming a deliberately self-derived chain still IS refused, mirroring the existing provenance-cycle test's own pattern. | none |
| D2 | Add the two fast, pre-computed columns (device-rule verdict, cross-setting stability) to the exported grid, computed once per point rather than per request. | Values for a few points match, field for field, what Closed-Loop Deployment's existing single-candidate path already reports for those same points today — an equality proof, not a fresh implementation of the rule. | D1 |
| D3 | Give Closed-Loop Deployment a compact grid-with-selection UI reading this export, with the slower checks (three-source comparison, receiver-operating curve, switching value) staying live-computed only for the point a user opens. | Selecting a point in the compact grid populates the same detail panels Closed-Loop Deployment already has for a single candidate, without recomputing the two fast columns. | D2, A2 (for the shared grid-interaction pattern) |
| D4 | Prove D1-D2 live on RCS08: full field-count and difference-count report, and confirm the refusal behaviour with a real, not constructed, read attempt from each module's own identity. | Per `ARCHITECTURE_cache_store.md` §7, on the live participant, through the bridge. | D1, D2, D3 |

## Dependency graph, in short

```
A1 -> A2 -> A3
A1 -> A4
A2 -> A5
B1 -> B2 -> B3
C1 -> C2 -> C3      (needs PI's ADR sign-off before C1 starts)
D1 -> D2 -> D3 -> D4
A1, B2, C2 -> A7
A2, D3 -> A8
```

Tracks A, B, C and D can be started in parallel once their own individual blockers (marked above)
clear; only A7 and A8 wait on more than one track landing.

## What is explicitly excluded from this plan

Option 3's timeline-anchored interaction (PRD §4) is deliberately not decomposed into tasks here —
it is sequenced after this plan's chosen option ships and after the timeline's left-label geometry
conventions are obtained (CLAUDE.md §9), and deserves its own short plan once those conventions
exist, rather than being estimated against unknowns now.
