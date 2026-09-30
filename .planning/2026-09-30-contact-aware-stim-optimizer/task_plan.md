# Task Plan: Contact-aware Stim Optimizer

## Goal
The Stim Optimizer's pain model knows which contacts were stimulating, so it stops pooling different Left contact configurations as if they were one.

## Next Step
Phase 2: find with jevgrep how Stage 1 groups epochs by pulse width, and search the decision record for rulings on contacts.

## Current Phase
Phase 2

## Scope and authority
The PI's answers of 2026-09-30:
1. Rule 13 ("never pool across electrodes") covers RECORDING electrodes only, not stimulating contacts.
2. The in-clinic rating chooses the next block; home ratings confirm it. Never merged.
3. Go-ahead for step A (Phases 2-4 below).
4. Remove today's visit plan entry (Phase 1).

Steps B (partial pooling across contacts), C (the model picks the next clinic block) and D (contact
as a position on the lead) are NOT authorised yet (rule 8): each needs its own go-ahead.

## Phases

### Phase 1: Remove the 2026-09-30 visit plan entry
- [x] Test first: RCS08 has no visit plan entry (watched RED, then GREEN)
- [x] Empty `VISIT_PLAN_BY_UID` (mechanism kept; its test runs on a constructed entry)
- [x] Both suites (host 1817 passed / 2 skipped / 0 failed; container PASS=945 FAIL=0); commit and push
- **Status:** complete

### Phase 2: Discovery for step A
- [ ] With jevgrep: how Stage 1 splits epochs into pulse-width groups (the minimum count, the key, which group the recommendation and the 55 Hz pain map read)
- [ ] Search DECISIONS_and_open_items.md for earlier rulings on contacts in the model
- [ ] Record in findings.md
- **Status:** in_progress

### Phase 3: Step A, the Left contact as a grouping key
- [ ] Tests first: a constructed record with two Left contact configurations gives two groups; the pain map at 55 Hz reads only the group for the contacts in question; the page is told the count per contact
- [ ] Add the Left contact configuration (the active contacts only, so 0 mA carries no contact) to the grouping key beside pulse width
- [ ] Response field: epochs, reports and days per Left contact configuration
- **Status:** pending

### Phase 4: Proof and record
- [ ] Equality proof on live RCS08: field count and difference count, before and after; every difference explained
- [ ] Both suites; page tests and rebuild if the page changes
- [ ] Decision line in DECISIONS_and_open_items.md Part 3 and a full row in docs/decision_log_full_2026-09-19.md (include the Sarikhani 2022 correction)
- [ ] Commit and push
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Step A before step B | Stop the silent pooling first; B is judged against A's contact-by-contact surfaces |
| 0 mA epochs carry no contact | 13 Left C+1-2- epochs have Left at 0 mA; the contact label means nothing when no current flows |
| Right contact stays pooled | 77 of 80 epochs on R C+1-2-; nothing to group |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| jg: Codiv network error, results incomplete | 1 | Re-ran after the PI said Codiv was back; complete |
| REDCap unreachable from the container | 1 | The saved copy of the pain reports was used; say so beside any count |
| git commit: "1Password: failed to fill whole buffer" (commit signing) | 2 | Stopped; signing not bypassed; asked the PI to check 1Password |
