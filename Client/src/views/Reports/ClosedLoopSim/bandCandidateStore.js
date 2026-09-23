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
 *
 * THE SERVER HOLDS THE RECORD SINCE 2026-09-23 (the PI's ruling 8, decision 233). Browser storage
 * alone meant another browser, or a cleared one, opened on "No band has been committed", and nothing
 * recorded which band was chosen, when or by whom. `/api/queryClosedLoopChosenBand` keeps an
 * append-only record; browser storage is now a mirror of it, still read first so the page draws at
 * once, then replaced by the server's answer. When the server cannot be asked, or a save does not
 * land, the status says so: the browser copy is never presented as the record.
 */
import { SessionController } from "database/session-control";

const ENDPOINT = "/api/queryClosedLoopChosenBand";

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

function _writeLocal(participantUid, envelope) {
  try {
    window.localStorage.setItem(_key(participantUid), JSON.stringify(envelope));
  } catch (e) {
    /* storage full or disabled: the server copy is the record */
  }
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

/**
 * Where the chosen band shown on the page is held, for the page to say so: `where` is "server" when
 * the server's record says it, "browser" when only this browser does (with the `reason`).
 */
function _status(where, { saved = where === "server", reason = null, record = null } = {}) {
  return {
    where, saved, reason,
    chosenBy: record ? record.chosen_by || null : null,
    // "browser_storage" means the band was chosen in a browser before the server kept a record, and
    // `chosenBy` is then who carried it over, not who chose it.
    source: record ? record.source || null : null,
    recordedUtc: record ? record.recorded_utc || null : null,
  };
}

function _why(err) {
  return (err && err.message) || String(err || "the server did not answer");
}

/**
 * Ask the server for the chosen band and bring this browser into line with it. Resolves to
 * `{ envelope, status }`; never rejects.
 *
 * - the server holds a band: it is shown and mirrored here;
 * - the server's newest row is a clear: this browser is cleared too;
 * - the server has never heard of a band and this browser holds one (chosen before the record
 *   existed): it is sent once as "browser_storage", keeping the time it was chosen;
 * - the server cannot be asked: this browser's copy, labelled as held in this browser only.
 */
export async function syncChosenBand(participantUid) {
  const local = loadBandCandidate(participantUid);
  let data;
  try {
    const res = await SessionController.query(ENDPOINT, { ParticipantId: participantUid, Action: "read" });
    data = (res && res.data) || {};
  } catch (err) {
    return { envelope: local, status: _status("browser", { reason: _why(err) }) };
  }
  if (!data.available) {
    return { envelope: local, status: _status("browser", {
      reason: data.reason || "the server could not read its record" }) };
  }
  if (data.record && data.record.band_candidate) {
    _writeLocal(participantUid, data.record);
    return { envelope: data.record, status: _status("server", { record: data.record }) };
  }
  const history = data.history || [];
  if (history.length) {                       // the newest row is a clear
    clearBandCandidate(participantUid);
    return { envelope: null, status: _status("server") };
  }
  if (local && local.band_candidate) {        // chosen before the server kept a record
    return _send(participantUid, local, {
      ParticipantId: participantUid, Action: "choose", BandCandidate: local.band_candidate,
      Source: "browser_storage", CommittedAt: local.committed_at,
    });
  }
  return { envelope: null, status: _status("server") };
}

async function _send(participantUid, localEnvelope, body) {
  try {
    const res = await SessionController.query(ENDPOINT, body);
    const data = (res && res.data) || {};
    if (data.saved && data.record) {
      _writeLocal(participantUid, data.record);
      return { envelope: data.record, status: _status("server", { record: data.record }) };
    }
    return { envelope: localEnvelope, status: _status("browser", {
      reason: data.reason || "the server did not record it" }) };
  } catch (err) {
    return { envelope: localEnvelope, status: _status("browser", { reason: _why(err) }) };
  }
}

/**
 * Record a chosen band: in this browser at once (so the page moves immediately) and on the server.
 * `source` is "grid" or "upload". Resolves to `{ envelope, status }`; never rejects.
 */
export async function recordChosenBand(participantUid, bandCandidate, source) {
  const local = commitBandCandidate(participantUid, bandCandidate);
  return _send(participantUid, local, {
    ParticipantId: participantUid, Action: "choose", BandCandidate: bandCandidate, Source: source,
  });
}

/** Record that no band is chosen: here and on the server. Resolves to `{ status }`. */
export async function recordClearedBand(participantUid) {
  clearBandCandidate(participantUid);
  try {
    const res = await SessionController.query(ENDPOINT, { ParticipantId: participantUid, Action: "clear" });
    const data = (res && res.data) || {};
    return { status: data.saved ? _status("server")
      : _status("browser", { reason: data.reason || "the server did not record the clear" }) };
  } catch (err) {
    return { status: _status("browser", { reason: _why(err) }) };
  }
}

/** The one line under the page title saying where the chosen band is held; null for nothing to say. */
export function chosenBandRecordText(status, hasBand) {
  if (!status) return null;
  if (status.where === "browser") {
    return hasBand
      ? `The chosen band is held in this browser only; the server did not record it (${status.reason}).`
      : `The server's record of the chosen band could not be read (${status.reason}).`;
  }
  if (!hasBand) return null;
  const when = status.recordedUtc ? new Date(status.recordedUtc).toLocaleString() : null;
  const by = status.chosenBy ? `by ${status.chosenBy}` : null;
  if (status.source === "browser_storage") {
    return "The chosen band is recorded on the server: carried over from this browser's own copy"
      + `${when ? ` on ${when}` : ""}${by ? `, ${by}` : ""}.`;
  }
  const detail = [when, by].filter(Boolean).join(", ");
  return `The chosen band is recorded on the server${detail ? ` (${detail})` : ""}.`;
}
