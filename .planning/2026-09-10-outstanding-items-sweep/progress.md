# Progress — outstanding items sweep

## 2026-09-10
- Plan opened after decision 112. Item 1 started: read DeploySignoffCard.js, deployPrint.css,
  index.js section ids, and how each panel draws (Plotly.react on a useRef div, purge on unmount).
- Item 1 built. PI supplied the section list (four sections, no per-week refit); the entries were
  strings where the code reads objects, so they were put in `{id,title}` form with plain captions.
  `cl-evidence` is hand-drawn SVG, so the helper serialises `svg[role="img"]` alongside Plotly.
  Field renamed `png_data_url` -> `image_data_url` since SVG ones are not PNG. Build clean, neither
  touched file in the warnings; five owned strings in `703.9c3946c8.chunk.js`. Not yet watched.
