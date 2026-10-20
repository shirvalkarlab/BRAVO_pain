import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import {SYNC_COMPLETED_EVENT} from 'utils/syncEvents';
import MultimodalSummary from './MultimodalSummary';

jest.mock('context',()=>({usePlatformContext:()=>[{}]}));
jest.mock('./requestScope',()=>({cacheScope:()=> 'account-a'}));
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,role})=><div role={role}>{children}</div>}));
jest.mock('./MultimodalChart',()=>({__esModule:true,default:props=><pre data-chart={props.title}>{JSON.stringify(props.traces)}</pre>}));
jest.mock('./HomeNeuralChart',()=>({NeuralLegend:()=>null,NeuralSensingIntervals:()=>null}));
jest.mock('./StimulationContext',()=>({__esModule:true,default:()=>null}));
let root,element,storedRevision,storedValue;
const stamp=Date.parse('2026-10-01T19:00:00Z')/1000;
// Direct ReactDOM roots require act; this is not a Testing Library render.
// eslint-disable-next-line testing-library/no-unnecessary-act
const mount=async(redcap={})=>act(async()=>root.render(<MultimodalSummary participant="p1" redcap={redcap} revision={0}/>));
const traces=()=>JSON.parse(element.querySelector('[data-chart="Multimodal Summary Oura activity and sleep"]').textContent);
beforeEach(()=>{
 global.IS_REACT_ACT_ENVIRONMENT=true;jest.useFakeTimers();jest.setSystemTime(new Date('2026-10-19T12:00:00Z'));
 storedRevision='a'.repeat(64);storedValue=100;SessionController.query.mockReset();
 SessionController.query.mockImplementation((url,body)=>Promise.resolve({data:body.RequestType==='Revision'?{revision:storedRevision}:url==='/api/queryOuraTimeline'?{revision:storedRevision,metrics:[{key:'steps',points:[{day:'2026-10-01',time:stamp,value:storedValue}]}]}:{revision:storedRevision,windows:[],visit_days:[],message:'No reviewed neural window'}}));
 element=document.createElement('div');root=createRoot(element);
});
afterEach(()=>{act(()=>root.unmount());jest.useRealTimers();});

test('summary refreshes its actual independent hooks after manual and daily updates with one poll per mounted stream',async()=>{
 await mount();expect(SessionController.query).toHaveBeenCalledTimes(2);expect(traces().some(t=>t.y.includes(100))).toBe(true);
 storedValue=200;storedRevision='b'.repeat(64);
 await act(async()=>window.dispatchEvent(new CustomEvent(SYNC_COMPLETED_EVENT,{detail:{participantUid:'p1',scope:'account-a',state:'failed'}})));
 expect(SessionController.query).toHaveBeenCalledTimes(4);expect(traces().some(t=>t.y.includes(200))).toBe(true);
 await act(async()=>jest.advanceTimersByTime(60000));expect(SessionController.query).toHaveBeenCalledTimes(6);
 expect(SessionController.query.mock.calls.slice(-2).map(([url,body])=>[url,body.RequestType])).toEqual([['/api/queryOuraTimeline','Revision'],['/api/queryHomeNeuralTimeline','Revision']]);
 storedValue=300;storedRevision='c'.repeat(64);await act(async()=>jest.advanceTimersByTime(60000));
 expect(SessionController.query).toHaveBeenCalledTimes(10);expect(traces().some(t=>t.y.includes(300))).toBe(true);
 expect(SessionController.query.mock.calls.every(([url])=>url==='/api/queryOuraTimeline'||url==='/api/queryHomeNeuralTimeline')).toBe(true);
});


test('summary names missing standard MPQ explicitly and never plots the distinct legacy sum',async()=>{
 const legacy={key:'mpq_sum',label:'Legacy MPQ sum',range:[0,72],points:[{time:stamp,value:65,phase:'synthetic'}]};
 await mount({metrics:[legacy]});
 expect(element.textContent).toContain('Standard MPQ (0–45) observations are unavailable.');
 expect(element.textContent).not.toContain('Legacy MPQ sum');
 const standard={key:'mpq_standard_0_45',label:'Standard MPQ total',range:[0,45],points:[{time:stamp,value:31,phase:'synthetic'}]};
 await mount({metrics:[legacy,standard]});
 expect(element.textContent).not.toContain('Standard MPQ (0–45) observations are unavailable.');
 expect(element.textContent).toContain('Standard MPQ total (0–45)');
 expect(element.textContent).not.toContain('Legacy MPQ sum');
});
