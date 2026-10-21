# Using BRAVO

[Open BRAVO on Jetstream](https://bravo-aditya.mde260021.projects.jetstream-cloud.org/)
and sign in with your individual account or the shared read-only lab account.
Credentials are supplied privately by the site administrator. The shared account
uses separate browser sessions, so one person signing out does not sign everyone
out. It permits viewing and **Refresh view**, but not edits, uploads, saved-band
changes or **Sync all streams**; see the [shared viewer guide](shared-viewer.md).
A local clone has neither the shared site's accounts nor
data. The old laptop/Tailscale address is not required.

## Find the modules

Open a participant you are authorized to view, select a report category, then
select **View**. The default category does not list every report.

| Category | Reports |
| --- | --- |
| Choosing stimulation settings | Aditya - All Data Streams; Biomarkers exploration; Stim optimizer; Closed-loop deployment; Analysis builder |
| Brain Data | Therapy History; Neural Activity Snapshot; Time-Series Analysis; Chronic Neural Activity; Multi-Modality Timeline Report; Chronic Events |
| Surveys and Questionnaires | Form Records; Pain Score Visualization |
| External Sensors | Oura Ring Dashboard and other configured sensor dashboards |

The shared viewer can open authorized read-only reports. Editing, administration
and analysis-building requests are blocked by the server; some overview cards may
still be visible. Use an individually authorized account for those actions.

## Aditya - All Data Streams

| Tab | Contents and requirements |
| --- | --- |
| Multimodal Summary | Survey, wearable and neural measures together, including recent recorded observations; coverage differs by stream |
| REDCap | Imported survey metrics and separately supplied clinic/study context |
| Stim Program Boxplots | Outcomes grouped by reviewed program assignments; settings alone do not establish home assignments |
| Stim Program Settings | Device settings observed at recorded times |
| Neural Data | Reviewed home periods plus separately labeled recent recorded observations |
| Medications | Comparisons requiring reviewed medication episodes and saved analysis results |
| Oura | Stored activity and sleep observations with original provider day labels |

Select dates and measures that contain observations. On small screens, scroll the
tab row horizontally. Missing values are unavailable, not zero. Settings observed
at a visit do not establish when a program became active at home.

Standard short-form MPQ total is **0–45**, sensory **0–33**, affective **0–12**.
It requires the verified item/aggregate mapping shown by the application; the
standard score is distinct from legacy expanded measures. The display does not
rescale a legacy total to manufacture a standard score. Read the displayed
provenance and limitations before comparing measures.

Neural snapshot spectra, time-domain recordings and chronic device summaries are
different products. Their units and coverage are not interchangeable. Recent
recorded observations can extend beyond reviewed historical home periods and also
appear in Multimodal Summary under its shared date filter. Their bounds come from
actual samples; power and current keep separate timestamps and gaps. A reviewed
home-continuity policy may label periods as assumed home between documented
stimulation sessions. The display names that assumption and its confirmation
boundary; it does not verify physical location or continuous device activation.
Known testing dates and overlapping averaging bins remain excluded. New stored
clinic dates update those exclusions, while other session evidence requires an
operator review. Future scheduled visits alone do not prove a session occurred.
These observations do not silently expand the historical analysis eligibility.

Sensing-contact or frequency changes between exports may leave the exact change
time unknown without making the recorded hemisphere unknown. Inherited sensing
settings stay qualified. A missing implant date is shown as unavailable rather
than a date manufactured from an empty value.

A separately reviewed PSD contact assignment can use the sensing-change timeline
only when it is bound to the exact event, spectrum and retained source claims.
Such results are labeled **Assigned from sensing-change timeline; conflicting
export labels retained**. This is not agreement between the source exports.
Changing the spectrum or source claims invalidates the assignment until reviewed
again. Unresolved assignments remain explicit, and the original spectra remain
available.

## Refresh versus sync

**Refresh view** rereads saved results. It does not fetch providers or import new
source files. Visible Aditya tabs check saved-data revisions every minute and
refresh after a manual sync finishes, including partial failures. Returning to
the window checks freshness without discarding a successful in-flight read.
Selected measures and date filters remain selected; widen dates if necessary.

**Sync all streams** is an administrator action and is unavailable to the shared
viewer. It requests fresh neural files,
clinic workbooks, REDCap surveys and Oura observations and shows each stream's
status. A duplicate click while a job is active returns that job. Closing the
status panel does not cancel the work. Files copied with import pending is not
completion. A partial failure can leave some streams updated and others older.
Daily jobs also refresh data; use the saved job status and observation dates as
evidence of freshness, rather than the application's deployment date.

## Prasad's modules and standard reports

Biomarkers exploration examines neural/outcome relationships. Stim optimizer
explores candidates from available evidence. Closed-loop deployment displays
candidate evidence and eligibility checks. Missing inputs, insufficient matches,
pending computation or a device-feasibility refusal can be legitimate outcomes.
Analysis computation is separate from source import and can take time. Avoid
launching competing repeated computations.

Band choice uses time-domain evidence; a device PSD-only grid cannot independently
select a band. Read each grid's own settings and status. **Last scan** refers to a
separate all-band scan and can be uncomputed while an individual grid is populated.
A displayed candidate is not an instruction to program a device.

Standard reports require their corresponding recording types. A JSON export need
not contain every recording type. Censored bins and ambiguous contact assignments
may limit particular analyses while raw spectra remain retained. Optional models
and participant-specific clinical configuration are separately provisioned.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Custom modules are missing | Return to the participant overview and select Choosing stimulation settings → View |
| Empty chart | Check participant access, selected dates/metric and recording type; read the availability message |
| REDCap/Oura looks old | Check successful import status and observation dates; a page refresh cannot fetch missing provider records |
| Network error | Allow the bounded automatic retry; use Refresh view or reload if it persists, and check connectivity/sign-in |
| Calculation pending/failed | Preserve its sanitized status for the operator; avoid competing repeated runs |
| Sign-in fails | Confirm the current site URL; an expired session may require signing in again |

For support, share page/tab, dates, build revision and sanitized error privately
with the operator. Do not put participant identifiers, credentials or clinical
exports in public issues. [Release status](release-status.md) states the actual
validation boundary; this guide is not a guarantee of complete data coverage.
