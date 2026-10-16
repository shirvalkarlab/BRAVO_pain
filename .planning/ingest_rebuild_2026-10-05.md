# Ingest rebuild (the PI, 2026-10-05)

Goal: every neural data type in every Percept export is ingested, on the tablet clock, independent of
pain matching; then the whole record is re-ingested (scratch database `BRAVOReingest` first, compared
with the exports type by type, then live with a backup).

Rules from the PI: no patchwork backfill; events with no neural data are dropped; a recording missing
one data type keeps the types it has, and the missing type contributes no time to matching.

| Step | What | Status |
|---|---|---|
| A | Events: merge copies across exports (attach PSD, missing side, empty SenseID); drop events with no neural data; one ingest at a time per participant | Done (439) |
| B | BrainSense streaming: TD stored even when band power fails; one bad recording skips only itself; single-packet fragments kept | Done (440) |
| C | Montage PSDs attached to their own montage, not every montage in the export | Done (442) |
| D | **MUST DO (the PI, 2026-10-05, no further prompting):** ingest ALL of BrainSenseSurveys (every mode), BrainSenseSurveysTimeDomain (every mode), MostRecentInSessionSignalCheck (compare to every other PSD of the session; any not bit-identical ingested, stamped with the session start in tablet time), Thresholds band-power streams (wire as the PSD->LSB calibration check, Biomarkers page and every module that shows it). Drop ONLY bit-for-bit duplicates of an ingested recording; one bit off = ingest, time-stamp, use for matching. Collect every montage type. Read the Percept manuals, white paper and data-type handoff document. | Done (443, 446, 447) |
| E | Chronic log: verify union and agreement on re-ingest (audit: 0 missing, 0 differing) | Done: chronic counts identical on re-ingest (439) |
| F | Extractor failures recorded on the export's row and reported | Done (441) |
| G | Re-ingest in session-date order | Done (439, 453) |
| H | Tablet clock for every type (clock audit pending) | Done (444): 0 s difference across 587 exports |
| I | REDCap: 1 dropped one-off report, other instruments with pain scores (the 8 repeated reports are independent ratings, the PI 2026-10-05: keep) | Done (448) |
| J | Matching reads only data present (no time from a missing type) | Done (446) |
| K | Full re-ingest in scratch; per-type counts against the exports; then live | Done: scratch 2026-10-05 (439); live 2026-10-05 08:17 UTC, 586 ingested, 1 identical copy skipped, 0 failed; 2,246 recording files, 0 unreferenced (checked 2026-10-06) |

Audit numbers to reproduce after re-ingest (exports): events with a PSD 810; BrainSense TD start times
316; band power 300; indefinite 118; montages 269; baseline tests 67; calibration 126; electrode
identifier 62; chronic left 21,880 and right 32,909 readings.

**Never discard intact neural data of any kind (the PI, 2026-10-05).**
