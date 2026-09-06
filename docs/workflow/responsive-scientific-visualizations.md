# Modern responsive scientific visualizations

User acceptance standard, 2026-09-04: all BRAVO plots and diagrams should be scientifically accurate, visually clean, and understandable to any lab member without code knowledge or a separate explanation. Match modern BRAVO timeline styling and fit available width; make dense data readable through adaptive labels, tick density, spacing and stacking. Do not claim success by hiding overflow or dropping observations.

The standard is recorded in workspace AGENTS.md and the shared rigorous-project-workflow skill. A password-free memory note records the cross-project preference. The shared skill was validated with quick_validate.py in the existing BRAVO Python environment.

## Neural Data redesign

Five charts: graphical paired contact configurations; combined device/group stimulation mode and cycling; left/right frequency; left/right amplitude; left/right pulse width. Lead schematics are flattened SenSight representations with distal ring 0/right8, segmented levels 1/2 or right9/10, proximal ring3/right11, separate case electrode and explicit positive/negative/unselected legend. No rotational anatomy or measured current is invented. Unverified geometry/contact strings get explicit placeholders.

Contacts form one configuration-state trace, with diagrams beside rows on wide screens and a complete local graphical key on narrow screens. Mode/cycling is one shared group trace ordered fixed/no cycling, numerical ON then OFF minutes, adaptive single/dual, then unresolved/conflicting source states. Only frequency/amplitude/PW have separate lead traces. Connected post steps preserve missing-evidence gaps, missing parameter values and disappearing-program breaks.

Source: current local Percept clinician-programming-percept.pdf, A610 pp26–27,35,39. The saved DBS-Meds-Pain-Essential-Timelines notebook and its recorded outputs were opened in Chrome through a read-only local HTML rendering, with no notebook execution. Notebook plot_dbs_settings_timeline uses connected post steps; it excludes testing-day survey rows. BRAVO instead uses reviewed home-program snapshots: interim clinic test sweeps are excluded, but final reviewed post-visit home programs are retained. UI makes this distinction explicit.

## Responsive legacy plot scope

Source inventory identified real width floors in REDCap, Medications, Oura–FreeReps, Neural Activity Snapshot (chronic/PSD), Therapy History (history/impedance), Chronic Neural Activity (timeline/circadian), Biomarker Data Timeline, and Open-Loop Stim Optimizer. The prior spacing audit permitted horizontal scientific-plot scrolling; it does not prove compliance with this newer standard.

The shared Plotly manager already enabled responsive rendering and ResizeObserver. This work removes/adapts individual CSS floors and adjusts labels/margins rather than adding another global responsiveness flag. Shared font, background, grid and axis-line defaults adopt BRAVO's modern style; scientific heatmap color scales remain unchanged.

## Completed validation

Authenticated Chrome text/DOM and geometry inspection was used, without screenshots or screen capture. At 1728px desktop and 390px narrow width, checked charts fit their containers and had no axis/legend/annotation text extending outside the chart. Scientific values and heatmap scales were retained.

| Surface | Evidence |
| --- | --- |
| REDCap | 11 full-history charts, plus past-28-days view; narrow charts 342px |
| Neural Data | Five charts; final build has 83 home-program observations on each state chart and all ten graphical configuration keys on narrow screens; desktop diagrams placed beside the timeline |
| Neural toggles | Past 28 days and Stimulation context work independently; no survey-median toggle |
| Medications | Timeline plus all eleven lazily rendered condition comparisons; complete local regimen keys fit narrow screens |
| Stim Program Boxplots | Narrow Mood VAS comparison fits its 334px container; prior comparison fit regressions retained |
| Oura | Six requested metric charts; final desktop plot width 1358px, narrow 342px; local context and three controls retained |
| Oura–FreeReps | Desktop/narrow trend fit; visible blue Refresh view button with complete label |
| Neural Activity Snapshot | Four plots fit desktop/narrow; contact ticks use L GPe / R MD Thal and raw selection keys are preserved |
| Therapy History | History and impedance fit both widths; final live dates span 2025–2026, resolving the competing-render year-2000 axis bug; narrow impedance panels stack |
| Chronic Neural Activity | Four plots fit desktop/narrow; channel and therapy labels use participant-scoped display adapters |
| Biomarkers | Final live availability timeline and histogram fit desktop; narrow responsive helpers and mounted regressions cover the layout path |
| Stim Optimizer | All 20 existing saved-result figures rendered in Chrome at both widths, with stacked narrow panels and preserved values; no new participant fit |

Full portable backend: 1,426 passed / 47 optional-dependency or unavailable private-data skips. Full frontend: 488 tests / 57 suites passed. True-branch critical-scope gate: Python 99.78%, JavaScript 98.92%, every declared critical unit at least 95%. This does not claim whole-repository coverage or current participant-model validity.

The final local appliance passes health/Django/app identity checks, and all 53 served JS/CSS assets match the compiled build. See `prasad-2026-09-04-integration.md` for source revision, image identity, boundary adaptations and limitations. No cloud release, clean dependency rebuild, or exhaustive rendering of every unchanged specialized report is claimed; this closes the inventoried responsive-plot fixes and the requested Neural redesign.

## Added goal scope

The user additionally authorized integrating the latest Prasad closed-loop branch changes on 2026-09-04 while this goal was active. Finish responsive visualization verification, review incoming `shirvalkar/PS_closedloop_deployment` commits against Aditya and existing uncommitted work, then integrate reviewed changes without overwriting local work and validate the combined result. No push is authorized.
