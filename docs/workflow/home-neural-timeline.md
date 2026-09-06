# Home Neural Data — current and previous visit periods

Requested September 4, 2026. The original Neural Data settings view is renamed **Stim Program Settings**. A separate **Neural Data** tab follows it, before Medications.

## Chart contract

Question: How do stored biomarker power and stimulation amplitude vary within the current versus preceding stimulation-visit periods, with the correct controlling sensing source for each stimulated side?

Four full-width responsive plots are grouped current-left/current-right, then previous-left/previous-right. Each uses blue biomarker power on the left y-axis and orange stimulation amplitude (mA) on the right, with points and thin connecting guides. Thresholds are dashed/dotted neutral lines only within the relevant source settings interval. Missing values, ambiguous mappings and gaps are explicit; there is no smoothing, resampling, outlier replacement, modeled filling or inference of instantaneous threshold crossings. Local legends wrap instead of creating horizontal scrollbars. Hover identifies the relevant stimulation contacts, compact frequency/amplitude/pulse width, sensing source/contacts/band, mode and thresholds. Clicking opens complete settings for that interval.

## Sources and interpretation

- Native Percept `DiagnosticData.LFPTrendLogs`, already decoded into `MedtronicChronicBrainSense` recordings. The new read-only endpoint reads stored source values rather than the legacy chronic renderer's iterative six-SD replacement.
- Medtronic local `Percept/context/white-paper-percept.pdf`, printed pp9–10: LFP power and amplitude are device-stored ten-minute averages. This is not a ten-minute transmission guarantee. Page14 distinguishes captured LFP levels from the final programmed threshold; page17 supports contralateral sensing control.
- Stimulation sides remain fixed per panel. `GangedToHemisphere` resolves the sensing controller from the same device/group; the biomarker and thresholds follow that source, while amplitude remains the stimulated side. Missing/conflicting control mappings never imply ipsilateral control.
- The full reviewed REDCap stimulation-testing calendar defines visit boundaries, including visits with unchanged programs. Current is latest reviewed visit to now; previous is its predecessor to the latest visit. Whole testing dates and overlapping averaging bins are excluded conservatively because exact departure/bin alignment is not established.
- Settings are observation-based home configurations. They are not proof of exact activation times. Unknown intervals are retained without carrying settings through them. Clinical-note adjustments retain their source/evidence and do not rewrite exports.
- A single-threshold export with unresolved unequal threshold values is labeled explicitly, rather than applying the capture formula to already-programmed threshold fields. Sensing-only/paused observations do not draw active control thresholds.
- Units are the recorded device LFP power scale (LSB), not a new physical-unit spectral estimate.

## Acceptance

Completed September 4, 2026:

- Full backend validation: 1,443 passed, 47 optional-dependency skips. Full frontend validation: 525 passed. The existing critical branch-coverage gate passed with the new backend and frontend files included; no new coverage exceptions were added. Focused cases cover same-side/contralateral mapping, sensing-only/single/dual modes, unchanged-program visits, clinic boundaries, raw missing/zero/conflicting values and account/participant request isolation.
- Offline Node 22 frontend and local appliance builds passed. Only the web container was replaced; database, Redis and sync services were preserved. The running image matches `bravo-local:aditya`, digest `sha256:af3f5ba255eb32dd7e01c17b3509a21b936e17d88fbeba4c4b2a839b012c8f13`. The prior image is retained as `bravo-local:before-home-neural`.
- `bravo-appliance check` passed database/storage/Django and exact localhost application checks. All 53 served JavaScript/CSS assets match the compiled build byte for byte, and all entrypoints are present in the served page.
- Normal viewer-account login in Chrome succeeded. The Aditya report has the requested six-tab order, the renamed settings tab retains its five plots, and the new tab has exactly four chronic plots. Current is September 2 to present; previous is August 18 to September 2.
- Live current panels each contain 30 biomarker and 30 amplitude averages. A selected right-side point explicitly identifies contralateral L GPe sensing, contacts 1–3, 23.44 Hz, right-side amplitude and lower/upper thresholds 166/167 LSB. Clicking the point opens the matching complete group/bilateral settings and clinical-note evidence. Previous panels each retain 1,010 resolved biomarker and 1,060 amplitude averages, with no active threshold guides for sensing-only periods.
- Text-only DOM/geometry checks at 1,728 px and 390 px: all four plots fit their containers (1,358 px and 342 px respectively), both y-axis titles and tick labels remain within plot bounds, and document width equals viewport width. Narrow-screen tooltip width was 272 px and fully within the viewport; only one detailed tooltip appeared. The horizontal tab navigator remains intentional. No screenshots or capture tools were used. Desktop sizing was restored and Neural Data left open in Chrome.

Validation logs: `/private/tmp/bravo-home-neural-full-backend.log`, `/private/tmp/bravo-home-neural-full-frontend.log`, `/private/tmp/bravo-home-neural-ui-tests/tests.log`, `/private/tmp/bravo-home-neural-tests/tests.log`, `/private/tmp/bravo-home-neural-chart-tests.log`. These local temporary logs are verification evidence, not tracked source data. Limited current-period coverage is displayed with explicit counts and latest recorded-average time; the view does not claim continuous data through the present.
