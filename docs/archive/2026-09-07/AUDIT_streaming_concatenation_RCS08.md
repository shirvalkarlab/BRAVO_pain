# Audit — BrainSense streaming concatenation (RCS08)

**Question (from HANDOFF_biomarker_20260623_2058):** are sequential, time-separated streaming
sessions being concatenated into one continuous recording somewhere upstream of the biomarker
pipeline? The prior session read `saveBrainSenseStreams` only as far as the hemisphere-pairing
block and concluded "no cross-time concatenation in that function." **That conclusion was
incomplete.**

**Verdict: CONFIRMED.** `saveBrainSenseStreams` *does* concatenate across time — in its
`FixBreaking` block (BrainSenseStream.py lines 181-257), which the prior read stopped short of. It
fires on real RCS08 data. The merge zero-fills the inter-recording gaps and those zeros flow into
the Welch PSD unmasked. Details below.

## Where the concatenation lives

Chain: real Percept JSON → `Session.decodeMedtronicJSON` → `Session.py:423`
`BrainSenseStream.saveBrainSenseStreams(StreamingTD, StreamingPower, FixBreaking=JSON["AutomaticStreamingFix"])`.
The `FixBreaking` flag is `JSON["AutomaticStreamingFix"]`, set in `DataCurator.py:146-150` from
`source_file.metadata["automatic_concatenation"]` (default True on ingest).

The `FixBreaking` loop walks consecutive `TimeDomainRecordings` and **merges** a pair
(`np.concatenate` at line 242, then `del` the second record at 257) when ALL of these hold:
1. identical `ChannelNames` on both the TD and the paired Power recording (line 187);
2. identical therapy descriptor, ignoring Lower/UpperLimitInMilliAmps (line 202);
3. 2nd stream's start stim amplitude == 1st stream's end amplitude (line 213);
4. inter-recording gap `Timeskip` in `(-1 s, 30 s]` (lines 227-235). **The 30 s ceiling was
   deliberately raised** ("updated to 30 seconds break only in favor of AnalysisBuilder customized
   inclusion", line 228).

When it merges, the gap is **zero-filled**: `nSampleSkipped = int(Timeskip * fs)` zeros are inserted
into `Data` and marked 1 in `Missing` (lines 238-243). Power/stim is filled by holding the start
amplitude (line 251).

**Important gate (line 170):** the whole `FixBreaking` block is wrapped in
`if len(TimeDomainRecordings) == len(PowerDomainRecordings)`. When the TD and Power recording counts
differ, the merge is **skipped entirely** regardless of the flag.

## Empirical results — real RCS08 JSONs decoded through the live chain

Decoded with the faithful Django-free chain (`Percept.decodeJSON` → `extractPerceptJSON` →
`saveBrainSenseStreams`), reading the source JSONs directly from the OneDrive grant (no patient data
copied into the repo). Of 6 RCS08 session JSONs, 3 contain `BrainSenseTimeDomain` with >1 distinct
`FirstPacketDateTime` (cross-time candidates):

| Session JSON (RCS08)        | TD streams | recTD | recPW | guard (recTD==recPW) | FixBreaking fired | pairs merged | gaps bridged (s) |
|-----------------------------|-----------:|------:|------:|:--------------------:|:-----------------:|-------------:|------------------|
| ...20250821T142630          | 15         | 9     | 9     | True                 | **YES**           | **3**        | 4.8, 6.5, 26.0, 7.2 |
| ...20250904T142339          | 28         | 14    | 15    | False                | no (guard failed) | 0            | — (would-merge pairs existed but block skipped) |
| ...20250918T114536 (.DB)    | 18         | 9     | 9     | True                 | **YES**           | **1**        | 29.5, 25.5, 5.8, 3.0, 3.0, 5.8 |

- **20250821:** recordings [0]+[1]+[2] fused 19:47:27 → one 1325 s block; [3]+[4] fused across a
  **26.0 s** real gap that was zero-filled (~6 500 samples), raising the block's Missing fraction
  0.007 → 0.063.
- **20250918:** [1]+[2] fused across **29.5 s** and **25.5 s** gaps (~7 375 + ~6 375 zero samples),
  raising Missing 0.000 → 0.031.
- **20250904:** four adjacent pairs satisfied criteria 1-4 (gaps 0.8/2.2/10.0/7.0 s) but
  `recTD(14) != recPW(15)`, so the guard skipped the merge. The would-merge gaps prove the gate is
  the only thing preventing concatenation here — a fragile, count-coincidence safety.

## Downstream impact on the biomarker (the part that matters)

The TD→Welch path does **not** respect the `Missing` mask:
- `adapter.bravo_timedomain_to_streamdata` (adapter.py:35-60) reshapes `recording["Data"]` and
  reads `StartTime`/`SamplingRate` only — it never touches `recording["Missing"]`.
- By contrast the **PowerDomain** adapter (adapter.py:385-397) explicitly drops `missing>0` samples.
  The two adapters are inconsistent.
- `streaming_psd.welch_psd_for_instance` / `welch_rating_centered` (the TD Welch transform) have no
  within-epoch Missing handling; the MAD rejection operates *across* epochs, not on zero-filled
  samples *within* an epoch.

**Consequence:** the zero-filled gap samples from `FixBreaking` enter the Welch PSD as genuine
zeros. A 30 s zero-fill inside a 30 s-epoch Welch window biases the spectrum (broadband power
deflation + spectral leakage) and shifts the rating-centered epoch boundaries, contaminating band
power exactly where a biomarker is read. This is a correctness risk for band-power validation, not
cosmetic.

## Recommended fix (decision required — see options)

The decode (concatenation + Missing labeling) is arguably correct *as a data model*; the defect is
that the **TD→Welch consumer ignores the Missing mask** while the Power consumer honors it. Options,
in increasing scientific weight:

- **A (parity, recommended): make the TD adapter Missing-aware.** Exclude any Welch epoch whose
  Missing fraction exceeds a threshold (e.g. >5-10 %), mirroring what the Power adapter already does
  for samples. Lowest-risk correctness fix; does not change the decoder. Needs a cache-key bump.
- **B: lower/parameterize the 30 s merge ceiling** back toward a true "dropped-packet" scale
  (≤ ~1-2 s) so only genuine packet drops are bridged, not 26-29 s clinical gaps. Changes decode for
  everyone; revisits the deliberate AnalysisBuilder choice behind the 30 s value.
- **C: leave decode as-is, document, and rely on the count guard.** Not recommended — the guard is a
  coincidence (`recTD==recPW`), not a safeguard, and fired-merge sessions already exist in RCS08.

Reproduction harness and per-pair numbers were generated this session against the live OneDrive
JSONs; no patient data was copied into the repo.
