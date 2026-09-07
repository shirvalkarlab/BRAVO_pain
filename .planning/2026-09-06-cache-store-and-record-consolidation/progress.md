# Progress log

## Session 2026-09-07 — takeover, and consolidation of the written record

**Took over from** `SESSION_HANDOFF_2026-09-07_cache_store_takeover.md`. Read the eight documents
in the order the PI set, plus the repository READMEs, the full project memory, and the Percept RC
document folder on the shared drive.

### What was read, in the order set

1. `SESSION_HANDOFF_2026-09-07_cache_store_takeover.md` — the reading order, the cache design, the
   format measurements, the last ten parallel lanes, the ten traps.
2. `PLAN_cache_store_phase2_2026-09-07.md` — 30 steps in seven tracks, with the two settled items.
3. The design ledger, retrieved from the artifact store as
   `f9b3d791-7e95-44bb-bd81-8aebcf9e1b3b` version `c7bf4b85-4867-4e3a-b8de-2ba900d1fd9b`, whose
   own title line reads revision 13. **It is not a file in the repository.**
4. `HANDOFF_TD_LSB_calibration_2026-06-27.md` — the calibration, the recipe, the per-recipe
   constant catalogue, and the seven catalogued errors.
5. `SESSION_HANDOFF_2026-09-06_sweep_ramp_and_matcher.md` — the previous session.
6. `README_CORRECTIONS_RECONCILED_2026-09-06.md`.
7. `README_BIOMARKERS_AND_DEPLOYMENT.md`.
8. `MEGA_HANDOFF.md` — header, the newest entry in §0, and reference sections §1 through §9 in
   full. **The older narrative in §0 was not read line by line**: it is 4,000 lines of
   session-by-session history whose durable content is what §1 through §9 exist to hold, and the
   two most recent sessions are covered by items 1 and 5 above. Stated rather than implied,
   because it is the one gap in the reading.

### Verified against the code rather than carried from the documents

Twenty-two constants and nineteen function definitions were read from the working tree at
`705bdb0`. **Every line citation in all eight documents has moved.** The current values and
locations are tabulated in `findings.md` §2, and they are what the replacement documents cite.

Two claims in the README describe machinery that **does not exist anywhere in the repository**:
the device-writing endpoint with its two environment variables, and a firmware version and value
range for the threshold. Both were confirmed absent by searching every Python and JavaScript file.

### Decided this session

**The ground-truth rule for the three-source comparison**, which the PI left open because it is a
scientific choice. Recorded in `task_plan.md` under Decisions Made, with the four conditions the
proposal needed. The proposal's precedence is accepted; what it lacked was a saturation ceiling
check on the stream it names as truth, the fold ratio between the two routes where both exist, a
rule that one-band coverage never reads as coverage, and the checked conversion span stated on
every row.

### Completed

- **Planning directory created** at `.planning/2026-09-06-cache-store-and-record-consolidation/`.
- **The supersession register is written** — 30 contradictions found across the eight documents,
  each resolved to the newer result, in `findings.md` §1. Four are marked as corrections to keep,
  because in those the mistake itself is the lesson.
- **Fourteen facts that appear in exactly one document** were identified as the items most at risk
  of being dropped in the port, and each is assigned to a replacement document. `findings.md` §3.

### Phase 1 delivered

**Five replacement documents at the repository root**, written against the supersession register
rather than by copying:

1. `DEVICE_percept_rc.md` — the three threshold modes and their fixed timing, the five recording
   products with their exact JSON keys, the two different quantities both written LSB, every
   calibration constant stated as what it converts from and to and **whether it was measured on
   simultaneous recordings or composed by chaining**, the transform recipe step by step, the
   harmonic landings by stimulation rate, the ramp measured across all 326 amplitude steps, the
   frozen per-participant model with its numbers kept verbatim, and the parsing traps.
2. `ARCHITECTURE_modules_and_store.md` — the three modules, the store as measured, the two
   duplicated implementations and their mismatched limits, the approved layout, the format
   comparison with its honest caveat, the Redis and MySQL facts, where a request actually spends
   its time, the three spectrum builders, and the named routines and response keys.
3. `METHODS_measurement_and_findings.md` — the measurement rules, the **two** different
   multiple-comparison corrections for the two different questions, the live results on RCS08 each
   with its limit, the ground-truth rule, and eight things that must never be claimed.
4. `OPERATIONS_runbook.md` — the container and the mount, the two test runners, how to make a
   backend and a frontend change actually take effect, and every trap already paid for.
5. `DECISIONS_and_open_items.md` — 34 numbered decisions with decision 20 marked superseded by 21
   rather than deleted, the single list of open items, and the commit lineage read from `git log`.

**One architecture drawing** — `bravo_architecture.html`, `.svg` and `.png`: the three modules, the
one store, the four arrows, the cycle they close, and where the provenance refusal sits.

**51 superseded documents archived** to `docs/archive/2026-09-07/` with `git mv` where tracked, so
history follows them, and an `INDEX.md` naming which replacement carries each one's content.
**Nothing was deleted.** Root markdown files went from 53 to 7.

**The port was machine-checked**, not asserted — `findings.md` §5 and `port_gap_report.json`. Four
groups of real omissions were found and ported: the response keys and routine names, the frontend
component files, the device JSON key spellings, and the commit lineage. Thirty-five flagged
identifiers were checked against the current source, all 35 are live, and all were ported. Seven
named scripts were confirmed session-only scratch and are labelled as such.

### The one honest gap in the port, stated rather than implied

**The mega handoff's §0 — about 4,000 lines of session-by-session narrative — was not ported line by
line.** Its reference sections §1 to §9 were ported in full, the two most recent sessions are
covered by their own handoffs, and the narrative remains in the archive. A future session that
needs the reasoning behind an older change should open the dated handoff rather than expect it in
the five replacements.

### Not done, and why

**No code has been changed and none will be until the PI gives an explicit go-ahead.** His
standing rule: a clicked plan approval unblocks the tooling only, and the second phase waits for
a spoken go-ahead. The one exception he authorised himself was the Redis memory bound, already
landed in `b7036bf`.

### Test and build state

**Not run this session.** No count is quoted anywhere in this session's output, and the
replacement documents carry the commands rather than a number.
