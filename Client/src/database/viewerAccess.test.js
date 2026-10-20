import axios from "axios";
import { SessionController } from "./session-control";
import { accountScope, isReadOnlyUser, viewerRouteAllowed } from "./viewerAccess";
import { putResult, getResult, settingsKey, invalidateAll } from "./resultCache";
jest.mock("axios", () => ({ post: jest.fn(), get: jest.fn() }));
const viewer = { Email: "shared-viewer", InstituteId: "synthetic-lab", ReadOnly: true };
beforeEach(() => {
  SessionController.setUser({});
  localStorage.clear(); invalidateAll();
  axios.post.mockResolvedValue({ data: {} });
});
test("only an explicit server boolean enables the viewer UI", () => {
  for (const user of [undefined, null, {}, {ReadOnly: false}, {ReadOnly: "true"}]) expect(isReadOnlyUser(user)).toBe(false);
  expect(isReadOnlyUser(viewer)).toBe(true);
  expect(accountScope(null)).not.toBe(accountScope(viewer));
});
test.each(["/study-management", "/form-manager", "/form-manager/id", "/survey/id", "/analysis-builder/id"])("viewer excludes write-oriented route %s", path => expect(viewerRouteAllowed(path)).toBe(false));
test.each([undefined, "/database", "/reports/biomarkers/id", "/reports/closed-loop/id", "/reports/redcap-timeline/id", "/source-files/id", "/reports/therapy-history/id"])("viewer retains read route %s", path => expect(viewerRouteAllowed(path)).toBe(true));
test("viewer preferences stay local and owner preferences still save", () => {
  SessionController.setUser(viewer);
  for (const [key, value] of [["language", "en"], ["darkMode", true], ["miniSidenav", true]]) SessionController.setSession(key,value,true);
  expect(axios.post).not.toHaveBeenCalled();
  expect(JSON.parse(localStorage.getItem("sessionContext")).darkMode).toBe(true);
  SessionController.setUser({...viewer, ReadOnly:false});
  SessionController.setSession("darkMode", false, true);
  expect(axios.post).toHaveBeenCalledWith(expect.stringContaining("/api/updateSessions"),{darkMode:false},expect.anything());
});
test("session refresh preserves viewer browser choices without saving the shared account", async () => {
  SessionController.setSession("darkMode",true,false);
  axios.post.mockResolvedValueOnce({data:{user:viewer,session:{language:"en",darkMode:false,miniSidenav:false}}});
  const session=await SessionController.syncSession();
  expect(session.darkMode).toBe(true); expect(SessionController.isReadOnly()).toBe(true);
  expect(axios.post).toHaveBeenCalledTimes(1);
});
test("account and access-scope changes clear cached results; ordinary profile refresh retains them", () => {
  const key=settingsKey({});
  SessionController.setUser(viewer);
  putResult("test","participant",key,{secret:"synthetic"});
  SessionController.setUser({...viewer,Name:"Viewer"});
  expect(getResult("test","participant",key)).toBeTruthy();
  SessionController.setUser({...viewer,StudyId:"different"});
  expect(getResult("test","participant",key)).toBeNull();
  putResult("test","participant",key,{secret:"synthetic"});
  SessionController.nullifyUser();
  expect(getResult("test","participant",key)).toBeNull();
  expect(localStorage.getItem("sessionContext")).toBeNull();
});
