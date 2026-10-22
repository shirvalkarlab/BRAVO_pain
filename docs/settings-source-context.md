# Reading settings and source context

The Aditya views separate recorded neural measurements, recorded sensing labels,
device configuration and evidence of stimulation delivery. Open an interval's
details to inspect its sensing information and any settings recovered from the
original recording source. A source configuration can be useful even when the
record does not establish its exact activation time.

## What the labels establish

| Display information | Meaning and limits |
| --- | --- |
| Recorded neural power | Stored averages from the labeled sensing channel. The contacts and center frequency describe sensing; the center frequency alone does not establish the power-band width. |
| Recorded current | The stored current values at their own timestamps. A plotted current trace does not by itself establish which sensing channel controlled it. |
| Source configuration | Program settings recovered from the original report that contributed the neural observations. These may include stimulation contacts, frequency, pulse width, adaptive limits, thresholds and the configured sensing-to-stimulation relationship. Configured limits are not measured delivered current. |
| Settings observation | A dated record of device configuration. An initial, final or historical settings observation does not prove uninterrupted delivery between observations. A date without an exact time remains labeled as such. |
| Reviewed home-program context | A separately reviewed home-program record with its stated timing and evidence. A device snapshot alone does not establish home use or physical location. |
| Configured control threshold | A setting used by the configured controller. An averaged neural-power value cannot establish every threshold crossing or the adaptive state at each sample. |

Contact pairs identify electrodes rather than a continuous numeric range. Known
device codes are displayed in readable language while source values and units
remain preserved. Group settings are shared by the device or group; side-specific
settings remain attached to their recorded lead. A configured control relationship
can use sensing from a different lead, so the sensing source and stimulation side
must be read separately.

## Linked reports and chronology

Source linking follows the recordings that actually contributed the displayed
samples. It does not select an unrelated report merely because its date is nearby.
The source reader uses the application's canonical report clock for settings
history and events. The linked details identify the source and show the dates of
the relevant settings observations.

When the contributing source configurations agree, the view can show their
recorded settings alongside the sensing interval. The accompanying chronology
message states whether the source observations bracket that interval and whether
therapy, group or adaptive-status changes are recorded within it. Absence of a
recorded change is not proof of uninterrupted adaptive delivery. Conflicting
status entries also remain qualified rather than becoming a unique delivery state.

When source configurations differ or cannot all be verified, the view retains the
available dated records and explains the conflict or source-read limitation.
Conflicting configurations can be opened individually. Missing settings context
does not remove otherwise valid neural measurements, and a missing display field
is not proof that the underlying report lacks the setting. Raw reports, device
reports and relevant clinic records should be checked before interpreting a
remaining uncertainty.

Linked configured thresholds are shown as settings context. They are not promoted
to interval-wide active threshold lines solely from a snapshot. Existing reviewed
controller intervals retain their own display rules. Settings context does not
change scientific sample selection, power/current values, units or exclusions.

## Controls across the seven tabs

| Tab | How to inspect the data |
| --- | --- |
| Multimodal Summary | Use the shared date view to compare streams. Hover over neural observations for sensing labels, recorded values and qualified settings context. Click an observation or choose its recorded sensing interval to open the corresponding details. The action reads **Sensing details** when settings rows are absent and **Recorded settings and sensing details** when they are present. |
| REDCap | Add or remove clinical metrics and adjust the date range. Survey tooltips retain score, time and available home-program context. Use the stimulation-context selector and expandable recorded-settings panel to inspect the reviewed record. Gaps in home assignments remain explicit. |
| Stim Program Boxplots | Select clinical metrics to compare. Hover over survey points for scores and settings; inspect program cards and per-metric coverage counts. Whole Pacific stimulation-testing days are excluded for clinic and home testing. Updated saved surveys, reports and the validated calendar automatically rebuild eligible assignments. Read the [comparison rules](program-comparisons.md), including lower pain versus higher relief ranking. **All recorded settings** appears only when rows are supplied. Ranking and dated reference programs remain descriptive comparisons. |
| Stim Program Settings | Select which settings to display and adjust the dates. Click an observation or use the searchable record selector to open shared group settings and separate lead settings. Snapshot markers do not carry settings forward; reviewed home-program steps retain their timing qualifications and missing-evidence gaps. |
| Neural Data | Inspect recent recorded observations and separately reviewed historical periods. Hover for actual values and sensing provenance. Select a recorded sensing interval or click its neural trace to open linked source observations and their activation limits. Power and independently recorded current retain their own timestamps. |
| Medications | Inspect regimen timing, then compare the selected clinical metrics. Hover for recorded regimen details and open the documented-regimen and condition lists for dates and survey counts. Readable frequency and route labels preserve the recorded drug and dose. PRN availability does not confirm use, and an ongoing source note does not verify later use. |
| Oura | Add or remove available measures, adjust dates, and use **Default Oura metrics** to restore the supported populated defaults. Current stored sleep heart-rate and variability streams retain their own labels; active calories remain distinct from total calories. Hover for values, original Oura days or recorded sample times, and applicable context. Daily totals are not assigned a single stimulation program. |

Selectors and expandable details change the view; they do not edit device settings
or source records. Dense settings histories can limit chart annotations while the
searchable selector retains access to the records. Empty sections explain the
missing recorded rows rather than presenting an empty complete-settings action.

Refresh controls reload available saved data. They do not establish that an
upstream import has completed or that provider coverage is complete. Loading,
access, freshness and empty-data messages should be read separately from source
settings uncertainty.

## Validation and release checks

Validation should compare source records with the displayed settings, source
identity, chronology and units; preserve neural measurements and their existing
analysis exclusions; and exercise both agreement and conflict cases. Portable
tests use synthetic fixtures for source linking, readable labels and controls.
Authenticated browser checks must also exercise populated data, selectors,
tooltips and expanded details across all seven tabs, including narrow layouts and
meaningful empty or error states.

A passing component test or source publication alone does not establish that a
particular deployment has passed these checks. Release acceptance separately
verifies the delivered application version, authenticated data paths and the
actual user journeys. This guide describes the behavior and verification process;
it does not claim live acceptance of a specific release.

For implementation, see the [source-settings reader](../BRAVO/modules/AdityaNeuralSettings.py)
and the [presentation adapter](../BRAVO/modules/AdityaPresentation.py).
