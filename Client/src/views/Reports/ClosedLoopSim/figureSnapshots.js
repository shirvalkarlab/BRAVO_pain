/**
 * Pictures of the page's figures for the printed sign-off record (audit item [49]).
 *
 * WHY THIS RUNS IN THE BROWSER. The figures on the Closed-Loop Deployment page exist only as
 * Plotly drawings in the reader's browser -- the server never renders them, and the server-side
 * image tool this item was once thought to need is the thing that was broken. Plotly can turn a
 * drawn figure into a PNG right here (`Plotly.toImage`), so the sign-off card asks for the pictures
 * at the moment Print or Export JSON is pressed, and what goes onto paper is exactly what the
 * reader was looking at, operating point and all.
 *
 * WHY THE FIGURES ARE FOUND BY PAGE SECTION, NOT BY PANEL. The panels draw with `Plotly.react` onto
 * their own private `useRef` divs and none of them exposes a handle. Every Plotly figure carries the
 * class `js-plotly-plot`, and every section of the page has an id (`#cl-roc`, `#cl-lsb`, ...), so
 * the card looks inside the named sections and takes whatever figures are drawn there. No panel
 * file changes, and a panel that has not been opened yet (the analyst fold is collapsed by default)
 * simply contributes nothing -- and the record SAYS so, because a sheet missing a figure without a
 * word about it reads as "there was no such figure".
 *
 * A figure that fails to render to an image is reported by name rather than dropped, for the same
 * reason.
 */
import Plotly from "plotly.js-dist";

// WHICH FIGURES GO ON THE PRINTED RECORD, AND WHAT EACH IS CALLED ON PAPER. The PI's choice,
// 2026-09-10: the four sections below, in this order; the per-week refit (`cl-era`) is left off.
// `id` is the section's id in index.js; `title` is the caption a clinician reads above the picture.
// A section that draws several figures gets them all under the one caption, numbered. The first
// two sit inside the collapsed analyst fold and are reported as "not drawn" until it is opened.
export const SNAPSHOT_SECTIONS = [
  { id: "cl-roc", title: "How well band power separates high pain from low pain" },
  { id: "cl-lsb", title: "Band power in the device's own units, and where the switching value sits" },
  { id: "cl-three-source", title: "How stimulation current moved band power, measured three ways" },
  { id: "cl-evidence", title: "The three links of evidence: current to power, power to pain, current to pain" },
];

// Pixels per CSS pixel. 2 keeps axis text legible on paper without making the JSON export enormous.
const SCALE = 2;

function figuresIn(sectionId) {
  const root = document.getElementById(sectionId);
  if (!root) return [];
  // Two kinds of drawing live on this page. Plotly figures carry the class `js-plotly-plot`, and
  // only one Plotly has actually drawn counts: a div that exists but was never given data has no
  // `_fullLayout`, and asking Plotly to image it throws. The evidence panel is hand-drawn SVG
  // (`role="img"`), which Plotly cannot see, so those are taken as SVG elements in their own right.
  const plotly = Array.from(root.querySelectorAll(".js-plotly-plot"))
    .filter((gd) => gd && gd._fullLayout)
    .map((el) => ({ kind: "plotly", el }));
  const svgs = Array.from(root.querySelectorAll('svg[role="img"]'))
    .filter((el) => !el.closest(".js-plotly-plot"))
    .map((el) => ({ kind: "svg", el }));
  return [...plotly, ...svgs];
}

async function pngOf(gd) {
  const w = Math.max(320, Math.round(gd.clientWidth || (gd._fullLayout && gd._fullLayout.width) || 700));
  const h = Math.max(200, Math.round(gd.clientHeight || (gd._fullLayout && gd._fullLayout.height) || 350));
  const url = await Plotly.toImage(gd, { format: "png", width: w, height: h, scale: SCALE });
  return { image_data_url: url, width_px: w, height_px: h, format: "png" };
}

function svgImageOf(svg) {
  // The SVG is serialised as it stands on the page -- the same markup the reader is looking at --
  // and carried as an image data URL. `<img>` renders it on paper and the JSON export holds it as
  // text, so nothing is rasterised and nothing is lost.
  const clone = svg.cloneNode(true);
  if (!clone.getAttribute("xmlns")) clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const w = Math.round(svg.clientWidth || 700);
  const h = Math.round(svg.clientHeight || 350);
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  const text = new XMLSerializer().serializeToString(clone);
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
  return { image_data_url: url, width_px: w, height_px: h, format: "svg" };
}

async function imageOf({ kind, el }) {
  return kind === "svg" ? svgImageOf(el) : pngOf(el);
}

/**
 * Snapshot every drawn figure under the listed sections.
 *
 * Returns { figures, missing, captured_at } where `figures` is an ordered list of
 * { section_id, title, index, n_in_section, image_data_url, width_px, height_px, format } and `missing` lists
 * the sections that had no drawn figure, each with its title, so the record can say which pictures
 * are absent and why.
 */
export async function captureFigureSnapshots(sections = SNAPSHOT_SECTIONS) {
  const figures = [];
  const missing = [];
  for (const { id, title } of sections) {
    const gds = figuresIn(id);
    if (!gds.length) {
      missing.push({ section_id: id, title, reason: "not drawn on the page when the record was made" });
      continue;
    }
    for (let i = 0; i < gds.length; i += 1) {
      try {
        // eslint-disable-next-line no-await-in-loop
        const img = await imageOf(gds[i]);
        figures.push({ section_id: id, title, index: i + 1, n_in_section: gds.length, ...img });
      } catch (e) {
        missing.push({ section_id: id, title,
          reason: `figure ${i + 1} of ${gds.length} could not be rendered to an image (${e && e.message ? e.message : e})` });
      }
    }
  }
  return { figures, missing, captured_at: new Date().toISOString() };
}
