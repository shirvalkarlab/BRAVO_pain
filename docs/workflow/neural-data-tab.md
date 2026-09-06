# Aditya - All Data Streams / Neural Data

Requested: rename report/sidebar to Aditya - All Data Streams; tabs REDCap, Stim Program Boxplots, Neural Data, Medications, Oura. Keep route/API/source identities unchanged. Neural Data uses the existing reviewed home-program records and unknown intervals from REDCap, not notebook-derived observations or raw clinic-testing snapshots. No backend/source/QC edits.

Six default charts: Contacts; Stimulation mode; Cycling; Frequency; Amplitude; Pulse width. Show all side/program records. Both targets visible with participant-scoped names. Numeric fields parse only complete unit-qualified source values; conflicting source text remains in details instead of being silently reduced to a scalar. Running adaptive programs use lower/upper bounds; paused programs use fixed/paused values. Cycling Off means No cycling; explicit ON/OFF seconds are independently converted to minutes, unknown durations remain unknown. Mode is side-specific and retains single/dual threshold status. No median toggle.

Controls: field add/remove selector, full/custom history, Past 28 days, Stimulation context. Same trial-phase shading/local labels and shared full-settings panel. Timeline steps describe last recorded settings between observations, not continuous delivery or exact activation time. Unknown intervals interrupt the guides. Clicking a plotted record opens complete source settings.

Inspiration: Percept/percept_analysis/notebooks/DBS-Meds-Pain-Essential-Timelines.ipynb calls plot_dbs_settings_timeline; src/percept_analysis/plots.py:2489 and following organizes mode/cycling and per-side amplitude/PW/frequency/contact rows. Its caveat at lines 2820-2823 distinguishes joined observations from telemetry. Source schema reviewed independently against BRAVO/modules/RedcapStimulation.py, RedcapHomePrograms.py and RedcapHomeAdjustments.py.

Acceptance: scoped parser/interval true-branch coverage >=95%; rendering and two-toggle integration tests; full frontend regressions; production build and exact served-bundle match; application health/Aditya identity; live authenticated Chrome tab ordering, source settings, context toggles, dates and desktop/narrow plot geometry.

## Validation on 2026-09-04

- Independent synthetic parser tests: 66 passed; Istanbul true branches 146/146, with statements/functions/lines all 100%. Log `/private/tmp/bravo-neural-parser-tests.log`; coverage `/private/tmp/bravo-neural-parser-coverage/coverage-final.json`.
- Full frontend regression run: 321 tests, 39 suites passed. Log `/private/tmp/bravo-neural-all-tests.log`. Covers six fields, two switches, source propagation, invalid/custom dates, prior records, dense context, selection, missing values and plot callbacks.
- Production build succeeded with existing repository lint warnings. Log `/private/tmp/bravo-neural-build.log`.
- Only web container replaced; sync, database, Redis and data volumes retained. `bravo-appliance check` passed, Django checks clean, exact `/index` BRAVO application verified.
- Live image: `sha256:cd6d4ce59b0b930970203f220a6f750c6dd1038be2380a0a7053c718e64af7b7`.
- Served asset `/static/js/main.02755ad9.js` exactly matches local build (6,580,452 bytes); SHA256 `bf0f394ebcdf22c49e93c11e30379febfcbd473b9951c2cb63d3281c9a7f14e6`.
- Final authenticated Chrome verification completed with the user-authorized viewer account. Sidebar, breadcrumb and report heading all display Aditya - All Data Streams. Tab order: REDCap, Stim Program Boxplots, Neural Data, Medications, Oura.
- All six live charts render from 83 home records. Contacts/mode: 166 observed markers; cycling: 83; frequency/PW: 165; amplitude: 175 including adaptive bound markers. One unresolved numeric source record remains available for inspection, rather than guessed.
- Actual SVG labels show L GPe / R MD Thal, single and dual threshold modes, independent cycling on/off durations in minutes, fixed values and adaptive limits. Clicking an amplitude marker opens complete settings, including controller sensing contacts/frequency, lower/upper LFP thresholds and source evidence.
- Exactly two Neural Data switches, with no median control. Past 28 days selects 2026-08-08 through 2026-09-04, retains five in-window home records plus prior context, and shows only intersecting Stage 2 labels. Context off removes its panel and chart annotations; turning it on restores five annotations. Full history restores 83 records and one selected-record annotation per chart.
- DOM/SVG geometry: desktop viewport 1728 px, document width 1728 px, six plot widths 1358 px with matching SVG/scroll widths. At viewport 390 px, document width 390 px; each plot/SVG/scroll width is 342 px for both full history and 28 days. No horizontally clipped SVG text and no overlapping categorical y-axis labels. Normal viewport restored afterward.
- User explicitly authorized persisting automatic local account sign-in. Credentials saved only in owner-readable Git-ignored local storage, with a source-location pointer in workspace instructions and a password-free memory note. Viewer used for final checks; no admin-only operations required.


## September 4 responsive redesign

The completed design and acceptance record is [Modern responsive scientific visualizations](responsive-scientific-visualizations.md). It supersedes the earlier six-chart Neural layout and any earlier allowance for horizontal scientific-plot scrolling. Mode/cycling now share one device/group state chart; contacts use graphical lead configurations.
