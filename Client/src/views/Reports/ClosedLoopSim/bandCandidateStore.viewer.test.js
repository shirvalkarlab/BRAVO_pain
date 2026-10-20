import { SessionController } from "database/session-control";
import {commitBandCandidate, syncChosenBand, recordChosenBand, recordClearedBand, loadBandCandidate} from "./bandCandidateStore";
jest.mock("database/session-control",()=>({SessionController:{query:jest.fn(),isReadOnly:jest.fn(),getUser:()=>({Email:"synthetic-viewer"})}}));
const band={contact:"LEFT_0_2",center_freq_hz:20};
beforeEach(()=>{localStorage.clear();SessionController.isReadOnly.mockReturnValue(true);});
test("viewer never migrates a browser-only band to the server",async()=>{
  commitBandCandidate("p",band);
  SessionController.query.mockResolvedValue({data:{available:true,record:null,history:[]}});
  const result=await syncChosenBand("p");
  expect(result.envelope).toBeNull();
  expect(SessionController.query).toHaveBeenCalledTimes(1);
  expect(SessionController.query.mock.calls[0][1].Action).toBe("read");
});
test("viewer never falls back to the owner's browser copy on a failed read",async()=>{
  SessionController.isReadOnly.mockReturnValue(false);commitBandCandidate("p",band);
  SessionController.isReadOnly.mockReturnValue(true);expect(loadBandCandidate("p")).toBeNull();
  SessionController.query.mockRejectedValue(new Error("offline"));
  expect((await syncChosenBand("p")).envelope).toBeNull();
});
test("viewer can mirror authoritative server band without changing the owner browser copy",async()=>{
  SessionController.isReadOnly.mockReturnValue(false);commitBandCandidate("p",band);
  SessionController.isReadOnly.mockReturnValue(true);
  const record={band_candidate:{...band,center_freq_hz:25}};
  SessionController.query.mockResolvedValue({data:{available:true,record,history:[record]}});
  expect((await syncChosenBand("p")).envelope.band_candidate.center_freq_hz).toBe(25);
  SessionController.isReadOnly.mockReturnValue(false);expect(loadBandCandidate("p").band_candidate.center_freq_hz).toBe(20);
});
test("explicit viewer choose and clear reject without local or server writes",async()=>{
  await expect(recordChosenBand("p",band,"grid")).rejects.toThrow("read-only");
  await expect(recordClearedBand("p")).rejects.toThrow("read-only");
  expect(SessionController.query).not.toHaveBeenCalled();expect(localStorage.length).toBe(0);
});
