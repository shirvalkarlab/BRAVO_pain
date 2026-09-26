/**
 * ONE VOCABULARY FOR THE TWO SOURCES ACROSS THE WHOLE BIOMARKERS PAGE (the PI, 2026-09-25).
 * Band power comes from one of two sources and the page names them the same way everywhere:
 *   "TD"  -- band power from the time-domain recording (the voltage trace, 3 s pieces, converted
 *            with the transform constant);
 *   "PSD" -- band power from the device's own 30 s snapshots (patient events, converted with the
 *            composed bridge constant).
 * A MONTAGE OR SURVEY RECORDING IS TD ON THIS PAGE (the PI, 2026-09-26, correcting a label of the
 * night before): every montage sample the page matches, counts or draws is worked out from the
 * recording's own time-domain signal (the sample index's "Montage" rows are Welch over the
 * recording's `Data`; the timeline's montage ticks are coloured by those rows), so it is shown as
 * "TD (montage)" and counted with TD. The device's own spectrum stored with a montage
 * (`Descriptor.MedtronicPSD`) reaches only the heat-map grid's pool, where it is filed as PSD.
 * Each card introduces them once as "time domain (TD)" and "PSD (the device's 30 s snapshot)" and
 * says TD / PSD after that. The heat maps have their own, stricter guard
 * (`heatmapSourceWords.test.js`); this one reads every string literal and every piece of JSX text
 * the page's other components can print (comments stripped) and fails if an older word for either
 * source comes back. "streaming" is NOT on the list here: on the timeline it names a kind of
 * recording (streaming, chronic, montage), not one of the two sources.
 */
import fs from "fs";
import path from "path";

import { modeledLegendName, routeLabel } from "./calibrationLabels";
import { SOURCE_SERIES, seriesOf } from "./timingHistogramModel";
import { computeMatchedScanModel } from "./binarizationModel";

// Every file in this folder whose text the Biomarkers page prints (BandTimeSweepPanel.js is
// rendered by nothing and is left out).
const FILES = [
  "index.js", "BiomarkerDataTimeline.js", "BiomarkerTimeline.js", "BinarizationPreview.js",
  "MatchWindowBand.js", "TimingHistogram.js", "timingHistogramModel.js", "CalibrationInEffectPanel.js",
  "calibrationLabels.js", "BiomarkerHeatmapGrids.js", "gridReadouts.js", "ReportSharingNote.js",
  "BiomarkerAnalytics.js", "binarizationModel.js",
];
const TD_DEF = "time domain (TD)";
const PSD_DEF = "PSD (the device's 30 s snapshot)";
const OLD_WORDS = new RegExp([
  "\\bvoltage\\b", "\\bFFT\\b", "snapshot", "time[- ]domain", "\\btiles?\\b", "transform DSP",
  "PSD\u2192LSB", "TD-transform", "PSD-bridge", "onboard", "Welch PSD", "PSD-first",
  "TD streaming", "full-spectrum PSD",
].join("|"), "i");

function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'\\])\/\/[^\n]*/g, "$1");
}
function printable(src) {
  const code = stripComments(src);
  const lits = code.match(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`/g) || [];
  const jsx = (code.match(/>([^<>{}]*[A-Za-z][^<>{}]*)</g) || []).map((s) => s.slice(1, -1));
  return lits.concat(jsx);
}
function withoutDefinitions(text) {
  return [TD_DEF, PSD_DEF].reduce((s, d) => s.split(new RegExp(d.replace(/[()]/g, "\\$&"), "i")).join(""), text);
}
function offending(src) {
  return printable(src).map(withoutDefinitions).filter((t) => OLD_WORDS.test(t));
}
function read(f) {
  return fs.readFileSync(path.join(__dirname, f), "utf8");
}

describe("the Biomarkers page names the two sources TD and PSD only", () => {
  FILES.forEach((f) => {
    test(`${f}: no older word for either source in any printable text`, () => {
      expect(offending(read(f))).toEqual([]);
    });
  });

  test("the timing histogram's legend names the sources TD and PSD, montage under TD", () => {
    expect(SOURCE_SERIES.map((s) => s.name)).toEqual(["TD (streaming)", "TD (montage)", "PSD (patient event)"]);
  });

  // Montage under PSD, in any spelling a reader could see: "PSD (montage)", "montage PSD",
  // "PSD from montages", "PSD (...), from a patient event or a montage" -- a "PSD" followed, in the
  // same sentence and with no "TD" in between, by "montage".
  const MONTAGE_AS_PSD = /\bPSD\b(?:(?!\bTD\b)[^.;\n]){0,80}\bmontages?\b|\bmontages?\b[\s-]*\bPSDs?\b/i;

  FILES.forEach((f) => {
    test(`${f}: a montage is never shown under PSD (it is TD on this page)`, () => {
      expect(printable(read(f)).filter((t) => MONTAGE_AS_PSD.test(t))).toEqual([]);
    });
  });

  test("the montage guard catches montage shown under PSD (negative control)", () => {
    const src = 'const a = "PSD (montage)"; const b = "montage PSD \u00b7 x";\n'
      + 'const c = `${n} PSD (patient event), PSD from montages and surveys`; // PSD (montage) in a comment\n'
      + 'const d = "TD (montage)"; const e = "PSD (patient event)";\n'
      + 'const f = "PSD (the device\'s 30 s snapshot), from a patient event or a montage.";\n'
      + 'const g = "3 PSD (patient event), 2 TD (montage)";';
    expect(printable(src).filter((t) => MONTAGE_AS_PSD.test(t))).toHaveLength(4);
  });

  test("a montage sample is counted in the TD group, never the PSD one", () => {
    expect(seriesOf("Montage")).toBe("td_montage");
    expect(seriesOf("BrainSense streaming")).toBe("trace");
    expect(seriesOf("Indefinite stream")).toBe("trace");
    expect(seriesOf("Patient event")).toBe("event");
    const H = 3600;
    const scanIndex = [
      { t: 1 * H, channel: "ZERO_THREE_LEFT", source: "BrainSense streaming" },
      { t: 2 * H, channel: "ZERO_THREE_LEFT", source: "Montage" },
      { t: 3 * H, channel: "ZERO_THREE_LEFT", source: "Montage" },
      { t: 4 * H, channel: "ZERO_THREE_LEFT", source: "Patient event" },
    ];
    const painSeries = { t: [1 * H, 2 * H, 3 * H, 4 * H], y: [2, 4, 6, 8] };
    const m = computeMatchedScanModel({ scanIndex, painSeries, toleranceMin: 1, strategy: "median",
                                        matchDirection: "nearest" });
    expect(m.counts.n_matched).toBe(4);
    expect(m.counts.n_matched_td).toBe(3);          // streaming 1 + montage 2: the TD group
    expect(m.counts.n_matched_td_montage).toBe(2);  // the montage part of it, shown as TD (montage)
    expect(m.counts.n_matched_event).toBe(1);       // the only PSD
    expect(m.counts.n_matched_montage).toBeUndefined();
    const all = ["low", "high", "excluded"].map((b) => m.counts.by_source[b]);
    expect(all.reduce((n, g) => n + g.td, 0)).toBe(3);
    expect(all.reduce((n, g) => n + g.td_montage, 0)).toBe(2);
    expect(all.reduce((n, g) => n + g.event, 0)).toBe(1);
    all.forEach((g) => expect(g.montage).toBeUndefined());
  });

  test("each card defines both terms where a reader first meets them", () => {
    // the matching card: the timing histogram's caption, under its legend
    const hist = stripComments(read("TimingHistogram.js"));
    expect(hist).toContain(TD_DEF);
    expect(hist).toContain(PSD_DEF);
    // the calibration card: its two headings
    const cal = stripComments(read("CalibrationInEffectPanel.js"));
    expect(cal.split(new RegExp("time domain \\(TD\\)", "i")).length - 1).toBe(1);
    expect(cal.split(PSD_DEF).length - 1).toBe(1);
    // the acquisition timeline: PSD in its first legend entry, TD in the first entry that uses it
    const tl = stripComments(read("BiomarkerDataTimeline.js"));
    expect(tl.split(PSD_DEF).length - 1).toBe(1);
    expect(modeledLegendName([{ method: "td_transform_x_k=345.59" }, { method: "event_psd_bridge_x_k=72.16" }]))
      .toContain(TD_DEF);
  });

  test("the calibration labels keep the two constants' own names beside TD and PSD", () => {
    expect(routeLabel("td_transform_x_k=345.59")).toBe("TD, transform constant \u00d7345.59");
    expect(routeLabel("event_psd_bridge_x_k=72.16")).toBe("PSD, bridge constant \u00d772.16");
  });

  test("the calibration card never calls the composed bridge measured", () => {
    const cal = stripComments(read("CalibrationInEffectPanel.js"));
    expect(cal).toMatch(/bridge constant \(composed\)/);
    expect(cal).not.toMatch(/bridge constant \(measured\)/);
    expect(cal).toMatch(/Composed, not measured/);
  });

  test("the guard itself catches an old word (negative control)", () => {
    const src = 'const a = "median over every device FFT snapshot"; // voltage trace in a comment is fine\n'
      + "const b = <span>VOLTAGE TRACE \u2192 DEVICE UNITS</span>;\n"
      + 'const c = "Its time-domain value"; const d = "the nearest 10 of the 3 s tiles";\n'
      + 'const e = "time domain (TD) and PSD (the device\'s 30 s snapshot)";';
    expect(offending(src)).toHaveLength(4);
    expect(offending("// only a comment about the voltage trace and the FFT snapshots")).toEqual([]);
  });
});

/**
 * ONE NAME PER THING, the design review's B5 (2026-09-26, approved by the PI). The page splits the
 * ratings into high and low pain; it says so rather than "binarize"; the older splitting rule is
 * named for what it does, not for the algorithm ("KMeans"); the matching sliders say what they count
 * in plain words ("samples", "TD around each rating") rather than "LSB samples" or "TD signal per
 * rating". Read from every string and piece of JSX text the page can print, comments stripped.
 * Three kinds of string are code, never printed, and are allowed: the import paths of the two
 * files still named for the old word, and the two keys the page's state uses ("binarization" for
 * the timeline's colour mode, "kmeans" for the splitting rule), which reach no screen.
 */
const B5_WORDS = /binari[sz]|\bk-?means\b|\bLSB samples\b|\bsignal per rating\b|\(legacy\)/i;
const B5_CODE_ONLY = /^["'`](\.\/[A-Za-z]+|binarization|kmeans)["'`]$/;
function b5Offending(src) {
  return printable(src).filter((t) => !B5_CODE_ONLY.test(t)).filter((t) => B5_WORDS.test(t));
}

describe("one name per thing on the Biomarkers page (design review B5)", () => {
  FILES.forEach((f) => {
    test(`${f}: no "binarize", "KMeans", "LSB samples" or "signal per rating" in printable text`, () => {
      expect(b5Offending(read(f))).toEqual([]);
    });
  });

  test("the guard catches the old words and lets the code keys through (negative control)", () => {
    const src = 'import X from "./BinarizationPreview"; const m = "binarization"; const k = "kmeans";\n'
      + 'const a = { key: "kmeans", label: "KMeans (legacy)" };\n'
      + "const b = <span>{\"Binarization\"}</span>; const c = `Max LSB samples per pain rating: ${n}`;\n"
      + 'const d = "TD signal per rating (seconds)"; const e = "Data available to binarize";\n'
      + "// a comment about binarization is fine";
    expect(b5Offending(src)).toHaveLength(5);
  });
});
