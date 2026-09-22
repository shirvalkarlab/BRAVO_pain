# Progress

## 2026-09-21
- Opened.
- Backend: five new tests RED then GREEN, 50 / 50 in test_titration_plan.py; host 1424 / 2 / 0, container 673 / 0 (run_both_suites.sh).
- Page: TitrationSessionCard.js section "Exploratory ladder for the pair the screen prefers" + per-side sheet table; four jest tests RED then GREEN; 31 / 31 across the seven Stim Optimizer suites; bundle chunk 100.18f67798; workers reloaded.
- Live RCS08: proposed Left, L C+1-2- for L 0-3+, 125 Hz (in force 55), pw 100, ceiling 4.5, right held 2.5 mA, watch 24.5-27.5 Hz clear, 15 ladder steps + 3 holds, 51 min; sheet rows 68 -> 101.
## 2026-09-22
- Field diff before/after: 8,821 common, 8 differing (bookkeeping), 1,630 added, 2 removed. Decision 230 written. Committed and pushed at the PI's request while the research workers run; the live watch of the card waits on his login.

- 2026-09-22 step 6 (outside this plan, decision 240): the embargoed time-blocked folds, the current-confound gate and the pre-build diagnostic; container 679 -> 691 / 0, host 1429 / 2 / 0; commit 881d665f.

- 2026-09-22 decision 241: the covariate shape (line, curve, three kernels, per setting) in both guards; container 691 -> 702 / 0, host 1429 / 2 / 0.
- Session ran in a cloud clone, not the lab machine: no container, no database, no bridge, so no live RCS08 numbers and no container suite. What the cloud clone CAN do, once the pinned packages are installed: the host suite (1423 passed / 0 failed / 3 skipped) and the frontend build and its jest suites.
- The ladder card's own title text was found in the served chunk 100.18f67798, which is the chunk the commit named, so the card IS in the bundle the page loads. That is as far as the "watched live" step goes without a browser; it still needs the PI's login to be seen rendered.
- Separate small fix while blocked (decision 244 (first written as 231)): the Closed-Loop page's jump links had two sections in the wrong order and a down-arrow that claimed the sign-off card was the bottom of the page. Fixed, with a test that compares the link order against the page file's own order. Chunk 603.e66d20d2.
