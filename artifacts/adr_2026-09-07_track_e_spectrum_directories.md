# Decision record for the PI: the two spectrum directories, and the statistics site — for sign-off, nothing changed

**Written 2026-09-07 as Track E step 1 ("Write the decision record before changing anything").
No code on the live path was changed for this record. Every number below is from a run made on
2026-09-07 through the container bridge on RCS08.**

## What exists

Two spectrum caches live outside the one store, under `<data>/cache/`:

| Directory | Files | Size | Written by | Read by (measured) |
|---|---|---|---|---|
| `biomarker_psd` | 98 | 506.2 MB | `warm_psd_cache`, submitted to a background pool by the biomarker page's availability build; it assembles one whole-participant spectrum matrix per key | the biomarker page (1 read per request), the closed-loop report (1), the band validation (1) |
| `biomarker_psd_rows` | 6,309 | 30.5 MB | the same warm path, one file per recording, keyed on the recording's database identity so an already-computed recording is not decoded again | no page request: 0 reads during the biomarker page, the band sweep, the closed-loop report, the optimizer request and the band validation. Read by the band-conversion panel endpoint (`band_psd_lsb_conversion`) and by the warm path itself |

The biomarker page computes 381 Welch spectra fresh on every request (`welch_psd_for_instance`,
one per time-domain recording), which under the profiler was 10.3 s of an 85 s page and in an
unprofiled run is inside a 52 s page.

## Do the stored per-recording spectra equal a fresh computation?

Yes, exactly. `_assemble_psd_rows_cached` was run twice on RCS08, once reading the files and once
with `force_recompute=True`:

| | Rows | Recordings | Time |
|---|---|---|---|
| from the files | 6,219 | 826 read from files, 0 computed | 0.54 s |
| computed fresh | 6,219 | 826 computed | 3.00 s |

Row for row (channel, source and time): 0 rows only in one side, 5,795 distinct keys in both;
**547,118 values compared, 0 differences**, across every power value, every frequency axis and
every duration.

## What connecting the live path to the stored spectra would change

The page's 381 fresh Welch computations would become file reads. The measured saving is the
difference between 3.00 s and 0.54 s for all 826 recordings, so **about 2.5 s of a 52 s page**;
the review's projection of up to 4.05 s was not measured then, and the measured figure is smaller.
The numbers would not change: the equality above is the proof. The cost is a second reader of a
cache whose key is the recording's database identity plus the Welch window, which is the same
rule the store uses for the tiles, so it could be moved into the store as a raw kind with the
same key.

## The statistics site, `compute_psd_pain_correlation`

It computes its own spectra inside the correlation pass, verbatim from the source notebook, and
does not read either directory. Pulling the spectra out of it would change nothing numerically
only if the same `welch_psd_for_instance` with the same window and channel order is used, which
the equality above suggests but does not prove for that call site, because its inputs are the
epoch streams rather than the stored recordings. **It is not touched here and should not be
touched without the second sign-off the plan requires.**

## The one decision, with a recommendation

Open item 7 says the 6,309-file directory must be settled in one decision with this track. The
options:

1. **Delete `biomarker_psd_rows`.** It is read by no page request. It is read by the
   band-conversion panel endpoint and by the warm path, both of which recompute correctly when it
   is absent (the warm path decodes what is missing). Saves 30.5 MB and one resolver outside the
   store. Costs a slower warm after each upload and a slower band-conversion panel.
2. **Keep it and move it into the store as a raw kind** keyed as it is today, so the one-store
   test stops grandfathering it. The live page would then read it as well, for about 2.5 s.
3. **Leave both as they are**, and record that the assembled matrix is live and exact.

**Recommendation: option 2 for the per-recording spectra and, in the same step, the assembled
matrix**, because both are exact, both are keyed on the recording set alone, and the store
already has a lock, a stamp and a provenance chain that neither directory has. The saving on the
page is small and is stated as small. Option 1 is safe if the 2.5 s is not wanted. Neither
option touches the statistics site.

**Nothing in this record has been done. It is the input to the sign-off.**
