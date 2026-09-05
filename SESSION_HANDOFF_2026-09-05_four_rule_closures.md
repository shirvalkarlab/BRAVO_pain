# 2026-09-05 — the four blocking unknowns closed, and D19 left alone

Suite: ClosedLoopDeployment 192 -> **198 passed**. No change to D19.

## D31 — closed at 55 Hz, on measured evidence rather than an unpublished limit

**There is no declared BrainSense envelope anywhere.** The A610 guide says a BrainSense group has a
lower maximum pulse width, a lower maximum rate and a higher minimum rate than a group without it,
and prints none of the three numbers. A walk of **all 1,154 RCS08 session reports (0 unreadable)**
found no field carrying them either: the only path in the whole corpus combining a rate,
pulse-width or frequency name with a limit/min/max/range/bound word is
`IndefiniteStreaming[].SampleRateInHz = 250`, which is the sensing sample rate, not a stimulation
limit. So the rule as written would have blocked forever.

**Replaced with an answerable question**: has the device already accepted this exact rate and pulse
width in a BrainSense group on this hemisphere? A demonstrated configuration is stronger evidence
than a limit comparison, because it is the device's own verdict. The measured table is
`device_facts.BRAINSENSE_PROGRAMMED_PAIRS`, 19 pairs across the two hemispheres.

Observed envelope in sensing groups: rates 55 (3,382), 110 (1,300), 125 (80), 145 (454), 165 (474);
pulse widths 60 (4,128), 80, 100 (1,806), 120, 140 (704), 150, 160 (3,552), 180 (492). Non-sensing
groups run down to 10 Hz (1,930) while sensing groups never go below 55, consistent with the guide's
direction and bounding the BrainSense minimum at 55 Hz or below without revealing it.

**PI decision 2026-09-05: "we're gonna use 55 Hertz. That's it."** Recorded as
`deployment_rate_hz: 55.0`. On the LEFT, 55 Hz with 60 us has been programmed **1,274 times**.

**The hemisphere is load-bearing and pooling would be wrong.** 55 Hz/60 us appears 1,274 times on
the Left and NEVER on the right, where 55 Hz has only run at 150, 160 and 180 us. 165 Hz/60 us
appears 152 times on the Left and never on the right, where 165 Hz has only run at 80 and 160 us.
An undemonstrated pair returns **None, not False** — absence of evidence is not a prohibition, and a
test pins that.

## D32 — closed, plus a routing bug of the kind that has bitten this module before

PI stated no pocket adaptor; each lead connects to the Percept RC directly. Cannot be derived: no
field in any of the 1,154 reports records accessory hardware.

**The bug**: `has_pocket_adaptor` is a property of implanted hardware so it arrives on the
PARTICIPANT dict, while `_p_d32` read only the CANDIDATE. The rule reported not-determinable on a
fact that had been supplied — indistinguishable from the fact never being given. Candidate is now
consulted first (the A610 exclusion is per hemisphere, so a one-sided override must win) with a
participant fallback.

## D29 — closed on ring stimulation, with the number rather than the ruling

PI: "there are no vertically aligned segments that are stimulated anymore. It's all ring
stimulation." A610 p. 39 requires vertically aligned segments to share amplitude and electrode
polarity when BrainSense is configured, and that condition only arises under DIRECTIONAL STEERING.

**Measured, and not a clean zero.** 98.50% of segmented levels are ring-mode (13,918 of 14,130):
13,550 with all three segments at one identical fraction, 368 with a single segment active. The
remaining **212 (1.50%) do carry unequal fractions**, e.g. -21 with -9. The PI's word was "anymore",
so historical steering is consistent, but the flag is set on a 98.50% measurement plus a clinical
ruling, not on zero.

It is nonetheless right for this rule for an independent reason: those 212 are steered WITHIN a
level, while p. 39 compares ACROSS levels at the same angular position — and on that comparison the
amplitude mismatch count is **zero across all 17,102 aligned pairs**.

**My check misread this first time.** It flagged 600 pairs as mismatched; every one was a
ring-to-ring bipolar montage (level 1 at +21/64 anode ring, level 2 at -21/64 cathode ring). Equal
magnitude, opposite sign, which is what makes a bipolar configuration bipolar. Seeing segment NAMES
in the contact list is not evidence that steering is in use.

Contact naming trap: the device spells the same lead family two ways, `SenSight_1a` but
`Sensight_1b`. A case-sensitive parse silently loses the b and c segments — exactly the ones an
alignment check needs. The segmented rows are numbered **1 and 2**, not 2 and 3.

## D30 — reworded, not closed

The PI rejected the old framing: "of course, we can always test more open loop frequencies in real
life." The rule used to demand the open-loop frequency search be "closed", importing a permanence
the device does not require. The actual constraint (p. 34 fn a, p. 44) is operational: rate and
pulse width cannot be adjusted once BrainSense is set up in a group, and changing either costs the
group plus the threshold capture. The flag is now `rate_committed_for_this_attempt`, a per-attempt
acknowledgement; `frequency_search_closed` is still honoured so an un-updated caller does not
silently regress.

## STILL BLOCKING: D19 only, and it fails on evidence

Band power rises with amplitude where Dual Threshold needs it to fall, and higher power goes with
lower pain where the law needs the opposite. The polarity matches only Single Threshold Inverse,
which is Sensing Only and `can_drive_therapy=False`. No choice of thresholds repairs a sign.

## OPEN, carried forward

1. **The 165 -> 55 Hz switch invalidates the current screen output.** The deployability screen, the
   prescription table and all three edge estimates were computed for ONE_THREE_LEFT at 165 Hz. They
   must be re-run at 55 Hz. Do not relabel the 165 Hz figures.
2. **A 55 Hz harmonic folds to 25 Hz**, inside the 22-27 Hz band of the 24.5 Hz candidate (landings
   at 25 and 30 Hz at fs=250). Advisory by prior decision, but it should be surfaced for THIS
   configuration rather than left general.
3. **The Left hemisphere has had no active sensing group since 2026-03-31**; the Right has one from
   2026-09-03. A Left-sided candidate needs its sensing configuration re-established.
4. **The clinic step timeline is unfinished and its parse was discarded.** Drive folder
   `10uYVdcj_NGtepeiDF2qHn2bb-fwHqQcv` holds 32 files = 29 testing sheets + 2 templates + 1 Stage 1
   log. GOTCHA: `read_file_content` returns only SOME tabs — "Stim Testing" appears zero times in
   the flattened text of the July and Sept 2025 sheets — and a header-scan takes the FIRST matching
   table, which on those sheets is the observation tab. Use `download_file_content` with the xlsx
   export mime type and read the **Stim Testing tab only**. PI-confirmed cell convention: with any
   separator (`/` or `&`) the value BEFORE it is LEFT and after it is RIGHT. Of 449 non-empty
   amplitude cells only 22 carry L/R labels, and 314 of 631 rows are asymmetric, so getting the
   order wrong swaps half the record.
5. **The stratified amplitude result used the coarse join.** The 123-epoch reconstruction has a
   median epoch of **27.5 hours** (75 of 123 over a day, longest 89 days) built from only 1,189
   distinct settings timestamps over 20 months. It shows zero within-epoch amplitude variation, but
   that is circular — epochs are defined by changes in that same stream. It cannot see within-visit
   steps at all.
6. **The biomarker-side automatic table is designed, not built** — one column per pain metric,
   surviving positive bands with averaging duration, frequency and channel, computed once and cached.
7. **Only NRS has been swept.** left_leg_vas and MPQ with PSD-first matching have not been run.
