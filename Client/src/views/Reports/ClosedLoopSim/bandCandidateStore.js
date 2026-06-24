/**
 * BandCandidate handoff store (DESIGN_biomarker_pipeline_v2 §6).
 *
 * The discovery/Biomarkers view emits a validated BandCandidate; the Closed-Loop Simulation /
 * threshold-deployment view consumes it. The two views are decoupled through the §6 contract —
 * no shared React context — so the handoff rides localStorage, keyed per participant, with a JSON
 * download/upload as the explicit persistence escape hatch the design calls for.
 *
 * Keying per participant prevents a committed band from one patient leaking into another's
 * deployment view. The stored envelope wraps the raw band_candidate with a committed_at stamp and
 * the participant uid so a downloaded file is self-describing.
 */

const KEY_PREFIX = "bravo.bandCandidate.";

function _key(participantUid) {
  return KEY_PREFIX + String(participantUid || "unknown");
}

function _envelope(participantUid, bandCandidate) {
  return {
    schema: "bandcandidate_envelope_v1",
    participant_uid: participantUid || null,
    committed_at: new Date().toISOString(),
    band_candidate: bandCandidate,
  };
}

/** Persist a committed BandCandidate for a participant. Returns the stored envelope. */
export function commitBandCandidate(participantUid, bandCandidate) {
  const envelope = _envelope(participantUid, bandCandidate);
  try {
    window.localStorage.setItem(_key(participantUid), JSON.stringify(envelope));
  } catch (e) {
    // Storage full / disabled (private mode): the download path is the fallback.
    // eslint-disable-next-line no-console
    console.warn("commitBandCandidate: localStorage write failed", e);
  }
  return envelope;
}

/** Read the committed BandCandidate envelope for a participant, or null if none. */
export function loadBandCandidate(participantUid) {
  try {
    const raw = window.localStorage.getItem(_key(participantUid));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

/** Clear the committed BandCandidate for a participant. */
export function clearBandCandidate(participantUid) {
  try {
    window.localStorage.removeItem(_key(participantUid));
  } catch (e) {
    /* no-op */
  }
}

/** Trigger a browser download of the committed envelope as a .json file. */
export function downloadBandCandidate(participantUid, bandCandidate) {
  const envelope = _envelope(participantUid, bandCandidate);
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

/** Parse an uploaded envelope or bare BandCandidate JSON; returns {band_candidate, ...} or null. */
export function parseUploadedCandidate(text) {
  try {
    const obj = JSON.parse(text);
    if (obj && obj.band_candidate) return obj;            // full envelope
    if (obj && obj.schema_version === "bandcandidate_v1") {
      return { band_candidate: obj, participant_uid: null, committed_at: null };  // bare candidate
    }
    return null;
  } catch (e) {
    return null;
  }
}
