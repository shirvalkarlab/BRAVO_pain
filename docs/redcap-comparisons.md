# REDCap stimulation and medication comparisons

The existing **REDCap – Pre-trial to Present** report has three views: Timeline,
Stimulation programs, and Medications. The views share the 11 default outcomes
and the 27-metric selector. Comparison views use analysis-eligible Stage 1 onward
surveys; they do not include the timeline's separately displayed testing-day X
points. They describe observed associations, not treatment efficacy.

## Stimulation programs

For each outcome, show up to three open-loop and three closed-loop programs with
at least five nonmissing eligible surveys, ordered by ascending median within
mode. Open-loop programs appear on the left; closed-loop programs on the right.
Fewer eligible programs produces fewer boxes, without relaxing the count rule.
Rankings are specific to the selected outcome. A lower mood or relief score is
not described as a better outcome.

Program identity follows the notebook's functional delivered-setting fields,
including contact/current distribution, amplitude, frequency, pulse width,
cycling, laterality and active adaptive parameters. Arbitrary group letters do
not create different programs. Sensing-only operation stays open-loop. Unknown
settings cannot become an OFF reference. OFF observations remain a separate
reference, outside the top-three selection.

The stimulation source supplies reviewed same-day Initial/Final assignments.
BRAVO requires the same survey identity, corrected timestamp, eligibility and
27 outcome values before accepting an assignment. Plot values then come from
BRAVO's existing canonical survey records. Unmatched surveys remain unassigned,
and coverage counts make the limitation explicit. A source snapshot is not
silently treated as covering newer surveys.

## Medications

The medication timeline displays documented regimens by clinical drug class,
including supportive medications, before the outcome comparisons. Boxes show
all documented analysis-priority medication conditions represented in eligible
surveys, organized by class, medication and regimen; there is no top-three cut.
Unchanged background regimens remain identifiable as having no within-study
contrast. Concurrent medications mean a survey can contribute to multiple
condition boxes, once per applicable condition.

Matching uses the notebook's calendar-date intervals: start inclusive, end
exclusive. A missing start needs an explicit pre-trial flag; a missing end needs
an explicit ongoing flag to establish exposure. Unknown intervals stay unknown.
PRN labels mean **available**, not taken. Scheduled-time labels are descriptive
metadata and do not establish ingestion or time since dose.

## Private source provisioning and refresh

Set `RCS08_COMPARISON_SOURCE` in the ignored `.env.appliance` to a local reviewed
Percept canonical data folder containing:

```text
stim/rcs08_stage1_to_stage3_pain_stim_matches.csv
medications/rcs08_medications.csv
```

The default is `./secrets/rcs08_comparisons`. That folder can contain portable
copies on a different laptop. The current machine uses its existing Percept
canonical data directory directly, mounted read-only. No Percept checkout or
notebook runtime is needed inside the application image.

After changing the path, recreate the sync service using the normal deployment
workflow. The sync container receives `/run/secrets/rcs08_comparisons` via
`RCS08_COMPARISON_SOURCE_DIR`. The web service does not mount these sources.
Ordinary data sync reads their current bytes, records source hashes, reconciles
assignments against that same canonical QC pass, and publishes compressed
comparison metadata with the daily survey form. The existing report cache and
nightly prewarming use the updated publication. No new scheduler exists.

A missing, invalid, or unreconciled comparison source must produce an explicit
unavailable/partial section while the existing reviewed timeline stays usable.
BRAVO does not refresh the Percept notebooks or write their source CSVs. Refresh
those canonical exports through their owning workflow when new assignments or
medication documentation become available, then run ordinary BRAVO sync.

The appliance backup includes the published database metadata and any source
copies under `secrets`. An external directory selected by
`RCS08_COMPARISON_SOURCE` is not automatically included: provision those two
reviewed CSVs separately on a replacement laptop, preserve their hashes, and
update its local path. Do not place participant source files in Git.

## Rendering

Interactive plots initialize as they approach the visible page, reserving their
height in advance. This avoids drawing every medication point at once when the
view opens. Initialized charts retain their zoom while scrolling; switching
views releases them. No observations are sampled away for rendering.

## Validation

Run the project's backend/frontend/true-branch/build gate, then private-source
reconciliation and the actual Chrome journeys. Confirm same-survey values,
mode/ranking/count rules, medication interval boundaries, incomplete-source
behavior and permissions. Verify `scripts/bravo-appliance check` and the live
Aditya image after deployment. Local acceptance evidence belongs in
`reports/redcap-comparisons/`; it does not establish shared-release CI or causal
scientific validation.
## Fixed reference programs and settings labels

The stimulation comparison retains its metric-specific top three OL and top
three CL programs (at least five eligible surveys), and adds a separate fourth
position on each side. A reference can repeat a ranked program. Reference
positions remain visible below five surveys; zero observations produce an empty
labelled slot, never a fabricated box or median. All values still come from the
same canonical reviewed Daily PRO observations.

The finalized OL reference is reviewed against the latest stimulation-testing
sheet's home-program tab. Its private definition is
`secrets/rcs08_processing/finalized_open_loop.json`, on the existing read-only
processing-rules mount. The version-1 rule contains `source` (title, URL, exact
range, verification timestamp), `program` (the reviewed source fields accepted
by `RedcapComparisonSources.functional`) and `condition_id` (that exact
functional identity). Retain the supporting source hash and any supplemental
settings provenance in `source`. Group A alone is never a matching criterion.
Do not commit participant settings, source exports, or the private rule. Copy
this rule with the existing private processing directory for another appliance,
then publish it through the ordinary reviewed data sync. A missing/invalid rule
does not change ranked programs or survey QC.

Current CL is derived at report time from the latest reviewed home-program
timeline, including reviewed at-home adjustments. Unknown current intervals,
conflicting simultaneous settings, or a current OL program cannot be presented
as known current CL. Canonical comparison assignments join to normalized native
snapshots by exact source basename and the resolved Initial/Final boundary.
Every matching snapshot must have the complete current home-settings signature;
duplicate/conflicting source snapshots cannot win by file order. Group/target
display labels, transient ON/OFF state, and sampled contact currents are excluded
from this signature; programmed contacts/fractions, amplitudes/limits, sensing,
thresholds and timing remain. Multiple matching functional identities are not
pooled. A current program without a unique matched cohort stays an empty current
reference; older programs are not backfilled into it.

Axis labels show cycling and per-side contacts, frequency, amplitude/range and
pulse width with units. OL labels omit sensing. Native current-home labels use
the timeline's original units and tablet targets. Detailed settings remain in
the point/box hover information. Wide comparisons scroll horizontally to keep
the labels legible, and charts retain lazy initialization.
