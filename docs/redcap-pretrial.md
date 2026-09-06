# REDCap – Pre-trial to Present

Customized Analysis → REDCap – Pre-trial to Present, on the Aditya build.
The default plots are Mood VAS, Overall NRS, Overall VAS, Left-leg VAS, Back VAS,
MPQ sensory (0–33), MPQ affective (0–12), Standard MPQ total (0–45), Fiery,
Tingly and Electrocuting, in that order. The searchable metric selector
exposes 27 clinical outcomes; survey duration and additional historical
questionnaires are outside this page's scope.

The remaining 16 choices are relief VAS and the 15 standard SF-MPQ descriptors.
Individual descriptors and fiery/tingly/electrocuting each use a 0–3 scale.
Expanded MPQ (0–54) is not substituted for the standard score.

## Source and plotting contract

The content follows Percept's `DBS-Meds-Pain-Essential-Timelines.ipynb` and its
`build_full_trend_score_data` helper. Interactive rendering uses BRAVO's existing
MUI and Plotly dependencies. No notebook runtime is needed by the application.

- Read only shared reviewed BRAVO ScaleRecords; no fresh REDCap fetch in a page request.
- Existing daily QC, corrected start times, unreliable/duplicate/incomplete survey
  exclusions and stimulation-testing-day exclusions remain applied.
- Historical forms require completion status 2 and retain their own timestamps.
- Join only the explicit like-for-like measures from fluctuation, Stage 0 mini,
  short and long forms, and daily surveys. Combined leg/back ratings stay separate
  and are not included in leg-only or back-only outcomes.
- Missing blocks remain missing. Preserve the existing notebook's Stage 0 partial
  MPQ block scoring; do not fabricate responses outside administered instruments.
- Share study-stage metadata with the import's reviewed study-stage CSV.
- Plot colors indicate phase, with dashed phase boundaries. The x-axis retains
  calendar time from the first reviewed observation through today. Drag to zoom.
  Tooltips show Pacific timestamps, scores and concise home settings with units.
- The optional centered five-survey median combines routine and QC-valid visit
  observations continuously, across phases and date gaps. It is calculated before
  date filtering, so zooming does not change values. Edge windows use the available
  observations. The line is a display smoother, not additional measured data.
- Fixed outcome scales retain comparability. No interpolated points, regression,
  treatment-effect tests or medication overlays are introduced.

## Recent view and stimulation context

The **Past 28 days** switch sets every metric to 28 Pacific calendar dates,
including today. Turn it off or choose **Pre-trial to today** to restore history.
Every date appears on the x-axis in compact M/D format (for example, 8/25).
Manual date selection remains available and the 11 default metrics are unchanged.

The **Stimulation context** switch controls both visit-day X markers and red
dashed stimulation lines. Visit-day points are published alongside the daily
form from the same canonical QC pass and reviewed hash. Only the deliberate
`intentional stimulation-testing day` exclusion is relaxed for this context:
incomplete, unreliable, duplicate or other excluded surveys remain excluded.
The publication is losslessly compressed to keep ordinary survey form queries
small. These points contribute to the display median even when their X markers
are hidden, but never become routine ScaleRecords or change other analyses.
Corrected survey start times and missing-value policies apply.

The overlay selects observed **take-home programs**: the last unambiguous Final
snapshot on a reviewed visit day, or the first changed observation between visits.
It excludes intermediate clinic tests and does not turn raw device log entries
into exact activation times. Unchanged configurations do not add lines. The full
reviewed visit calendar includes visits with no survey that day. Missing final
snapshots or conflicting observations create explicitly unknown intervals until
the next unambiguous observation; tooltips do not carry earlier settings through
those intervals. This selection rule establishes observed programs, not physical
departure times or undocumented activation times.

Compact numbered labels identify home-program changes. Hovering a survey or
change shows stimulation, sensing and adaptive settings, grouped by shared,
left and right scope. A survey uses only the home context available as of its
timestamp. Visit-day tooltips explicitly distinguish home context from clinic
testing. The matching selector opens a complete settings card, initially folded.
More than 12 changes in a date window shows only the selected line for readability;
all remain selectable. The searchable selector renders at most 100 matches.

The settings card separates shared group parameters (cycling, high-pass filter,
sensing blanking) from each side's stimulation, sensing and adaptive control.
Contact polarity, Hz, mA and microseconds are retained. Adaptive durations retain
their native millisecond values with readable seconds where useful. Biomarker
frequency, sensing contacts and lower/upper thresholds are shown; threshold units
are **LFP Power (LSB)**. Contralateral sensing is explicit. Adaptive running
amplitude is a programmed range; a paused amplitude is not current delivery.

Definitions follow local Medtronic `white-paper-percept.pdf` (p34 field scope,
p16 adaptive timings, p9 threshold units) and `clinician-programming-percept.pdf`
(p28 group settings, p35 adaptive paused amplitude, p38/p42 timing definitions).
The September 2026 **Home Programs (New)** sheet and the RCS08 stimulation-test
slides informed reporting and take-home verification. Approved imported device
sources supply observed settings. A separately reviewed clinical-note adjustment
may supplement a change not yet present in an export; proposed worksheet programs
are never imported automatically.

## Operations

`POST /api/queryRedcapTimeline` accepts only `ParticipantId`. Authentication and
participant access are checked before the shared report cache. Approved data
changes invalidate reports. This inexpensive report joins existing nightly
prewarming; it does not add a scheduler or heavy precomputation.

Normal REDCap sync maintains the enriched shared metric mappings. For an existing
installation, the one-time local upgrade can replay its encrypted saved survey
audit through the same import, under the sync lock and a database transaction;
all previously stored fields/timestamps must remain unchanged or the upgrade
rolls back. No upstream REDCap writes are performed. The web service needs neither
REDCap credentials nor access to the Percept checkout.

Portable tests cover metric provenance and mappings, missing data, permissions,
phase dates, filtering, smoothing, request races, errors and UI controls. See the
local acceptance record in `reports/redcap-timeline/ACCEPTANCE.md` for deployment
and real-data verification; that report is not a substitute for CI on a shared release.

### Reviewed between-visit adjustments

Optionally place `rcs08_home_program_adjustments.csv` in the private processing-rules
folder mounted at `/run/secrets/rcs08_processing` (or `RCS08_PROCESSING_RULES`).
Normal daily sync publishes its exact rows and SHA-256 alongside the reviewed
survey metadata. The API uses this stored publication; it needs neither the private
CSV mount nor live Google access. Keep this participant-specific file out of Git.

Columns: `date,time_local,group,side,field,previous_value,value,source_url,note`.
Dates are ISO dates; optional `time_local` is Pacific wall time. Use Group A–D,
side `left`/`right`, an HTTPS source link and a human-reviewed explanatory note.
Supported fields are Lower/Upper LFP threshold (values with `LFP Power (LSB)`),
Amplitude and Fixed / paused amplitude (values with `mA`). The prior value and
group must match the preceding observed home program; unmatched rows remain
unresolved. Shared contralateral sensing thresholds update both controlled sides.
A later conflicting export is identified explicitly, without rewriting raw data.

An unknown time stays date-only: the line is anchored to that calendar day and
its tooltip says the time was not recorded. Surveys on that day are explicitly
qualified because they may precede the change. Never fill in an invented time.
The detailed card retains the source link and explanatory evidence. The existing
nightly process handles publication and cache refresh; no second scheduler exists.

## Program and medication comparison views

See [REDCap comparisons](redcap-comparisons.md) for the Stage 1 onward boxplot
views, medication timeline, notebook-equivalent assignments and private-source
provisioning. The timeline behavior documented above remains separate.
