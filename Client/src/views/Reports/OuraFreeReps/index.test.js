import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import OuraFreeReps from './index';

const mockDispatch=jest.fn();
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
jest.mock('react-router-dom',()=>({useParams:()=>({participant_uid:'synthetic'}),Link:require('react').forwardRef(({to,children,...props},ref)=><a href={to} ref={ref} {...props}>{children}</a>)}));
jest.mock('context.js',()=>({usePlatformContext:()=>[{},mockDispatch],setContextState:jest.fn()}));
jest.mock('layouts/DatabaseLayout',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDBox',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,role})=><span role={role}>{children}</span>}));
jest.mock('./Chart',()=>({__esModule:true,default:props=><pre data-chart={props.yTitle}>{JSON.stringify(props)}</pre>}));

const day=(day,value)=>({day,value});
const payload={metrics:[
  {key:'readiness',label:'Readiness',unit:'score',points:[day('2026-01-01',8),day('2026-05-25',1),day('2026-05-27',2),day('2026-05-31',3)]},
  {key:'hrv',label:'HRV',unit:'ms',points:[day('2026-05-25',6),day('2026-05-27',4),day('2026-05-31',2)]},
],sleep:[
  {id:'s1',day:'2026-05-31',start:1780210800,duration_hours:6},
  {id:'s2',day:'2026-05-30',start:1780124400,duration_hours:7},
]};
const sleep={start:1780210800,end:1780232400,duration_hours:6,efficiency:90,hr:60,hrv:30,
  stages:[{stage:'Deep',start:1780210800,end:1780211100}],heart_rate:[{time:1780210800,value:60},{time:1780211100,value:61},{time:1780218000,value:58}],hrv_series:[{time:1780210800,value:30}]};
let root,element;
const text=()=>element.textContent;
const chart=()=>JSON.parse(element.querySelector('[data-chart]').textContent);
async function click(label){
  const node=[...element.querySelectorAll('button,a')].find(n=>n.textContent===label);
  expect(node).toBeDefined();await act(async()=>node.dispatchEvent(new MouseEvent('click',{bubbles:true})));
}
async function select(label,option){
  const node=[...element.querySelectorAll('[role="button"],[role="combobox"]')].find(n=>{
    const labelIds=(n.getAttribute('aria-labelledby')||'').split(' ');
    return labelIds.some(id=>document.getElementById(id)?.textContent===label);
  });
  expect(node).toBeDefined();
  await act(async()=>node.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0})));
  const item=[...document.querySelectorAll('[role="option"]')].find(n=>n.textContent.includes(option));
  expect(item).toBeDefined();await act(async()=>item.dispatchEvent(new MouseEvent('click',{bubbles:true})));
}
async function input(label,value){
  const input=[...element.querySelectorAll('input')].find(n=>document.querySelector(`label[for="${n.id}"]`)?.textContent===label);
  expect(input).toBeDefined();
  await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));});
}
async function mount(){await act(async()=>root.render(<OuraFreeReps/>));}
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);
  SessionController.query.mockReset();SessionController.query.mockImplementation((_,body)=>Promise.resolve({data:body.SleepId?{sleep}:payload}));
});
afterEach(()=>{act(()=>root.unmount());element.remove();});

test('overview defaults to ninety days and history/date buttons really change included observations',async()=>{
  await mount();expect(text()).toContain('3 observed days');expect(text()).not.toContain('4 observed days');
  expect(element.querySelector('a[href*="multimodal"]').getAttribute('href')).toBe('/reports/multimodal-timeline-report/synthetic?source=oura');
  await click('All history');expect(text()).toContain('4 observed days');
  await click('Latest 90 days');expect(text()).not.toContain('4 observed days');
  await input('From Oura day','2026-06-01');expect(text()).toContain('Choose a start date on or before the end date');
  await input('Through Oura day','2026-06-02');expect(text()).toContain('No observations in selected range');
});

test('trend entry, metric selector, interval means and missing-date gaps are wired to displayed traces',async()=>{
  await mount();await click('Explore trend');
  expect(chart().traces[0].y).toEqual([1,null,2,null,3]);expect(chart().traces[0].connectgaps).toBe(false);
  await select('Display interval','Weekly mean');
  expect(chart().traces[0].y).toEqual([2]);expect(chart().traces[0].customdata).toEqual([3]);
  expect(chart().traces[0].mode).toBe('markers');
  await select('Trend metric','HRV');expect(chart().traces[0].y).toEqual([4]);
  await select('Display interval','Monthly mean');expect(chart().traces[0].x).toEqual(['2026-05-01']);
});

test('compare controls use paired observed dates and show insufficient observations rather than inventing correlation',async()=>{
  await mount();await click('Compare');expect(text()).toContain('Pearson r: -1 · 3 paired days');
  expect(chart().traces[0].x).toEqual([1,2,3]);expect(chart().traces[0].y).toEqual([6,4,2]);
  await select('X metric','HRV');await select('Y metric','Readiness');
  expect(chart().traces[0].x).toEqual([6,4,2]);expect(chart().traces[0].y).toEqual([1,2,3]);
  await input('From Oura day','2026-05-30');expect(text()).toContain('Pearson r: Unavailable · 1 paired days');
  expect(text()).toContain('at least three paired days');
});

test('sleep tab lazily queries chosen session, draws detail and excludes sessions outside selected dates',async()=>{
  await mount();expect(SessionController.query).toHaveBeenCalledTimes(1);
  await click('Sleep');expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryOuraFreeReps',{ParticipantId:'synthetic',SleepId:'s1'});
  expect(text()).toContain('Mean HR: 60 bpm');expect(element.querySelector('[role="img"]')).not.toBeNull();
  expect(element.querySelectorAll('[data-chart]')).toHaveLength(2);
  expect(chart().xTitle).toBe('Hours since session start');
  expect(chart().traces[0].x).toEqual([0,1/12,2]);
  expect(chart().traces[0].mode).toBe('markers');
  await select('Sleep session (Pacific time)','2026-05-30');
  expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryOuraFreeReps',{ParticipantId:'synthetic',SleepId:'s2'});
  await input('From Oura day','2026-05-01');await input('Through Oura day','2026-05-02');
  expect(text()).toContain('No eligible sleep sessions in this date range');
});

test('permission failure offers working refresh and empty dataset has clear state',async()=>{
  SessionController.query.mockRejectedValueOnce({response:{status:403}});
  await mount();expect(text()).toContain('You do not have access');
  SessionController.query.mockResolvedValue({data:{metrics:[],sleep:[]}});
  await click('Refresh view');expect(text()).toContain('No eligible Oura measurements');expect(text()).not.toContain('You do not have access');
});
