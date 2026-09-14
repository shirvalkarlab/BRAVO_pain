# Findings: Make Closed-Loop Work

## 1. The ledger on RCS08, committed band L 0-2+ at 24.5 Hz, measured 2026-09-12 (probe_ledger_rows.py)
51 rules checked: 1 fail, 4 unknown, 27 advisory, 1 deferred. Verdict `blocked`.

| Rule | Bucket | Why, measured | Where the value lives |
|---|---|---|---|
| D16 impedance | FAIL | worst bipolar pair on Left = 10261 ohm > 10000 open limit (pair 2-3); the committed band's own pair 0-2 reads 6209 | impedance recording metadata; top-level `Amplitude` = measurement current |
| D19 polarity | unknown, "inputs not supplied" | pipeline withholds a sign unless the edge is resolved; E1 -4.45 (CI -18.6..9.7, p 0.54), E2 AUC 0.588 (CI 0.477..0.695, 27 reports), E3 -0.154 resolved. Observed pattern (-,+,-) EQUALS the expected pattern | edges; E2 computed on the module's own 27-report table, "the exported table is the intended route" |
| D27 capture artefact | unknown | pulse_width_us None; capture_amp_high_mA 5.0 present; capture_pulse_width_us 100 present but not read by the rule | epochs: pw_us_Left 100, pw_us_Right 150 |
| D30 rate committed | unknown | `rate_committed_for_this_attempt` / `frequency_search_closed` sent by nothing | a declaration; device has sensing/active groups at 55 Hz |
| D31 BrainSense envelope | unknown | rate_hz None, pulse_width_us None; with 55/100 Left the pair table returns True (280 records) | epochs newest: freq 55, pw L 100 / R 150; BRAINSENSE_PROGRAMMED_PAIRS |
| D44 rate floor | advisory not determinable | rate None | same as D31 |

Page sends `rate_hz: null, pulse_width_us: null` (useDeploymentReport.js) because the band candidate
committed from the grid carries neither. `pipeline._facts_for` fills a None candidate key from device
facts, so adding hemisphere-resolved `rate_hz`/`pulse_width_us` to `dev` in adapter.py is the wiring.

## 2. Impedance measurement current (probe_imp_amplitude.py)
563 recordings. `Amplitude`: "Automatic increasemA" 545, "0.4mA" 17, "1.0mA" 1.
Left max > 10000 in 351 of 544 automatic-increase records; 0 of 18 fixed-current records
(0.4 mA median max 7199; 1.0 mA 5363). Pair (0,2) Left ~5900-6200 in every record.
The PI's statement is confirmed by the record: high readings come only from the default low
stepping current.

## 3. Newest exposure epoch (evidence_inputs_cached)
epoch 123, from 2026-09-03 20:07 UTC, open-ended: 55 Hz, L 3.0 mA / 100 us cathode 2a-2b-2c,
R 2.5 mA / 150 us. Columns: freq_hz, amp_mA_{Left,Right}, pw_us_{Left,Right}, cathode_{Left,Right}.

## 4. The device's ACTIVE group today, read from the raw session reports (probe_active_group.py, decrypted via DataCurator.loadCacheFile)
Every report 2026-09-05 .. 2026-09-11 (six newest): Group D ACTIVE, sensing configured, rate 55 Hz,
sensing pulse widths [100 Left, 150 Right], AdaptiveTherapyStatus RUNNING on both sides. Group A
(inactive) is 55 Hz too, adaptive NOT_CONFIGURED.
=> D30 option (a) is satisfied on the record: 55 Hz is already frozen in the active BrainSense group.
=> The device is currently running adaptive DBS. The page's verdict "blocked" describes eligibility
   of the candidate on the module's rules, not what the device is doing.

**The committed summary `ClosedLoopDeployment/_facts_RCS08.json` is STALE**: scanned 2026-09-05 from
1,154 files; says newest active sensing group rates_seen [110], pulse_widths_seen [100],
adaptive_status_newest NOT_CONFIGURED, capture_newest at 110 Hz. The raw files say 55 Hz / RUNNING.
`session_report_facts.scan_folder` reads a plain-JSON folder (the shared drive), never the
ingested encrypted files, so nothing refreshes it. D32's four inputs, D28's limits, D17's artefact
rate, D09's spectrum and D27's capture pulse width all come from it.
Raw files on the container are Fernet-encrypted at `SourceFile.pointer`; `DataCurator.loadCacheFile(sf)`
returns the plain bytes.

## 5. Sizing a live session-report scan (measured on the container)
RCS08 has 572 ingested session reports on the server (the 2026-09-05 scan read 1,154 files from
the shared drive -- duplicates the ingest's hash check removes), 4,079 MB in total, largest 130.8 MB.
Decrypt + parse of the 20 newest (daily home exports, small): 1.34 s. A whole-record scan is
minutes and belongs off the request path (the daily precompute loop) with the stored summary keyed
on the session-report file set; the committed file stays as the fallback, dated on the provenance.
