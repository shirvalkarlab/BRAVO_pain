/**
 * The chosen band is recorded on the server (the PI's ruling 8, decision 233).
 *
 * Until 2026-09-23 the band chosen on this page lived only in browser storage: another browser, or
 * a cleared one, opened on "No band has been committed". The server now holds an append-only
 * record (`/api/queryClosedLoopChosenBand`), and browser storage is a mirror of it. These tests pin
 * the four things that make that true: the server's answer wins when it can be asked; a band held
 * only in this browser from before is sent to the server once, keeping its own time; a clear
 * recorded on the server clears this browser too; and when the server cannot be asked, or a save
 * does not land, the page is told so rather than shown the browser copy as if it were the record.
 */
import { SessionController } from "database/session-control";
import {
  loadBandCandidate, commitBandCandidate, syncChosenBand, recordChosenBand, recordClearedBand,
  chosenBandRecordText,
} from "./bandCandidateStore";

jest.mock("database/session-control", () => ({ SessionController: { query: jest.fn() } }));

const UID = "2e3c75c00d7f4f37b53a048d195f11da";
const BAND = { schema_version: "bandcandidate_v1", contact: "ONE_THREE_LEFT", center_freq_hz: 24.5 };
const serverRecord = (band = BAND) => ({
  schema: "bandcandidate_envelope_v1", participant_uid: UID, committed_at: "2026-09-23T08:00:00.000Z",
  band_candidate: band, action: "chosen", source: "grid", chosen_by: "clinician@example.org",
  recorded_utc: "2026-09-23T08:00:00.000Z", saved_on_server: true,
});
const reply = (data) => Promise.resolve({ data });

beforeEach(() => {
  window.localStorage.clear();
  SessionController.query.mockReset();
});

test("the server's band wins and is mirrored into this browser", async () => {
  commitBandCandidate(UID, { ...BAND, center_freq_hz: 12.5 });        // a stale local copy
  SessionController.query.mockImplementation(() => reply({
    available: true, record: serverRecord(), history: [serverRecord()] }));
  const out = await syncChosenBand(UID);
  expect(SessionController.query).toHaveBeenCalledWith("/api/queryClosedLoopChosenBand",
    { ParticipantId: UID, Action: "read" });
  expect(out.envelope.band_candidate.center_freq_hz).toBe(24.5);
  expect(out.status.where).toBe("server");
  expect(out.status.chosenBy).toBe("clinician@example.org");
  expect(loadBandCandidate(UID).band_candidate.center_freq_hz).toBe(24.5);
});

test("a band held only in this browser is sent to the server once, keeping its own time", async () => {
  const local = commitBandCandidate(UID, BAND);
  SessionController.query
    .mockImplementationOnce(() => reply({ available: true, record: null, history: [] }))
    .mockImplementationOnce((url, body) => reply({ saved: true, reason: null,
      record: { ...serverRecord(), source: "browser_storage", committed_at: body.CommittedAt } }));
  const out = await syncChosenBand(UID);
  const [, body] = SessionController.query.mock.calls[1];
  expect(body).toEqual({ ParticipantId: UID, Action: "choose", BandCandidate: BAND,
    Source: "browser_storage", CommittedAt: local.committed_at });
  expect(out.status.where).toBe("server");
  expect(out.envelope.committed_at).toBe(local.committed_at);
});

test("a clear recorded on the server clears this browser too", async () => {
  commitBandCandidate(UID, BAND);
  SessionController.query.mockImplementation(() => reply({ available: true, record: null,
    history: [{ action: "cleared" }, serverRecord()] }));
  const out = await syncChosenBand(UID);
  expect(out.envelope).toBeNull();
  expect(loadBandCandidate(UID)).toBeNull();
  expect(SessionController.query).toHaveBeenCalledTimes(1);          // nothing pushed back
});

test("when the server cannot be asked, the browser copy is shown AND labelled as such", async () => {
  commitBandCandidate(UID, BAND);
  SessionController.query.mockImplementation(() => Promise.reject(new Error("network down")));
  const out = await syncChosenBand(UID);
  expect(out.envelope.band_candidate).toEqual(BAND);
  expect(out.status.where).toBe("browser");
  expect(out.status.reason).toMatch(/network down/);

  SessionController.query.mockImplementation(() => reply({ available: false, record: null,
    reason: "no database is reachable from the server" }));
  const out2 = await syncChosenBand(UID);
  expect(out2.status.where).toBe("browser");
  expect(out2.status.reason).toMatch(/no database/);
});

test("a choice is written here and on the server, and a refused save says why", async () => {
  SessionController.query.mockImplementation(() => reply({ saved: true, reason: null,
    record: serverRecord() }));
  const ok = await recordChosenBand(UID, BAND, "grid");
  const [, body] = SessionController.query.mock.calls[0];
  expect(body).toEqual({ ParticipantId: UID, Action: "choose", BandCandidate: BAND, Source: "grid" });
  expect(ok.status.where).toBe("server");
  expect(loadBandCandidate(UID).band_candidate).toEqual(BAND);

  SessionController.query.mockImplementation(() => reply({ saved: false,
    reason: "the band candidate has no band centre", record: null }));
  const refused = await recordChosenBand(UID, BAND, "upload");
  expect(refused.status.where).toBe("browser");
  expect(refused.status.reason).toMatch(/no band centre/);
  expect(loadBandCandidate(UID).band_candidate).toEqual(BAND);      // still usable here
});

test("a clear is recorded on the server and empties this browser", async () => {
  commitBandCandidate(UID, BAND);
  SessionController.query.mockImplementation(() => reply({ saved: true, reason: null, record: null }));
  const out = await recordClearedBand(UID);
  expect(SessionController.query).toHaveBeenCalledWith("/api/queryClosedLoopChosenBand",
    { ParticipantId: UID, Action: "clear" });
  expect(out.status.saved).toBe(true);
  expect(loadBandCandidate(UID)).toBeNull();
});

test("the line under the page title says where the band is held", () => {
  const onServer = { where: "server", chosenBy: "clinician@example.org", recordedUtc: "2026-09-23T08:00:00.000Z" };
  expect(chosenBandRecordText(onServer, true)).toMatch(/^The chosen band is recorded on the server \(.*, by clinician@example\.org\)\.$/);
  expect(chosenBandRecordText(onServer, false)).toBeNull();
  expect(chosenBandRecordText({ where: "browser", reason: "network down" }, true))
    .toBe("The chosen band is held in this browser only; the server did not record it (network down).");
  expect(chosenBandRecordText({ where: "browser", reason: "network down" }, false))
    .toMatch(/could not be read \(network down\)/);
  expect(chosenBandRecordText(null, true)).toBeNull();
});

test("a band carried over from browser storage does not name the carrier as the chooser", () => {
  const carried = { where: "server", source: "browser_storage", chosenBy: "demo@bravo.local",
    recordedUtc: "2026-09-23T08:19:39.000Z" };
  const text = chosenBandRecordText(carried, true);
  expect(text).toMatch(/carried over from this browser's own copy/);
  expect(text).toMatch(/by demo@bravo\.local/);
  expect(text).not.toMatch(/recorded on the server \(.*by demo/);
});
