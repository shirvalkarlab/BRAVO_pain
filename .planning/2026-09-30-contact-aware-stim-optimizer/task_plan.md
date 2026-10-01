# Task Plan: Contact-aware Stim Optimizer

## Goal
The Stim Optimizer's pain model knows which contacts were stimulating, so it stops pooling different Left contact configurations as if they were one.

## Next Step
Phase 6: the within-visit ladder from the top block (waits on the tie); PI questions open: group D on C+1-2- or 1a-2a; use Overall when left leg is missing?

## Current Phase
Phase 7

## Scope and authority
The PI's answers of 2026-09-30:
1. Rule 13 ("never pool across electrodes") covers RECORDING electrodes only, not stimulating contacts.
2. The in-clinic rating chooses the next block; home ratings confirm it. Never merged.
3. Go-ahead for step A (Phases 2-4 below).
4. Remove today's visit plan entry (Phase 1).

2026-10-01: the PI, "keep going with tests and steps B C etc": B (partial pooling across contacts)
and C (the model picks the next clinic block) are authorised, after A. D (contact as a position on
the lead) only if B finds contacts differ, and it is named to him before it starts.

## Phases

### Phase 1: Remove the 2026-09-30 visit plan entry
- [x] Test first: RCS08 has no visit plan entry (watched RED, then GREEN)
- [x] Empty `VISIT_PLAN_BY_UID` (mechanism kept; its test runs on a constructed entry)
- [x] Both suites (host 1817 passed / 2 skipped / 0 failed; container PASS=945 FAIL=0); commit and push
- **Status:** complete

### Phase 2: Discovery for step A
- [x] With jevgrep: how Stage 1 splits epochs into pulse-width groups (the minimum count, the key, which group the recommendation and the 55 Hz pain map read)
- [x] Search DECISIONS_and_open_items.md for earlier rulings on contacts in the model (none)
- [x] Record in findings.md
- **Status:** complete

### Phase 3: Step A, the Left contact as a grouping key
- [x] Tests first (tests/test_left_contact_groups.py, 31; watched failing): a constructed record with two Left contact configurations gives two groups; the pain map at 55 Hz reads only the group for the contacts in question; the page is told the count per contact
- [x] Add the Left contact configuration (the active contacts only, so 0 mA carries no contact) to the grouping key beside pulse width, in run_stage1 (per-pairing and pooled) and the clinic fit
- [x] The clinic epoch frame (`clinic_pain.epoch_frame_from_steps`) keys stretches on Left contact too
- [x] PI's call: share Left-0-mA stretches into every Left contact group (yes)
- [x] Map every reader of the group label (server: stage1_openloop grouping, _freeze_joint, bravo_service line ~951, rate tables, pooled fit; page: ~18 files)
- [x] Refactor commit first: `contacts_short` moved to DecodeCommon.sensing_rule (c465a11e; host 1817/2/0, container 945/0)
- [x] Side fix (PI): the menu named 'Choosing stimulation settings' twice; the platform page is 'Analysis builder' again (ed112d74)
- [x] Baseline: the live RCS08 two-stage response saved before the change, for Phase 4
- [x] Response field: `audit.left_contacts` and `frozen_configuration.incumbent_left_contact`
- [x] Page: groups/rows/pooled surfaces keyed on contact and named; per-contact sentence (171 page tests pass); rebuild running
- **Status:** complete

### Phase 4: Proof and record (done with step A: live diff, suites, decisions 344-346, commit b4a90d8e)
- [ ] Equality proof on live RCS08: field count and difference count, before and after; every difference explained
- [ ] Both suites; page tests and rebuild if the page changes
- [ ] Decision line in DECISIONS_and_open_items.md Part 3 and a full row in docs/decision_log_full_2026-09-19.md (include the Sarikhani 2022 correction)
- [ ] Commit and push
- **Status:** pending

### Phase 5: Step B, partial pooling across Left contacts (offline first)
- [x] One fit: shared surface over (log2 rate, L current, R current) + a per-Left-contact deviation whose size is estimated (routines/contact_pooling.py, 6 tests)
- [x] Judge by leave-one-day-out prediction of held-out stretches' pain, against step A (separate surfaces) and the old pooled model; mean absolute error with interval
- [x] Reported (decision 347): contact effect only with pulse width ignored (confounded); no gain over step A at home -> NOT wired into Stage 1; D waits
- **Status:** complete

### Phase 6: Step C, the model picks the next clinic block
- [x] Between visits: which (Left contact, rate) block to test -- ranked most promising first (PI), server side, decision 348; 47 of 48 tie on RCS08, so no single block is offered
- [x] PI: borrow across rates AND pulse widths (decision 349); 30 blocks still tie (contacts with < 8 stretches)
- [x] Sheets checked: Left C+1-2- with current 2025-10-30 to 2026-02-03; device history disagrees (decision 350)
- [x] Page: two lists (NextBlocksCard), decision 350
- [ ] Within a visit: the fixed 0.5 mA up / 1.0 mA down ladder; block order randomised; feeds the titration card and its sheet
- **Status:** in_progress

### Phase 7: Every visit sheet, every tab, REDCap gaps, exposure, and the parsing record (the PI, 2026-10-01)
- [x] Sync all sheets from Drive: 3 downloaded (09_24_26, 09_30_26 new; 09_16_26 changed); 32 workbooks, 546 rated steps stored
- [x] Find pain ratings on other tabs: the Notes tab (32/32 workbooks) holds TIMED verbal ratings (Time, Current verbal pain score, Head, BACK, Left LEG, ...); REDCap tab empty; prototype: 882 step rows, 426 unrated, Notes fills 35, 65 have no time
- [x] Design: keep unrated step rows (rating_source None); a two-row step's ramp row is not 'unrated' when its test row is rated; Notes fill at parse (rule version bump); REDCap fill at load (survey belongs to the step in force when filed, within start + duration + grace; VAS/10); load_clinic_steps stays rated-only; load_clinic_exposure returns all
- [x] Then REDCap: 6 steps filled (filing time, step in force, VAS / 10)
- [x] Unrated steps count as EXPOSURE; untimed unrated = planned only (09_24_26)
- [x] CLAUDE.md section 10; docs/clinic_sheets_parsing.yaml (generated from data, yaml.safe_load-checked)
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Step A before step B | Stop the silent pooling first; B is judged against A's contact-by-contact surfaces |
| 0 mA epochs carry no contact | 13 Left C+1-2- epochs have Left at 0 mA; the contact label means nothing when no current flows |
| Right contact stays pooled | 77 of 80 epochs on R C+1-2-; nothing to group |
| Left-0-mA stretches are shared into every Left contact group (PI, 2026-10-01) | no current, so the contact makes no difference; they are each contact's zero-current point |
| Contact goes into every group label, not a filter to the contact in force (PI, 2026-10-01) | each (pulse widths, Left contact) gets its own surfaces and the frozen setting can choose between contacts; touches ~44 server lines and ~18 page files |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| jg: Codiv network error, results incomplete | 1 | Re-ran after the PI said Codiv was back; complete |
| REDCap unreachable from the container | 1 | The saved copy of the pain reports was used; say so beside any count |
| git commit: "1Password: failed to fill whole buffer" (commit signing) | 2 | The PI unlocked 1Password; commit 946d378a went through |
| Container bridge stalled (heartbeat 2530 s, last poll 00:54) while the suites ran after the contacts_short move | 1 | Runbook §1: an OrbStack container restart, which only the PI can do; asked him |
