# Task Plan: The exploratory ladder for L C+1-2- on the Stim Optimizer page

## Goal
The Stim Optimizer's titration card carries a second ladder for the stimulation configuration the readiness screen's best left sensing pair requires (L 0-3+ needs stimulation on contacts 1 and 2, never yet powered): rate from that cell, its pain-positive bands to watch, a first-exposure stop rule, the up/down ladder for the biomarker's slope, and three timed on/off holds with a rating every minute for the acute pain effect; its rows go into the clinic sheet.

## Next Step
Watch the card live on the Stim Optimizer page once the PI has logged in to the browser pane (the only unticked step); everything else is built, proven and committed.

## Current Phase
Phase 3

### Phase 1: Backend
- [x] `titration_plan`: `stim_rings_for_sensing_pair`, `configuration_exposure`, `acute_pain_holds`, `configuration_plan`; `plan_for_sides` carries `proposed`; the flat sheet rows gain the exploratory blocks (tests RED first)
- [x] `titration_plan_block` builds `proposed[side]` when the best contact's pair needs other stimulating contacts than the ones in force
- **Status:** complete

### Phase 2: Page
- [x] The card's new section (four jest tests RED then GREEN); bundle rebuilt (chunk 100.18f67798); workers reloaded
- [ ] Watched live (the pane came back logged out after the session restart; waits on the PI's login)
- **Status:** in_progress

### Phase 3: Proof and record
- [x] Live response before/after: 8,821 fields in common, 8 differing (all store and cache bookkeeping), 1,630 added (904 under `titration_plan.proposed.Left`, 33 sheet rows x 22 columns), 2 removed (bookkeeping); host 1424 / 2 / 0, container 673 / 0; decision 230; pushed
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| The exploratory ladder runs at the rate of the cell where the pain-positive bands were found (125 Hz), not the rate in force (55 Hz) | at 55 Hz those bands (24.5-27.5 Hz) sit on the half-rate harmonic (27.5); at 125 Hz they are clear |
| Three 5-minute holds, off / on / off, a rating every minute, the patient blind to the current | the biomarker reads in 60 s; a pain change needs minutes and a washout to be believed |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
