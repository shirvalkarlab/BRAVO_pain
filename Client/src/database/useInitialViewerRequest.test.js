import React, {useState} from "react";
import {render, screen} from "@testing-library/react";
import {useInitialViewerRequest} from "./useInitialViewerRequest";
function Probe({readOnly, participant="p", saved=null, metric="nrs", created}) {
 const [request,setRequest]=useState(saved);
 useInitialViewerRequest(readOnly,participant,request,value=>{created(value);setRequest(value);},()=>({LabelMetric:metric}));
 return <output>{JSON.stringify(request)}</output>;
}
test("fresh viewer loads the normal saved read once and later filters do not trigger a rebuild",()=>{
 const created=jest.fn(); const view=render(<Probe readOnly created={created}/>);
 expect(screen.getByRole("status").textContent).toBe('{"LabelMetric":"nrs"}');
 expect(created).toHaveBeenCalledTimes(1);
 view.rerender(<Probe readOnly created={created} metric="mpq"/>);
 expect(created).toHaveBeenCalledTimes(1);
 expect(screen.getByRole("status").textContent).not.toMatch(/mpq/);
});
test.each([{readOnly:false},{readOnly:true,participant:""},{readOnly:true,saved:{LabelMetric:"mpq"}}])("respects owner, absent participant, or existing request %j",props=>{
 const created=jest.fn();render(<Probe {...props} created={created}/>);expect(created).not.toHaveBeenCalled();
});
