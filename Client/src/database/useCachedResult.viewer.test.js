import React from "react";
import {act,render} from "@testing-library/react";
import {SessionController} from "database/session-control";
import {useCachedResult} from "./useCachedResult";
import {invalidateAll,getResult,settingsKey} from "./resultCache";
jest.mock("database/session-control",()=>({SessionController:{query:jest.fn(),getUser:jest.fn()}}));
function Probe({fetcher,onResult}) {
 const result=useCachedResult({moduleKey:"test-viewer",uid:"p",settings:{},fetcher});
 onResult(result);return null;
}
test("a previous account's pending analysis cannot populate the next account's result cache",async()=>{
 invalidateAll();
 SessionController.getUser.mockReturnValue({Email:"synthetic-owner"});
 SessionController.query.mockResolvedValue({data:{boot_token:"test-viewer"}});
 let finish;const fetcher=jest.fn(()=>new Promise(resolve=>{finish=resolve;}));let current;
 render(<Probe fetcher={fetcher} onResult={result=>{current=result;}}/>);
 await act(async()=>{await Promise.resolve();await Promise.resolve();});
 expect(fetcher).toHaveBeenCalledTimes(1);
 SessionController.getUser.mockReturnValue({Email:"synthetic-viewer",ReadOnly:true});
 await act(async()=>{finish({private:"old account"});await Promise.resolve();});
 expect(getResult("test-viewer","p",settingsKey({}))).toBeNull();
 expect(current.data).toBeFalsy();
});
