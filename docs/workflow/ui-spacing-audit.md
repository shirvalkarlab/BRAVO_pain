# UI spacing audit — 2026-09-04

Objective: make BRAVO page content, navigation, menus, and dialogs readable without overlapping or clipped text across desktop, tablet, and phone widths.

Work is on the existing dirty `aditya` checkout. Earlier backend and scientific changes are preserved. The session bootstrap fetched both remotes; tracking branches were current. No commit or push is part of this task.

## Changes

- Sidebar route labels and branding wrap; compact navigation reveals labels on expansion. Section headings follow the compact state.
- Breadcrumbs have normal line height and can wrap. Navigation buttons have accessible names; account menus anchor to their button.
- Tab strips scroll when necessary, with individually bounded, wrapping labels. Pagination and dialog action rows wrap.
- Dialog papers and their content have bounded widths. Autocomplete options and selected chips can wrap.
- Report-card actions remain below descriptions in normal layout. Cards use one column on phones.
- Profile, study, participant, survey, date-range, and token-entry controls adapt to narrow screens. Long field labels are shortened without removing their meaning.
- Therapy details can wrap alongside the electrode graphic. The biomarker metric selector shrinks to its card width.
- Dense optimizer tables and scientific charts scroll within their cards. Snapshot categories use angled labels with sufficient margins; impedance subtitles wrap.
- Histogram class summaries are wrapping cards above the plot, preserving the existing sample/day and matched PSD/rating counts.
- REDCap legends, medication class names, stage headings, and transition labels have dedicated space. Oura/native Plotly charts resize when their containers change. The shared renderer also reconciles dimensions after drawing finishes, including first-load sidebar expansion; one observer is retained per graph and removed on purge.

## Validation

Text-only isolated Chrome checks; no screenshots, capture helpers, or Chrome AppleScript JavaScript. Live data checks use a temporary read-only session. Editor and research states unavailable to that account use explicitly synthetic browser-only API responses; those checks do not save records or launch analyses.

- Frontend regressions: **202 tests / 29 suites passed** using Node 22 in Docker. This includes two new checks preserving daily and matched-pain-rating counts after moving histogram summaries outside the plot.
- Production frontend build: passed from the final source.
- Route sweep: **170 checks**, covering 34 registered/general routes at widths **1440, 1024, 768, 390, and 320 px**. No detected page overflow, clipped UI labels, text intersections, or page errors.
- Logged-out home, login, and offline entry: **15 checks passed**.
- Live navigation, report tabs, dropdowns, and unsaved dialogs: **39 states passed**.
- Editor fixtures: **24 states passed**, including participant creation, file upload, and survey editing/viewing.
- Populated research fixtures: **12 states passed**, including multimodal biomarker timelines, histogram summaries, optimizer tables/figures, and selected-band evidence review. These fixtures are explicitly synthetic; no analyses or clinical actions were run.
- Live Oura, REDCap, therapy, neural activity, and snapshot charts: **40 states** with transformed SVG text geometry checks. All 40 states pass with no detected SVG text intersections or labels outside the chart. The previously failing impedance first-load/sidebar sequence also passes; plot and container widths now agree. Charts are allowed two seconds to settle after viewport/sidebar resizing; measuring during transitions produced transient false alarms.

The audit covers reachable views, shared controls, and representative loaded data states; it cannot enumerate every possible future data combination. Dense scientific plots and tables preserve their contents with horizontal scrolling inside their own cards. Both theme variants share the layout fixes. The initial pass used geometry checks without screenshots, as required by the then-current workspace instruction. On user review, this missed an unacceptable zero-width branding label. The subsequent user request explicitly authorized screen viewing; see the visual follow-up below.

Reproducible audit scripts are under `output/playwright/layout-*.cjs`. They use the local production bundle through `LOCAL_BUILD=1` while retaining real server HTML/CSRF. `layout-audit.cjs` supports `ROUTES`, `WIDTHS`, `REPORT`, and `PUBLIC=1`. Audit tokens and detailed participant-facing output are temporary and are not included here.

Source backups for this task are under `output/layout-before/`.

## Local deployment and handoff

The UI was deployed to `bravo-local:aditya` using the previously running backend image as its base, copying only the verified client bundle and regenerating its HTML template. The sync service and database/storage volumes were retained. No commit or push was made.

- Release image: `sha256:5898a45d1d42face74b04a054ccd1d919d5af142d69a4a290144cf3e4913b459`.
- Previous image retained as `bravo-local:before-ui-spacing` for rollback.
- Live main bundle: `/static/js/main.a39e8d91.js`; SHA-256 `92e0fe7af772690b252df085d37267212f7d31fd30e59bae04e258ac5d2c9a69` matches the final local build byte for byte.
- `scripts/bravo-appliance check` passed after replacement: app, database, storage, Django checks, and expected localhost binding.
- Isolated authenticated browser confirmed the Aditya brand, correct title, and no page errors at `http://127.0.0.1:8080/database`.
- Existing Chrome tab was refreshed and inspected using URL/title only. It displays `http://127.0.0.1:8080/index` with title `UF BRAVO Platform`.
- Direct checks against the deployed server passed for database, therapy history, and REDCap at three widths (9 checks), without substituting local assets.
- The temporary read-only audit session and its local token file were removed. Detailed participant-facing output remains outside this report in temporary local files.


## Visual follow-up — sidebar branding and Sync Data

The user explicitly authorized screen viewing after the first handoff. Direct inspection of their logged-in Chrome page showed the brand name stacked one character per line. Its container had a computed width of 0px because `width={!brandName && "100%"}` evaluated to false. Normal wrapping had exposed this pre-existing width expression as a severe visual regression, which the earlier geometry checks missed.

Removed the false width prop, gave the title flexible remaining width, and hid it fully in compact navigation instead of retaining an invisible tall label. Full branding remains visible when the sidebar expands. Direct screenshots of the deployed page confirm that expanded branding fits on two lines and compact navigation has evenly spaced icons. The compact labels retain their accessible link names while their invisible text is constrained to zero height. The brand link has an explicit accessible name. The sidebar was returned to expanded mode with Database open. The production build and post-replacement appliance checks pass, and the served bundle matches the local build.

The Sync Data control was not removed. On the user's admin account it is visible and enabled on Database, beneath Upload Data and Add New Participant, with the label “SYNC DATA FROM REDCAP, DROPBOX, AND OURA”. Its existing admin-only visibility rule was retained. No sync was started during this investigation.


## September 4 responsive redesign

The completed design and acceptance record is [Modern responsive scientific visualizations](responsive-scientific-visualizations.md). It supersedes the earlier six-chart Neural layout and any earlier allowance for horizontal scientific-plot scrolling. Mode/cycling now share one device/group state chart; contacts use graphical lead configurations.
