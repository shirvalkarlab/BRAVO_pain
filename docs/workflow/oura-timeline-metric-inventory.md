# First-party Oura timeline: metric inventory

Status: **six default charts implemented, locally deployed, and verified in the authenticated Chrome session**.
The first-party REDCap Oura tab uses `/api/queryOuraTimeline` and does not import
or modify the Oura–FreeReps adapter. This inventory covers the local normalized
BRAVO ingest schema; unavailable metrics remain visible with empty observations.

Approved defaults, in order: **Steps; Heart rate; Heart-rate variability; Total
calories; Sleep duration (longest episode); Total sleep duration, including naps.**

Heart rate uses all recorded times, states, and heart-rate channels across
stored streams. At duplicate timestamps, eligible finite observations beat
missing cells and standard HeartRate observations take priority over other HR
streams; otherwise the last-loaded equal-priority observation wins.
HRV searches every stored stream for HRV channels; the current normalized ingest
records HRV in Sleep, so all recorded HRV samples are shown without inventing
unrecorded daytime measurements. These defaults preserve exact sample timestamps,
source stream labels, and null readings. Lines break for gaps longer than 900
seconds. This display gap threshold is not a new data exclusion or wear policy.

The source ingest does **not retain Oura sleep-type classification**. The
first duration chart selects the longest time-in-bed session per eligible Oura day,
plotting its total asleep duration (awake time excluded). Twelve selected episodes
occurred during daytime, so the UI provisionally uses “Sleep duration (longest
episode)” rather than asserting a literal nighttime measurement. The user was
offered the option to specify a nighttime window; none has been imposed. The total
sleep chart sums distinct nonoverlapping sessions, including naps, per Oura day;
it omits days with unknown session duration, invalid bounds, or overlapping
sessions rather than silently using zeros or double-counting. Calories remain
Oura estimates. No new wear-time filter has been applied.

## Existing QC and a possible wear-time criterion

The current reviewed RCS08 policy excludes Oura days April 30 through May 27,
2026, inclusive. Sample timestamps are excluded independently from April 29,
2026 at 20:53:55.700 PDT through (but not including) May 27 at 13:55:36 PDT.
Source missing masks and nonfinite values are also honored. There is **no 70%
wear-time rule** in this policy. Sources: `config/rcs08_oura_exclusion_windows.csv`
and `modules/OURA/QualityControl.py`.

`DailyActivity.NonWearTime` stores the Oura `non_wear_time` source field in
seconds. A proposed nominal daily wear fraction could use
`(86400 - NonWearTime) / 86400`, but this has not been validated or enabled.
An approved policy must resolve missing daily rows, invalid nonwear values,
partial ingestion, independent sample coverage, and daylight-saving day lengths.
Do not describe the existing Oura QC as equivalent to manuscript Fitbit wear
eligibility without that validation.

## Catalog

There are 44 selectable metrics, including the six approved defaults. Raw
`average_met_minutes` is omitted because its unit has not been verified.

| Key | Display label | Unit | Stored stream / field | Conversion |
| --- | --- | --- | --- | --- |
| `heart_rate` | Heart rate | bpm | `@sample` / `Heart Rate` | Exact samples, all available times |
| `hrv` | Heart-rate variability | ms | `@sample` / `Heart Rate Variability` | Exact samples, all available times |
| `sleep_total` | Total sleep duration, including naps | h | `SleepTotal` / `TotalSleepDuration` | Sum distinct nonoverlapping sessions, divide by 3600 |
| `sleep_duration` | Sleep duration (longest episode) | h | `Sleep` / `TotalSleepDuration` | Divide by 3600 |
| `sleep_efficiency` | Main sleep efficiency | % | `Sleep` / `Efficiency` | Unchanged |
| `sleep_hr` | Main sleep heart rate (eligible samples) | bpm | `Sleep` / `@Heart Rate` | Eligible-sample mean |
| `sleep_hrv` | Main sleep HRV (eligible samples) | ms | `Sleep` / `@Heart Rate Variability` | Eligible-sample mean |
| `steps` | Steps | steps | `DailyActivity` / `Steps` | Unchanged |
| `sleep_score` | Sleep score | score | `DailySleep` / `Metadata.Score` | Unchanged |
| `readiness` | Readiness score | score | `DailyReadiness` / `Metadata.Score` | Unchanged |
| `activity` | Activity score | score | `DailyActivity` / `Metadata.Score` | Unchanged |
| `sleep_breath` | Main sleep respiratory rate | breaths/min | `Sleep` / `AverageBreath` | Unchanged |
| `sleep_awake` | Main sleep awake time | min | `Sleep` / `AwakeTime` | Divide by 60 |
| `sleep_in_bed` | Main sleep time in bed | h | `Sleep` / `TimeInBed` | Divide by 3600 |
| `sleep_deep` | Main sleep deep sleep | h | `Sleep` / `DeepSleepDuration` | Divide by 3600 |
| `sleep_light` | Main sleep light sleep | h | `Sleep` / `LightSleepDuration` | Divide by 3600 |
| `sleep_rem` | Main sleep REM sleep | h | `Sleep` / `RemSleepDuration` | Divide by 3600 |
| `sleep_latency` | Main sleep latency | min | `Sleep` / `Latency` | Divide by 60 |
| `sleep_restless` | Main sleep restless periods | count | `Sleep` / `RestlessPeriods` | Unchanged |
| `sleep_hr_summary` | Main sleep heart rate (Oura summary) | bpm | `Sleep` / `AverageHeartRate` | Unchanged |
| `sleep_hrv_summary` | Main sleep HRV (Oura summary) | ms | `Sleep` / `AverageHRV` | Unchanged |
| `active_calories` | Active calories | kcal | `DailyActivity` / `ActiveCalories` | Unchanged |
| `total_calories` | Total calories | kcal | `DailyActivity` / `TotalCalories` | Unchanged |
| `activity_high` | High activity time | min | `DailyActivity` / `HighActivityTime` | Divide by 60 |
| `activity_medium` | Medium activity time | min | `DailyActivity` / `MediumActivityTime` | Divide by 60 |
| `activity_low` | Low activity time | min | `DailyActivity` / `LowActivityTime` | Divide by 60 |
| `sedentary` | Sedentary time | h | `DailyActivity` / `SedentaryActivityTime` | Divide by 3600 |
| `resting_time` | Resting time | h | `DailyActivity` / `RestingTime` | Divide by 3600 |
| `nonwear` | Non-wear time | h | `DailyActivity` / `NonWearTime` | Divide by 3600 |
| `inactivity_alerts` | Inactivity alerts | count | `DailyActivity` / `InactivityAlert` | Unchanged |
| `walking_distance` | Equivalent walking distance | m | `DailyActivity` / `EquivalentWalkingDistance` | Unchanged |
| `meters_to_target` | Distance to activity target | m | `DailyActivity` / `MetersToTarget` | Unchanged |
| `target_distance` | Activity target distance | m | `DailyActivity` / `TargetMets` | Unchanged |
| `high_met` | High activity MET minutes | MET·min | `DailyActivity` / `HighActivityMETMinutes` | Unchanged |
| `medium_met` | Medium activity MET minutes | MET·min | `DailyActivity` / `MediumActivityMETMinutes` | Unchanged |
| `low_met` | Low activity MET minutes | MET·min | `DailyActivity` / `LowActivityMETMinutes` | Unchanged |
| `sedentary_met` | Sedentary MET minutes | MET·min | `DailyActivity` / `SedentaryActivityMETMinutes` | Unchanged |
| `temperature` | Temperature deviation | °C | `DailyReadiness` / `TemperatureDeviation` | Unchanged |
| `temperature_trend` | Temperature trend deviation | °C | `DailyReadiness` / `TemperatureTrendDeviation` | Unchanged |
| `spo2` | Blood oxygen saturation | % | `DailySpo2` / `Spo2` | Unchanged |
| `breathing_disturbance` | Breathing disturbance index | index | `DailySpo2` / `BreathingDisturbance` | Unchanged |
| `stress` | High stress time | min | `DailyStress` / `StressHigh` | Divide by 60 |
| `recovery` | High recovery time | min | `DailyStress` / `RecoveryHigh` | Divide by 60 |
| `vascular_age` | Cardiovascular age | years | `DailyCardiovascularAge` / `VascularAge` | Unchanged |

`TargetMets` is a misleading internal name: DataManager explicitly populates it
from Oura `target_meters`, so the displayed target distance is in meters. The
unit of `average_met_minutes` has not been independently verified; this metric is **excluded from the selectable catalog** until its source unit
is verified. The approved catalog contains 44 metrics.

Non-line-chart source detail includes stress day summaries, score contributors,
sleep bedtime timestamps, sleep stage/movement samples, activity classes/MET
samples, and heart-rate state samples. These are not silently encoded as daily
numeric outcomes. VO2max, resilience, rest mode and enhanced tags are not
implemented as normalized stored streams by the current ingest.

## Validation and deployment boundary

Validation: **29 synthetic tests passed**, including the existing FreeReps and
Oura QC suites. New adapter and API scope: **72/72 branches and 171/171
statements covered (100%)**. Coverage is scoped to these two new modules, not a
claim about the full backend.

Synthetic tests cover catalog completeness, real scores, units, missing and zero
values, source immutability, Oura dates, duplicate records, main-sleep selection,
QC masks, sample timestamp duplicates, authentication, participant permissions,
read-only viewers, cache permission rechecks, and private error handling.

Approved backend integration files:
- `BRAVO/modules/OURA/Timeline.py` (new)
- `BRAVO/Server/APIs/OuraTimeline.py` (new)
- Add `OuraTimeline` import and endpoint to `BRAVO/Server/APIs/urls.py`.
- Add `/api/queryOuraTimeline` to the read-only POST allowlist in
  `BRAVO/Server/Middlewares/ReadOnlyAccount.py`.

Apply these minimal insertions to the verified live backend; do not copy unrelated
dirty backend changes. No modifications to FreeReps, raw records, source QC,
analysis identifiers, or existing analysis calculations are part of this integration.


Candidate image patch helper: `scripts/deployment/patch_oura_timeline.py`.
Use a context containing this helper plus the reviewed new `Timeline.py` and
`OuraTimeline.py`. Build FROM the verified current Aditya image; after the UI
assets are copied, copy the payload into a temporary image directory and run:

```dockerfile
COPY oura-timeline /tmp/oura-timeline
RUN BRAVO_CANDIDATE_IMAGE_BUILD=1 python3 /tmp/oura-timeline/patch_oura_timeline.py /usr/src/BRAVO /tmp/oura-timeline
```

The helper checks expected live URL/allowlist anchors, validates syntax before
writes, prints preserved dependency hashes, and adds only the two endpoint
registrations plus the new modules. It does not replace DataManager,
QualityControl, ReportCache, settings, or unrelated backend files. A source/base
mismatch fails the build for review. Existing dependency hashes and actual
participant output must still be checked against the chosen live base image;
synthetic tests alone do not establish patient-data parity.

Final release and browser evidence: [six-chart release validation](six-chart-release-validation.md).
