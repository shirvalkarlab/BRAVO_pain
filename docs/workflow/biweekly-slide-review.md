# Biweekly slides: review, revise, verify, deliver

Required for every scheduled pair and manual revision. User instruction,
September 5, 2026: apply scientific and visual judgment, give yourself concrete
feedback, and correct mistakes before asking Aditya to review. This is an active
critique, not a frozen-coordinate template or a checklist whose completion alone
establishes quality. Apply alongside `biweekly-slides.md`.

## Adapt to the current evidence

Read the current data window, source freshness, exact analysis request/response,
BrainSense channel/frequency, stimulation observations and uncertainties. Decide
which settings are truly invariant and which need interval-specific labels.
Recalculate dates, cutoffs, counts, metrics, limits, thresholds and annotations;
old examples are not current facts. Preserve gaps and distinguish observation
boundaries from known programming times.

Choose margins, plot heights, line breaks, group annotations and legend placement
for the actual content density. Keep fonts large, the four-row timeline, complete
score scales, all daily dates, modality colors and required context. Non-score
display ranges must contain the current data and configured limits; previous
examples are not permanent bounds. Recompute helper transforms and native axes
whenever scale or geometry changes. Never change scientific methods, omit
required settings or drop observations merely to make the slide fit.

## Critique the actual output before delivery

Export the actual published Google Slides pair and inspect the standalone images
at normal presentation size, enlarging regions as needed. This is artifact
rendering, not screen capture. Read as a lab member without conversation history,
source code or hover tooltips. Explicitly review these distinct aspects:

1. **Scientific interpretation:** Are the measured quantity, hemisphere/channel,
   pain metric, time scope, units, scales, smoothing and stimulation context clear?
   Are measured amplitudes distinguished from configured limits? Are thresholds
   and control-channel attribution correct in every relevant interval? Preserve
   unknown transition times. Distinguish Spearman from Pearson, signed AUC/chance,
   actual sensing frequency from scan-band center, and exploratory results from
   validation or programming decisions.
2. **Evidence and arithmetic:** Match displayed dates, numerical results,
   histogram counts/cutoffs, settings and sensing annotations to this run's
   sources. Distinguish matched neural samples from independent pain reports and
   channel-specific fit counts. Label inactive options correctly. Show missing,
   stale or partial sources accurately. Verify native chart values and every
   changed coordinate mapping against the source.
3. **Visual interpretation:** Check titles, tick numbers, dates, units, legends,
   reminders and settings for overlap, clipping and tiny text. Check neighboring
   panels together: a title must clear both its plot border and adjacent text.
   Inspect all 28 date labels, dense transitions, long group labels and nearly
   coincident thresholds. No necessary information may be obscured by masks or
   placed off-slide. Maintain meaningful contrast and axis/series color matching.
   Successful rendering alone does not establish readability.
4. **Lab-member explanation:** Privately write one or two plain-language sentences
   for each analytical section using only visibly supported information. If this
   requires missing context, ambiguous abbreviations or unsupported inference,
   revise the slide. Do not infer causality or clinical utility from correlation.

## Close the feedback loop

Write specific findings: what could be misread, the evidence and the correction.
Fix each material scientific or layout issue within scope, export again, and
reinspect the affected region and its neighbors. Recheck mappings after geometry
changes. Repeat until there are no unresolved material issues; a fixed number of
passes or an automated checker cannot substitute for judgment. Use the native
checker as a supplement. Reassess historical warning exceptions on the current
rendering instead of treating them as permanent waivers.

Only then send the exact reviewed final PNGs to Aditya and record their hashes
and Google slide revision. Never send an older cached export after a fix. If a
material problem cannot be resolved before the 07:00 Pacific cutoff, preserve
the last validated output, do not deliver a flawed pair as ready, and report the
specific incomplete stage. Do not extend the window or invent evidence.

## Continuous improvement record

For each pair save ignored `output/slides/YYYY-MM-DD/review.json`: source/request
identifiers, revision, export paths/hashes, scientific and visual findings,
corrections, reinspection outcomes, unresolved limitations, short lab-member
explanations and delivery eligibility. Close an issue only after inspecting its
correction in the final artifact.

Before each run, read this workflow and recent review records/user corrections.
Turn observed recurring errors into specific preventive checks here, retaining
Aditya's explicit preferences. Do not autonomously rewrite scientific policy or
expand publication scope. Historical coordinates are examples, not constraints.

Known September 5 regression: Spearman and Signed AUC headings overlapped plot
borders after adding the red reminder and compressing the panels. Check title
clearance against both plots and neighboring text after every header, font,
panel-height or settings-strip change. That day's 4pt fix is not a universal
solution for future layouts.
