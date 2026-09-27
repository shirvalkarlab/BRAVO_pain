# Every time field in RCS08's Percept exports, and how best to match band power to a pain report

2026-09-26. Read-only analysis following decision 328 (every Percept time on the tablet clock); recorded as decision 330. Nothing in the product, the database or the saved answers on disk was changed by this analysis. Scripts, all scratch: `BRAVO/_agent_bridge/_jsontime_fields.py` (the walk over every field), `_jsontime_detail.py` (time zone, anchors, odd fields), `_jsontime_match.py` (matching); outputs in `BRAVO/_agent_bridge/_jsontime_out/`. Page before/after counts are read from decision 328's captures (`BRAVO/_agent_bridge/_clock2/cap_{before,after}_grid_*.json`).

Words used here:
- **device clock**: the implanted stimulator's own date and time; on RCS08 it ran ahead of real time by up to 2.1 hours by September 2026.
- **tablet clock**: the clinician tablet's date and time, set from the internet.
- **device seconds counter**: the count of seconds the stimulator keeps beside its date (`...OffsetInSeconds`); each dated entry carries its own.
- **anchor**: for one export, the tablet time at which the device seconds counter would read zero (the tablet's save time minus the counter at the save). Decision 328 converts an entry as its own counter value plus the anchor of the export that first carried it.
- **match window**: how far either side of a pain report a band-power measurement may lie and still be paired with it (Biomarkers page's settings 5 minutes; daily defaults 60 minutes, at the time of writing).
- **TD**: band power from the time-domain recording, in 3-second pieces. **PSD**: the device's own 30-second snapshot, on RCS08 almost always triggered by the patient pressing the event button on her phone remote.

## Part 1. Every time field, and its clock

### How it was checked
All 583 stored exports for RCS08 were read raw, before conversion. Every value in every file was examined. A field was kept if its value looked like a date or time, if it was a number in the Unix-time range, or if its name held a time word (date, time, tick, offset, stamp, zone, UTC, duration, sync, and so on): 184 key paths.

Each dated field was compared, in every export, against three things:
- the export's `SessionDate` and `SessionEndDate`;
- the device's own date at the start and end of the session;
- the device date implied by the field's own counter (device date at the save, minus the counter at the save, plus the field's counter). A difference of 0 means the text is the device clock.

A tablet field stays within minutes of the session times however far the device has run ahead. The test was made in the 321 exports where the device ran more than 30 minutes ahead. No field holds a Unix-style number.

### The table
"Converted" means `MedtronicPercept/TabletClock.py` rewrites the field onto the tablet clock when the file is read. Counts are occurrences across all exports; entries are re-sent in many exports.

| Field | Count | Format | Own counter | Clock, and the evidence | Converted |
|---|---|---|---|---|---|
| `SessionDate` (top level) | 583 | `9999-99-99T99:99:99Z` | no | **Tablet, true UTC.** In the 321 large-lead exports it sits 920 to 7,708 s from the device's date. `ProgrammerUtcOffset` equals the Los Angeles offset at `SessionDate` read as UTC in 583 of 583, including 23 within 3 days of a daylight-saving change. Local hours 07:00 to 19:59 | no (correct) |
| `SessionEndDate` (top level) | 556, plus 27 empty | same | no | **Tablet.** 132 to 7,542 s from the device's date in the 313 large-lead exports; median 34 s after `SessionDate` | no (correct); the anchor's source |
| `DeviceInformation.Initial/Final.DeviceDateTime` | 583 each | same | yes | **Device.** Final fits its own counter in 583 of 583; Initial in 575 of 583 | yes |
| `EventSummary.SessionStartDate`, `.SessionEndDate` | 562 each | same | yes | **Device.** Counter fits in 561 of 561 and 562 of 562; the end equals the device's date at the save | yes |
| `FirstPacketDateTime` of BrainSenseTimeDomain (495), BrainSenseLfp (305), IndefiniteStreaming (693), LfpMontageTimeDomain (1,548), survey recordings (1,548) and electrode identifiers (308; plus 3,698 empty), SenseChannelTests (408), CalibrationTests (256), Thresholds (92) | 5,653 dated | `...99.999Z` | yes | **Device**; the counter fits every one. After conversion all 3,797 recording and test starts checked lie inside their own session | yes |
| Chronic log `LFPTrendLogs.<side>.<date>[].DateTime` (a reading every 10 min) | 51,430 right, 32,687 left | `...99Z` | yes | **Device**, stamped exactly 600 s before its own counter in 83,109 of 83,109 | yes, 600 s kept |
| The chronic log's date keys | 740 right, 432 left | `...99Z` | no | **Device** (up to 16 h either side of their first reading) | **no**; nothing reads them as times |
| `LfpFrequencySnapshotEvents[].DateTime` (patient events) | 46,400 (1,257 distinct) | `...99Z` | yes | **Device**, 46,400 of 46,400 | yes |
| The PSD inside an event, `<side>.DateTime` | 1,520 left, 4,992 right | `...99Z` | yes | **Device**; sits 30 s after its event (counter 30 more); the saved PSD pieces use this one | yes |
| `EventLogs[].DateTime` | 235,215 | `...99Z` | yes | **Device**, all of 150,000 checked | yes (234,877); 338 left out (clock block with no export); 793 via their block's latest export |
| `GroupHistory[].SessionDate` | 2,901 | `...99Z` | yes | **Device, despite the name** (2,877 of 2,877) | yes (correct) |
| `RechargeCount[].SessionStartDate` | 7,955 | `...99Z` | yes | **Device** (7,727 of 7,727) | yes (7,897); 58 left out |
| `Annotations[].Date` | 1,795 (two annotations, re-sent) | `...99Z` | yes | Block-1 one (100 copies): device. Block-43 one (1,695 copies): neither; its text is 13.6 to 15.8 h before its counter's device date and about 13.6 h before the tablet time the counter gives, and its counter changes between exports (three values 505 s apart) while its text does not | yes (moves it about 13.6 h); nothing reads the export's annotations |
| `DeviceInformation.*.ImplantDate` | ISO in 2 exports (same value); 7-character placeholder in 581 | `...99Z` | no | Cannot be told apart, and immaterial: in both exports the device read 2 s behind the tablet. The database's implant date, and so the start of every view, comes from it | no |
| `BatteryInformation.ERIDate` | 583 | `...99Z` | no | A projected replacement date, not a moment | no (correct) |
| `BatteryReminder.ReminderTime` | 568 | 5-character "hh:mm" | no | A daily wall-clock reminder setting | no (correct) |
| `PatientInformation.*.PatientDateOfBirth` | 581 | 7-character placeholder | no | removed at de-identification | no |
| `ProgrammerTimezone` | 583 | text | no | "Pacific Daylight Time" in all 583, including 227 winter exports: a fixed label | not a time |
| `ProgrammerTimezoneId` | 583 | text | no | "America/Los_Angeles" in all 583 | not a time |
| `ProgrammerUtcOffset` | 583 | "-07:00" 356, "-08:00" 227 | no | Follows daylight saving correctly; stored as the session's time-zone label; no code converts with it | not a time |
| Ticks and counters (`TicksInMs` 270,995 packet ticks, `TicksInMses`, `GlobalSequences`, every `...OffsetInSeconds`/`...BlockId`), durations (`AccumulatedTherapyOnTimeSince*`, `DurationInHours`, `AverageRecharge*`), every setting in ms or s | many | numbers | n/a | Durations or the device's counters; ticks only space samples inside one recording (allowed by 328) | not times |

### Missed or mistreated
- No tablet-clock field was missed.
- Every dated field with a counter is converted, including the two named like tablet times.
- Oddities, none reaching a page: the chronic date keys (unused as times), one annotation fitting neither clock (unused), `ImplantDate` unconverted (clocks 2 s apart that day).
- Stale comment, corrected with decision 330: the paragraph above `_pro_timestamps_utc` in `Biomarkers/bravo_service.py` said the device side "needs no such fix" because device times "match true CA wall-clock to <1 min in every DST era"; decision 328 measured the opposite.

### Accuracy of the converted times
- **The anchor.** Across 575 exports of the main clock block it moves a median of 1 s between consecutive exports (95th percentile 22 s, largest 288 s). Over all the data it moves 316 s (5th to 95th percentile 109 s). The counter keeps time to about 0.3 s a day; the 2.1-hour lead is all in the device's date setting, which moved 7,742 s.
- **Using the first-carrying export's anchor.**
  - Patient events: the anchor moved at most 2 s for 95% of the 1,257 events (40 more than 30 s, 2 more than 60 s, largest 287 s). An event reaches its first export a median of 6 minutes later.
  - Chronic readings: at most 30 s for 95% of 61,445 readings (60 more than 60 s, largest 288 s). A reading reaches its first export a median of 33 hours later.
- **What this means.** Converted times are within seconds of the tablet clock almost always and never more than about 5 minutes off. Taking the anchor part-way between the export before an entry and the one that carried it would remove even that; no window of 5 minutes or more needs it.

## Part 2. Matching band power to a pain report

### The report clocks
- **REDCap.** 778 reports, all parsed, 766 with non-zero seconds, so the time is REDCap's completion stamp, not typed. California wall-clock is converted with the Los Angeles rules. 0 of 778 fall in a repeated or skipped daylight-saving hour.
- **Clinic and at-home sheets.** 524 steps, 504 with a time, 495 with non-zero seconds. California wall-clock on the visit date, Los Angeles rules.

### Are they the same clock as the tablet?
1. **Remote presses against REDCap reports.** 980 of 1,199 patient events after implant are the "Streaming" event from her phone remote.
   - With today's times, 393 of 778 reports lie within 2 minutes of a press. On the device clock it was 20; moved to the same time on a neighbouring day, 10.5.
   - Among reports within 10 minutes of a press, the report comes a median of 0.3 min before it (middle half 1.6 before to 0.6 after).
   - Where the device ran more than 30 minutes ahead (333 reports): 247 within 2 minutes today, none on the device clock, which put 148 between 30 and 60 minutes away.
2. **Sheet current changes against streamed current changes.** For 365 sheet steps changing one side's current, the nearest streamed change to the same value is a median of 0.0 min away (middle half 0.4 before to 0.1 after); 258 within 1 minute. On the device clock, 143 of 296.
3. **Daylight saving.** No hour-sized error: 0 reports within 2 minutes of a press moved by an hour, in summer or winter (as they are, 207 of 540 summer and 186 of 238 winter reports lie within 2 minutes). Over ±12 hours the only concentration is at 0.

REDCap, sheet and converted device times agree to within about a minute; no correction between them is needed.

### What the correction changed (REDCap NRS, 778 reports)
"≤30 s" needs one PSD snapshot or any TD piece; "60 s" needs two snapshots. Three versions: yesterday (every re-stamped copy, median 17 copies an event, 9 to 22), device clock with one copy, today.

| Pair, window | Yesterday ≤30 s / 60 s | Device, one copy | Today | Yesterday → today: ≤30 s +/−; 60 s +/− |
|---|---|---|---|---|
| L 1-3+, 5 min | 114 / 106 | 61 / 48 | 128 / 53 | +24 −10; +4 −57 |
| L 1-3+, 60 min | 198 / 192 | 148 / 103 | 200 / 109 | +7 −5; +6 −89 |
| R 0-3+, 5 min | 302 / 288 | 67 / 50 | 331 / 171 | +47 −18; +26 −143 |
| R 0-3+, 60 min | 411 / 411 | 294 / 197 | 411 / 246 | +4 −4; +4 −169 |

- **TD barely moved:** L 1-3+ 45 → 43 at 5 minutes (4 gained, 6 lost), R 0-3+ 47 → 45; at 60 minutes 99 → 100 and 99 → 102.
- **The one-snapshot rows were roughly right by accident:** copies spread over up to 2 hours, so one usually fell near the report. With one copy on the device clock, R 0-3+ at 5 minutes would have had 67 instead of 331.
- **The 45 and 60 s rows rested on copies of one press,** which supplied the second snapshot.
  - Pages, daily defaults: 188 → 104 (L 1-3+) and 445 → 241 (R 0-3+).
  - Pages, Biomarkers page's settings: 156 → 101 and 333 → 318.
- **Sheet Left Leg ratings (207) against TD:** at 5 minutes, L 1-3+ 75 → 69 (+15 −21) and R 0-3+ 140 → 167 (+34 −8); at 60 minutes 199 → 195 and 199 → 199.
- **Rows up to 30 s on the pages** (a report there claims its own pieces):
  - Daily defaults: L 1-3+ 201 → 192, R 0-3+ 465 → 404. Two nearby reports used to claim two copies of one snapshot; now one wins.
  - Biomarkers page's settings: 174 → 176 and 356 → 480.

### Window width (today's times, REDCap NRS)
Each cell is matched / same report on a neighbouring day (1 to 3 days, averaged) / real (the difference).

| Window either side | L 1-3+ PSD | R 0-3+ PSD | L 1-3+ TD | R 0-3+ TD |
|---|---|---|---|---|
| 2 min | 27 / 3.3 / 24 | 177 / 6.8 / 170 | 30 / 9.3 / 21 | 30 / 9.7 / 20 |
| 5 min | 98 / 8.0 / 90 | 295 / 17.2 / 278 | 43 / 12.0 / 31 | 45 / 12.2 / 33 |
| 10 min | 127 / 12.8 / 114 | 330 / 30.5 / 300 | 51 / 14.8 / 36 | 56 / 15.2 / 41 |
| 15 min | 135 / 18.0 / 117 | 339 / 43.7 / 295 | 63 / 20.0 / 43 | 68 / 20.3 / 48 |
| 20 min | 142 / 21.7 / 120 | 349 / 54.7 / 294 | 73 / 23.7 / 49 | 76 / 23.8 / 52 |
| 30 min | 152 / 31.0 / 121 | 359 / 79.2 / 280 | 79 / 32.2 / 47 | 86 / 32.5 / 54 |
| 60 min | 172 / 56.5 / 116 | 377 / 142.3 / 235 | 100 / 52.7 / 47 | 102 / 53.8 / 48 |

Real matches stop growing at 10 to 15 minutes (PSD) and about 20 minutes (TD). The neighbouring-day matches grow in proportion to the window: at 60 minutes they are 38% (R 0-3+) and 33% (L 1-3+) of PSD matches and about half of TD matches.

### Recommended rule (adopted by the PI, 2026-09-26: 15 minutes)
1. **Keep decision 328's tablet times.** 393 of 778 reports lie within 2 minutes of her own press, against 20 on the device clock. REDCap, sheet and device clocks disagree by a median of 0.3 and 0.0 minutes.
2. **Match either side of the report.** Presses fall before and after it about equally (242 and 234 reports within 5 minutes).
3. **Use a 15-minute window either side for both TD and PSD.** It keeps 97–98% of real PSD matches (R 0-3+ 295 of about 300; L 1-3+ 117 of 121) and about 85–88% of real TD matches (43 of about 50; 48 of about 54). About 13% of PSD matches and 30–32% of TD matches at that width are the neighbouring-day kind.
   - 5 minutes loses 7% (R 0-3+) and 26% (L 1-3+) of real PSD matches, and nearly 40% of real TD.
   - 60 minutes adds almost nothing real and about triples the neighbouring-day matches.
   - The clock error left after conversion (seconds; at most about 5 minutes) is well inside 15 minutes.
4. **Count one press once.** Only 10 (L 1-3+) and 126 (R 0-3+) reports have two separate snapshots within 5 minutes, so the 45 and 60 s rows are thin on the PSD route.

### Limits
- Moving reports by whole days keeps her daily habits, so "real" is an estimate.
- These counts use the saved TD pieces and PSD snapshots of the two allowed pairs. The pages also limit samples per report and let a report claim pieces, so their counts differ by a few.
- The chronic log was not matched here. The device clock led by a median of 19 minutes at report time (548 of 778 reports more than 5 minutes, 167 more than 60), so any chronic-log matching before decision 328 paired most reports with the wrong 10-minute reading.
