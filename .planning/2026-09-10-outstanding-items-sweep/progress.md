# Progress — outstanding items sweep

## 2026-09-10
- Plan opened after decision 112. Item 1 started: read DeploySignoffCard.js, deployPrint.css,
  index.js section ids, and how each panel draws (Plotly.react on a useRef div, purge on unmount).
- Item 1 built. PI supplied the section list (four sections, no per-week refit); the entries were
  strings where the code reads objects, so they were put in `{id,title}` form with plain captions.
  `cl-evidence` is hand-drawn SVG, so the helper serialises `svg[role="img"]` alongside Plotly.
  Field renamed `png_data_url` -> `image_data_url` since SVG ones are not PNG. Build clean, neither
  touched file in the warnings; five owned strings in `703.9c3946c8.chunk.js`. Not yet watched.
- Item 1 watched live on RCS08 with the PI signed in. Two defects found on the way and fixed/handled:
  the grid and report shared one cache slot (fixed, `CL.grid`); two stale gunicorn workers
  (SIGHUP, four fresh workers). Print: 11 pictures, print called once after they were in the
  document; Export JSON: 567 KB, 11 pictures, missing empty; fold closed: 6 pictures and two named
  as NOT ON THIS RECORD. Display-size fix so a 2x PNG shows at the figure's own size. Reliable-change
  panel seen rendered for the first time, numbers equal decision 111's.
- PI's brief for the next session (CL page redesign) recorded as Phase 7 and findings §3.
- Item 2 done. Found first that the "spectral point" is on no page (per_pro_lsb_spectrum has no
  production caller since 2026-06-28); measured 240/240 equal on RCS08; wrote
  `test_timeline_circle_equals_spectrum_point.py` (3 tests, live one ~16 s, skips without RCS08).
  Container 636/0 (+3). Host suite untouched (Biomarkers is not in it).
- Item 2 follow-up: PI had `per_pro_lsb_spectrum` (+ scan, + indexed twin, + my test, + 7 DecodeCommon
  tests) deleted — decision 115. Trap met and caught: `CENTERS` lived in the removed test block and
  the tile-cache test still needs it. Container 626/0; host 1018/42/1 known. House rule added: never
  write "spectrum" bare. Item 3 folded into Phase 7. Suite logs now saved to /tmp/claude-502/.
- Item 4 done, decision 116. The always-failing host test was also wiping the production
  closed_loop cache on every suite run (fixture teardown + override=None). Measured: old test 2->0
  files, new 2->2, full host suite 1019/42/0 with the directory intact. Host run logged to
  /tmp/claude-502/host_item4.log.
