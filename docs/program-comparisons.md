# Stimulation-program boxplots

The **Stim Program Boxplots** tab compares recorded survey scores associated with
source-supported stimulation settings. It recomputes the comparisons from saved
surveys, original device reports and the validated testing calendar. It does not
fetch providers, run an analysis job or edit source records when someone opens it.

## Eligible surveys and settings

Comparisons begin at the participant's configured implant boundary. Surveys on a
documented stimulation-testing date are excluded for the **entire Pacific day**,
whether testing took place in clinic or at home. Previously reviewed excluded
dates are preserved. Ordinary home surveys outside those dates can be eligible.
An unavailable or invalid testing calendar withholds comparisons until it is
verified; it never implies that there were no testing days.

Each survey is evaluated separately, preserving distinct records with identical
timestamps. A missing metric is unavailable for that metric, rather than zero.
Clinic-sheet ratings remain separate and do not enter the survey boxplots.

A survey can be associated with a same-Pacific-day programmer report's initial
settings before its session, or final settings after its session. Within a session,
both settings must agree. Ambiguous boundaries, conflicting source settings and
unknown stimulation or adaptive states remain unassigned. Settings are not carried
forward to another day merely because they are the last available observation.
The source reader uses BRAVO's canonical tablet-clock conversion. Filenames and
the implanted device's uncorrected clock do not determine survey timing.

These associations provide settings context. They do not establish uninterrupted
delivery, physical location, adherence or an exact activation time. A configured
adaptive amplitude range is distinct from measured current. Paused adaptive
settings retain their recorded status.

## Rankings and counts

For each available metric, the tab shows up to three open-loop and three
closed-loop programs with at least **five nonmissing assigned surveys** each.
Programs are ordered by their observed median: lower for pain scores and higher
for pain relief. Ties use a stable program identity. A metric with fewer qualifying
programs displays fewer boxes; it does not borrow observations from another metric.

Stimulation OFF is a separate reference. Reviewed reference programs, when supplied,
are labeled separately from ranked programs and retain their source-date limits.
Program cards and survey-point tooltips show their recorded settings and counts.
Boxes show the middle 50% of scores, with the median marked. These descriptive
comparisons do not establish a treatment effect or prescribe device settings.

Coverage counts distinguish missing scores, testing-date exclusions, assigned
open-loop/closed-loop/OFF observations and surveys without a verified assignment.
The latest stored survey and settings observation are reported separately. A newer
survey does not imply that equally recent verified settings are available.

## Automatic updates

Completed imports change the comparison revision when surveys, source reports,
canonical clock information, clinical configuration or the validated testing
calendar change. The visible page checks saved-data revisions every minute,
checks again on return to the page, and reloads after a manual sync finishes.
**Refresh view** also rereads saved inputs. Existing selected metrics remain selected.

These refreshes establish the state of completed imports, not upstream completeness.
An import failure can leave one stream older than another; read sync status and the
coverage dates together. Only an authorized administrator can request an upstream
sync. The shared viewer reads saved comparisons.

## Verification

Synthetic tests cover Pacific-day and daylight-saving boundaries, missing and
conflicting source state, duplicate-time surveys, metric missingness, five-survey
eligibility, ranking direction, stable ties, automatic invalidation and access
isolation. Release checks additionally compare real source records with the
displayed counts, settings and medians, preserve the canonical timeline values,
and exercise populated charts and controls through authenticated browser journeys.
Passing source tests or publishing code does not by itself establish deployment
acceptance; see the current release status.
