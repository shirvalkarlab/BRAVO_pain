/** Candidate choices live only in this tab. Evidence is revalidated by the server on entry. */
const KEY_PREFIX = "bravo.bandCandidate.";
const choices = new Map();

function _envelope(participantUid, bandCandidate, details = {}) {
  return {
    schema: "bandcandidate_envelope_v2",
    participant_uid: participantUid || null,
    committed_at: new Date().toISOString(),
    band_candidate: bandCandidate,
    InputManifest: details.InputManifest || null,
    request_params: details.requestParams || {},
  };
}

export function commitBandCandidate(participantUid, bandCandidate, details = {}) {
  const envelope = _envelope(participantUid, bandCandidate, details);
  choices.set(String(participantUid), envelope);
  return envelope;
}

export function loadBandCandidate(participantUid) {
  // Retire old persistent evidence rather than silently reviving it after a data/QC change.
  try { window.localStorage.removeItem(KEY_PREFIX + String(participantUid)); } catch (e) { /* optional storage */ }
  return choices.get(String(participantUid)) || null;
}

export function clearBandCandidate(participantUid) {
  choices.delete(String(participantUid));
  try { window.localStorage.removeItem(KEY_PREFIX + String(participantUid)); } catch (e) { /* optional storage */ }
}

/** Trigger a browser download of the committed envelope as a .json file. */
export function downloadBandCandidate(participantUid, bandCandidate, details = {}) {
  const envelope = _envelope(participantUid, bandCandidate, details);
  const bc = bandCandidate || {};
  const contact = (bc.contact || "band").toString();
  const ctr = bc.center_freq_hz != null ? `${Number(bc.center_freq_hz).toFixed(1)}Hz` : "";
  const metric = (bc.label && bc.label.pro_metric) || "metric";
  const fname = `BandCandidate_${participantUid || "pt"}_${metric}_${contact}_${ctr}.json`
    .replace(/\s+/g, "_");
  const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fname;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
  return fname;
}

/** Uploaded evidence is never trusted: only a same-participant selection can be revalidated. */
export function parseUploadedCandidate(text, participantUid) {
  try {
    const obj = JSON.parse(text);
    if (!participantUid || !obj || String(obj.participant_uid) !== String(participantUid)) return null;
    const bc = obj.band_candidate;
    if (!bc || typeof bc.contact !== "string" || !bc.contact ||
        bc.center_freq_hz == null || !Number.isFinite(Number(bc.center_freq_hz))) return null;
    return obj;
  } catch (e) { return null; }
}
