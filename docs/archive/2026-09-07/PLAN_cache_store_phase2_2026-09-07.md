# IMPLEMENTATION PLAN — the cache store as a two-way bus

**For the new session.** Branch `PS_closedloop_deployment`. Approved by the PI on 2026-09-07.
Companion to `SESSION_HANDOFF_2026-09-07_cache_store_takeover.md`, which carries the measurements,
the reading order and the traps. **Read that first; this file is only the work.**

Step titles below are **verbatim from the approved plan** so progress can be reported against them
without renaming anything.

---

## BEFORE YOU START

1. **Read the documents in the order given in §0 of the takeover handoff.** In particular
   `HANDOFF_TD_LSB_calibration_2026-06-27.md`, which **overrides §4 of the design ledger** on
   band-power units.
2. **Load the skills.** Every BRAVO skill (`bravo-session-rules`, `bravo-stimoptimizer-figures`),
   the Plotly and visualisation skills (`ps-plotly`, `ps-scientific-visualization`,
   `figure-style`), `code-review` for the architecture audit, and `ps-statsmodels` for anything
   inferential. **The PI asked for this explicitly and it is not optional.**
3. **Confirm the module architecture before writing the store.** Use the review skill to check the
   shape below against the code as it stands, and say so if the code disagrees with this plan.
4. **The PI gives a manual go-ahead before implementation.** Plan approval is not execution
   authority — his rule, stated twice.

---

## TWO STEPS IN THIS PLAN ARE ALREADY SETTLED — DO NOT REDO OR RE-ASK

**1. The band range is decided. The plan text still says "CONFIRM THE BAND RANGE FIRST" — that is
now answered.** The PI's flowchart note said "bands 8-20"; he corrected it in conversation:

> *"I meant all the bands that this week already covers from 8.5 to 29.5 Hz."*

**Use all 22 band centres, 8.5 to 29.5 Hz.** Taking 8–20 Hz literally would have dropped the 22 to
27 Hz range holding this record's clearest and best-resolved amplitude response.

**2. "Fix the Redis memory limit and eviction policy first" is DONE — commit `b7036bf`.** It was
authorised out of order because it was a live hazard. `maxmemory 512mb` and
`maxmemory-policy allkeys-lru`, applied live and set durably as a `command:` on the redis service in
**both** `docker-compose.yml` and `Docker/docker-compose.yml`. **Verify it is still in force rather
than trusting this line**, then mark the step complete and move to the build lock.

---

## PHASE 1 IS DELIVERED — DO NOT REPEAT IT

Six steps, all complete, outputs saved as `CACHE_MAP.md`, `cache_map.png`, `cache_map.excalidraw`,
`cache_map.html` and `build_cache_map.py`. Its findings are summarised in the takeover handoff:
four cache directories under one root totalling about 782 MB, two duplicated store implementations
with mismatched caps, no on-disk cache in Stim Optimizer at all, and the visit sheets never reaching
the server.

---

## PHASE 2 — SEVEN TRACKS, 30 STEPS

### Ordering, because it is not arbitrary

**Track A must come before any track that writes to the store.** Everything else can be sequenced
for convenience. The reason is in the first two steps of Track A and it is the whole reason the rest
is safe.

```
A. Two-way bus          <-- provenance FIRST, then the writers
B. Canonical form       <-- independent of A, can run alongside
C. Cache and dates      <-- needs A's single store
D. Readers              <-- needs B's form
E. Statistics site      <-- gated on a SECOND sign-off from the PI
F. Redis wins           <-- memory step done; the rest independent
G. Closed-loop fixes    <-- independent; the triangle is a display bug
```

---

## TRACK A — "Two-way bus" (8 steps)

The PI's four red arrows make all three modules **writers** and let one module consume another's
computed output through the store. **This is the architecture change; the rest of the plan is
plumbing around it.**

**1. Build the one store implementation as a superset, and delete the duplicate**
His note: *"fix this so only one implementation exists as a superset callable by any module that
needs it"*. One module owns the store; every operation takes a `kind` argument;
`Biomarkers/bravo_service.py` and `ClosedLoopDeployment/adapter.py` stop carrying their own
duplicated resolver, loader, writer, event counters and lock **with their mismatched 1074 MB and
268 MB caps**. Add a test that fails if any code resolves a cache directory of its own. Delete
`biomarker_psd_rows` — his "(DELETE ME)", 6,309 files, **zero reads measured** — only after
verifying its removal breaks nothing.

**2. Give every written-back product a provenance chain, not just a version**
**THE LOAD-BEARING STEP.** The four arrows close a cycle: **Stim Optimizer would read a ground-truth
verdict computed from data Stim Optimizer itself chose to collect**, making the exploration policy
self-confirming with no crash to reveal it. So each product stores **the keys of every input it
derived from**, a module **refuses** to consume a product whose provenance contains that module's
own current output and says so, and the chain is queryable. **Prove the refusal fires with a
deliberately constructed cycle rather than asserting it cannot happen.**

**3. Put the provenance and version ledger in MySQL**
One append-only row per written-back product: its key, what wrote it, when, which inputs it derived
from, and the recipe version. MySQL rather than a file because it is small, heavily queried, needs
joins to answer *"which biomarker run informed this exploration queue?"*, and must be backed up with
the rest of the database. Round trip measured at **0.031 ms**.

**4. Store the REDCap frame, and keep the freshness fetch anyway**
The pain-report frame is stored with the other caches, as **Parquet with zstd**. State honestly in
the code that this buys **reproducibility and a key for derived products, not speed** — the fetch is
only 0.651 s. **The fresh fetch on every request STAYS**, and a test must prove a newly filed report
changes the answer. Reports are filed continuously, and serving a stored snapshot unchecked is **the
one failure in this system with no visible symptom**: every correlation and every "established"
verdict computed on an incomplete set while the page looks completely normal.

**5. Write the therapy and pain matched table into the store**
His note: Stim Optimizer *"should load cached therapy settings already time matched to redcap
scores"*. **This product has never existed as a stored table.** Parquet with zstd, keyed on both the
recording set and the pain-report snapshot signature.

**6. Write the biomarker results back after computing them**
His top note: push results to the cache with version control, including the assembled matrices of
biomarker performance across bands. Two new tables, per band centre and per contact pair: the
correlation results and the discrimination results. **Band range settled at all 22 centres, 8.5 to
29.5 Hz — see above.** Every area-under-curve value is referenced to **0.5**, never 0.

**7. Write the amplitude effect on each band where Stim Optimizer can read it**
His realisation: *"the stim optimizer probably should read in the stim amp effects on biomarkers, to
decide what still needs to be explored"*. A new table of **slope, curvature, and the current range
actually tested** per band and setting, so the exploration queue is driven by which bands are still
unresolved rather than by coverage alone. Curvature matters here: a rise-then-fall response exists
in this record and a straight-line test reads it as no response.

**8. Have Stim Optimizer read the store and write its outputs back**
Close the loop his two arrows draw: load the matched table and the amplitude effects instead of
rebuilding the settings stream twice at **65.71 s**, and write its own four outputs back with
provenance so nothing is recomputed when nothing changed.

---

## TRACK B — "Canonical form" (5 steps)

**1. Promote the prototype to real code**
Move `DecodeCommon/representation.py` from the untracked prototype into the module proper with its
32 tests. Keep the rule that **the file converts nothing and stores no calibration constant**,
including the test that asserts the module source contains neither constant.

**2. Adopt it at the 72-million-call site**
Replace the spectrum-record scan inside `per_pro_lsb` with a lookup prepared once per request. This
is the line accounting for **99.87 percent** of the request's channel-name normalisations and
**9.51 seconds** of the page.

**3. Adopt it at the identical sibling scan**
Same change to `per_pro_lsb_spectrum`, which carries a byte-for-byte copy of that scan. **It is not
exercised by the default page**, so measure it on the band-by-length sweep instead and report that
figure as new rather than carried.

**4. Fix the repeated column resolution and float conversion**
Three sites re-scan and re-convert all **832 voltage traces roughly 30 times per request**. Route
them through the form's prepared per-channel column.

**5. Prove every number unchanged, then measure**
Compare the full payload field by field against the pre-change path on live data and **report the
field count and the difference count, not a tolerance**. Then time the page in **alternating
rounds** so the filesystem cache cannot favour whichever ran second.

---

## TRACK C — "Cache and dates" (5 steps)

**1. Move every cache to the single approved location**
All three modules and every dependent function at one place, with a test that fails if any code
resolves its own. **Format is decided: Parquet with zstd for every table** (0.027 MB against
pickle's 0.451 and CSV's 0.492 on the real 6,629-row therapy table). **Note honestly in the code
that pickle writes twice as fast and reads are tied** — Parquet is chosen for size and durability,
not speed. **CSV and JSON are excluded on correctness: the table carries a timezone-aware timestamp
and both lose it.** The large spectrum **arrays stay as compressed array files** in the same
directory, because they are not tabular.

**2. Implement the approved writing policy**
**The key decides, not the caller** — the PI adopted this over his own first proposal. A write
happens only when the key does not match what is on disk. The read path must be **read-only by
construction rather than by convention**, and a test must prove that opening a page leaves the cache
directory **byte-identical** when the key already matches.

**3. Stamp every cache with when and why it was written**
Inside each file: the write time, what triggered it, and how many recordings it covers — so a date
shown on a page is read from the cache itself rather than a file timestamp that a copy or backup
would falsify. The stamp is what the Redis freshness key mirrors, so the two cannot disagree.

**4. Show the last cache update on all three module pages**
In the payload and on screen for all three, **including the case where no cache exists yet**, with
wording saying what the date means so a stale page is distinguishable from a current one at a glance.

**5. Verify the pain reports stay out of the cached form and its key**
Confirm by test that no pain report or REDCap column enters the decoded form or its key, so a file
cannot serve a stale rating. Demonstrate that changing the report set alters the answer **while
causing no rebuild.**

---

## TRACK D — "Readers" (4 steps)

**1. Point the Biomarker reading sites at the form** — convert the `_load_recordings` call sites,
keeping the database type and sensing centre stamping that currently happens at decode time.

**2. Reduce the three spectrum builders** — establish which is authoritative, wire the others to it
or remove the dead one, and prove the surviving path returns identical values on live data.

**3. Point the Stim Optimizer and closed-loop reads at the form** — including the remaining
`settings_stream` consumer that still builds its own copy at **65.71 s across two passes**.

**4. Confirm both endpoints unchanged and faster** — identical field by field, then timings in
alternating rounds.

---

## TRACK E — "Statistics site" (2 steps) — GATED ON A SECOND SIGN-OFF

**1. Write the decision record before changing anything**
Set out exactly what pulling the spectra out of `compute_psd_pain_correlation` would change, given
its docstring records that **each step was ported verbatim from the source notebook**, so the
analysis arithmetic is unchanged. **Present it for a second sign-off rather than proceeding.** This
is the one site where computing the spectra and correlating them against pain happen in a single
pass.

**2. Connect the live path to the spectrum cache that already exists**
One builder maintains **6,309 cached spectrum files the live request never reads** — zero reads
measured. Establish whether the live path can read them and whether the values agree exactly. **The
review projected up to 4.05 seconds and did not measure it, so report the measured figure including
if it is smaller.**

> Note the tension with Track A step 1, which deletes `biomarker_psd_rows`. **These two steps concern
> the same 6,309 files and must be settled together**: either the live path reads them and they are
> kept, or nothing reads them and they go. Do not delete in one track and wire up in another.

---

## TRACK F — "Redis wins" (4 steps, first one DONE)

**1. Fix the Redis memory limit and eviction policy first — DONE, commit `b7036bf`.** Verify, then
mark complete.

**2. Add a build lock so four workers cannot duplicate a build**
**The strongest of the three, and the only one touching the 37-second build rather than a read.**
Nothing today stops all four workers independently starting the same tile build for the same
participant. Take a short-lived lock keyed on the same cache key. **Three hard requirements:** the
lock must **expire on its own** so a worker dying mid-build cannot wedge the participant
permanently; a waiter that times out must **fall back to building** rather than failing the page;
and **Redis being unreachable must degrade to today's behaviour** rather than breaking the page.
Prove it by starting concurrent cold requests and showing the build ran once.

**3. Move the freshness key and last-updated date into Redis**
Small values read on every request that must agree across all four workers — exactly what a
**0.037 ms** shared store is for. **The authoritative copy stays stamped inside the cache file**;
Redis holds a mirror so a page can answer without opening a 245.90 MB file. A missing or stale Redis
entry must fall back to reading the file stamp, **never to showing a wrong date.**

**4. Point Django's cache at Redis instead of per-process memory**
The backend is currently `LocMemCache` — per-process, the same defect behind the 47-second
cold-worker penalty — while `REDIS_HOST` is already set, so **Redis was intended here and never
wired.** Point the cache at it, **with `protocol=2` pinned** (this Redis is 5.0.14 and rejects the
modern handshake). **Do NOT move the large payloads there:** measured, Redis is about **three times
slower** than the file cache for the 245.90 MB tile store (0.14 s against 0.05 s) and marginally
slower even for the 0.027 MB therapy table, because the cache files are already in the operating
system's page cache and Redis adds a socket round trip on top.

---

## TRACK G — "Closed-loop fixes" (2 steps)

**1. Find out why the evidence triangle stopped displaying**
The PI: *"right now the triangle doesnt display properly, though it did in a prior mockup version"*.
**Specific lead rather than a guess:** earlier in the previous session a panel existed in the source
and in **no served bundle**, because source was committed without rebuilding the front end — and a
component in that state can neither render nor report a failure. **Check the served bundle before
touching any component code**, then fix whatever it actually is.

**2. Agree a ground-truth rule for the three-source comparison, then write it back**
The PI: *"The three-source comparison of how current moves biomarkers needs some kind of decision
rule to determine which data to use as ground truth and write back to StimOpt."* **Proposed for his
sign-off, not decided:**

> The device's own onboard reading is ground truth wherever it exists, because that is the
> measurement the control law will actually run on. The calibrated route from raw samples where it
> does not. **Never** the uncalibrated route.

**The limitation travels with the rule: the device computes its own power for only the single
programmed band**, so every other band falls through to the calibrated route by necessity rather
than by choice. Once agreed, write the verdict and the chosen source into the store for Stim
Optimizer — **subject to the cycle refusal in Track A step 2.**

---

## WHAT THE PI EXPECTS TO RECEIVE

1. One store implementation as a superset callable by any module, with the duplicate removed and `biomarker_psd_rows` resolved.
2. A provenance chain on every written-back product, and a **proven** refusal to consume a product derived from the consumer's own output.
3. Five new stored tables: the REDCap snapshot, therapy-and-pain matched, biomarker results per band, amplitude effect per band, and the ground-truth verdict.
4. A MySQL ledger recording what wrote each cached product, when, and from which inputs.
5. One canonical decoded form used by every module that reads recordings, enforced by a test.
6. Parquet with zstd for every cached table; compressed array files for the spectra.
7. The date of the last cache update stamped inside each cache and shown on all three module pages.
8. A Redis build lock proven under concurrent cold requests, and Django's cache pointed at Redis.
9. **Before-and-after timings in alternating rounds, and an exact-equality proof at every adoption step** — field counts and difference counts, never a tolerance.
10. The evidence triangle displaying again, and an agreed ground-truth rule written back.
11. Updated `MEGA_HANDOFF.md`, session handoff and design ledger. **The mega handoff's reference sections (§2, §3, §4, §7, §8) were NOT reconciled for the cache design and need it once the store is built.**

---

## FEASIBILITY, AS APPROVED

Medium confidence. Phase 1 is delivered and measured. The red edits turn the cache from a one-way
speed-up into the platform's data bus between modules, which is **a larger change than it appears**
and introduces a genuine dependency cycle. The provenance step is therefore ordered before anything
that writes back, and the cycle refusal is **proven by construction rather than asserted**. One item
remains open on the PI: **the ground-truth rule, which is a scientific choice and not an engineering
one.**
