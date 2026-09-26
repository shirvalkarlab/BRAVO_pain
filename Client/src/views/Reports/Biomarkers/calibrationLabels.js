/**
 * Labels for the calibration constant a modeled LSB point was computed with, read from what the
 * server sent rather than typed here (decision 209, 2026-09-20).
 *
 * Every modeled point carries `method` ("td_transform_x_k=349.10", "event_psd_bridge_x_k=72.90") and
 * every per-rating record carries `reason` ("direct TD->LSB transform (k=349.10)"). The number after
 * "k=" is the constant in effect on the server the day the point was computed, so the page can never
 * print a constant other than the one its numbers were built with.
 */

/** The constant named in a served method or reason string, as the server wrote it, or null. */
export function kFromServed(text) {
  const m = /k=([0-9]+(?:\.[0-9]+)?)/.exec(String(text || ""));
  return m ? m[1] : null;
}

/** "TD, transform constant ×345.59" / "PSD, bridge constant ×72.16" / "modeled"; no number when none
 *  was served. TD and PSD are the page's one vocabulary for the two sources (the PI, 2026-09-25):
 *  TD for the time-domain recording, PSD for the device's 30 s snapshot. */
export function routeLabel(method) {
  const s = String(method || "");
  const k = kFromServed(s);
  const suffix = k ? ` ×${k}` : "";
  if (s.startsWith("td_transform")) return `TD, transform constant${suffix}`;
  if (s.startsWith("event_psd_bridge")) return `PSD, bridge constant${suffix}`;
  return "modeled";
}

/** The legend entry for the modeled-LSB glyphs, naming the constants actually seen in the data. It is
 *  the timeline legend's first entry that says TD, so it defines the term. */
export function modeledLegendName(points) {
  let kTd = null; let kBridge = null;
  (points || []).forEach((p) => {
    const s = String((p && p.method) || "");
    if (!kTd && s.startsWith("td_transform")) kTd = kFromServed(s);
    if (!kBridge && s.startsWith("event_psd_bridge")) kBridge = kFromServed(s);
  });
  const td = kTd ? ` ×${kTd}` : "";
  const br = kBridge ? ` ×${kBridge}` : "";
  return `modeled LSB  (○ time domain (TD), transform constant${td} · ◇ PSD, bridge constant${br}; red ring = TD saturated)`;
}
