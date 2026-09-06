import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import OuraTimeline from './OuraTimeline';
import {OURA_DEFAULTS} from './ouraData';
jest.mock('context',()=>({usePlatformContext:()=>[{}]}));
jest.mock('database/resultCache',()=>({cacheScope:()=> 'account-a'}));
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,role,variant})=>variant==='h4'?<h4>{children}</h4>:<span role={role}>{children}</span>}));
jest.mock('./OuraChart',()=>({__esModule:true,default:props=><pre data-oura={props.metric.key}>{JSON.stringify(props)}</pre>}));
const labels=['Steps','Heart rate','HRV','Total calories','Sleep duration','Total sleep time'];
const units=['steps','bpm','ms','kcal','h','h'];
const point=(day,value)=>({day,value,time:Date.parse(`${day}T19:00:00Z`)/1000});
const payload={metrics:[...['steps','heart_rate','hrv','total_calories','sleep_duration','sleep_total'], 'sleep_efficiency','readiness'].map((key,i)=>({key,label:labels[i]||key,unit:units[i]||'%',resolution:i===1||i===2?'sample':'day',points:i===7?[]:[point('2025-07-01',10+i),point('2026-08-07',20+i),point('2026-09-03',30+i)]}))};
const phases=[{key:'pre',label:'Pre-trial',color:'#123456',start:Date.parse('2025-01-01T20:00:00Z')/1000},{key:'stage1',label:'Stage 1',color:'#234567',start:Date.parse('2026-01-01T20:00:00Z')/1000},{key:'stage2',label:'Stage 2',color:'#345678',start:Date.parse('2026-08-15T20:00:00Z')/1000},{key:'future',label:'Future stage',color:'#456789',start:Date.parse('2027-01-01T20:00:00Z')/1000}];
let root,element;
const charts=()=>[...element.querySelectorAll('[data-oura]')].map(node=>JSON.parse(node.textContent));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const render=props=>act(async()=>root.render(<OuraTimeline participant="p1" phases={phases} {...props}/>));
async function click(label){const node=[...element.querySelectorAll('button')].find(n=>n.textContent===label);expect(node).toBeDefined();await act(async()=>node.click());}
async function input(label,value){const node=[...element.querySelectorAll('input')].find(n=>document.querySelector(`label[for="${n.id}"]`)?.textContent===label);expect(node).toBeDefined();await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new Event('input',{bubbles:true}));});}
async function toggle(label){const node=[...element.querySelectorAll('label')].find(n=>n.textContent===label)?.querySelector('input[type="checkbox"]');expect(node).toBeDefined();await act(async()=>node.click());}
async function openOptions(){const node=element.querySelector('input[role="combobox"]');await act(async()=>node.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0})));}
async function option(label){const node=[...document.querySelectorAll('[role="option"]')].find(n=>n.textContent.startsWith(`${label} ·`));expect(node).toBeDefined();await act(async()=>node.click());}
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);SessionController.query.mockReset();SessionController.query.mockResolvedValue({data:payload});jest.spyOn(Date,'now').mockReturnValue(Date.parse('2026-09-04T06:00:00Z'));});
afterEach(()=>{act(()=>root.unmount());element.remove();jest.restoreAllMocks();});

test('new Oura view uses its own endpoint and ordered approved metrics, units and full history through Pacific today',async()=>{
  await render();expect(SessionController.query).toHaveBeenCalledWith('/api/queryOuraTimeline',{ParticipantId:'p1'});
  expect(SessionController.query.mock.calls.some(([url])=>/FreeReps/i.test(url))).toBe(false);
  expect(charts().map(chart=>chart.metric.key)).toEqual(OURA_DEFAULTS);
  expect(charts().every(chart=>chart.range.start==='2025-07-01'&&chart.range.end==='2026-09-03'&&chart.markers&&chart.smooth)).toBe(true);
  expect(element.textContent).toContain('kcal');expect(element.textContent).toContain('bpm');
  expect(charts()[0].phases.map(phase=>phase.key)).toEqual(['pre','stage1','stage2']);
});

test('metric selector adds/removes optional metrics, disables unavailable choices and restores defaults',async()=>{
  await render();await openOptions();
  const unavailable=[...document.querySelectorAll('[role="option"]')].find(node=>node.textContent.startsWith('readiness ·'));
  expect(unavailable.getAttribute('aria-disabled')).toBe('true');
  await option('sleep_efficiency');expect(charts().at(-1).metric.key).toBe('sleep_efficiency');
  await option('Steps');expect(charts().some(chart=>chart.metric.key==='steps')).toBe(false);
  await click('Default Oura metrics');expect(charts().map(chart=>chart.metric.key)).toEqual(OURA_DEFAULTS);
  const clear=element.querySelector('button[title="Clear"]');await act(async()=>clear.click());expect(charts()).toEqual([]);expect(element.textContent).toContain('Select an Oura metric');
});

test('date controls update all charts, reject invalid/future dates and restore full history',async()=>{
  await render();await input('From','2026-08-01');expect(charts().every(chart=>chart.range.start==='2026-08-01')).toBe(true);
  await input('Through','2026-08-20');expect(charts().every(chart=>chart.range.end==='2026-08-20')).toBe(true);
  await input('From','2026-08-21');expect(charts()).toEqual([]);expect(element.textContent).toContain('Choose valid dates');
  await input('From','');expect(charts()).toEqual([]);await click('Full Oura history');expect(charts()).toHaveLength(6);
  await input('Through','2026-09-04');expect(charts()).toEqual([]);expect(element.textContent).toContain('no later than today');
  await input('Through','');expect(charts()).toEqual([]);await click('Full Oura history');expect(charts()[0].range.end).toBe('2026-09-03');
  await input('From','2026-08-10');await input('Through','2026-08-12');expect(charts()).toEqual([]);expect(element.textContent).toContain('No eligible observations for this metric');
});

test('past 28 days and display controls preserve the date window and only applicable study phases',async()=>{
  await render();await toggle('Past 28 days');expect(charts().every(chart=>chart.range.start==='2026-08-07'&&chart.range.end==='2026-09-03')).toBe(true);
  expect(charts()[0].phases.map(phase=>phase.key)).toEqual(['stage1','stage2']);
  expect([...element.querySelectorAll('input[type="checkbox"]')]).toHaveLength(3);
  await toggle('Stimulation context');expect(charts().every(chart=>chart.transitions.length===0)).toBe(true);
  expect(charts()[0].phases).toHaveLength(2);
  await toggle('5-point rolling median');expect(charts().every(chart=>!chart.smooth)).toBe(true);
  await toggle('Stimulation context');
  await toggle('Past 28 days');expect(charts()[0].range.start).toBe('2025-07-01');
});

test('loading blocks duplicate refresh, failure has recovery, and empty or missing payload metrics do not fabricate observations',async()=>{
  const pending=deferred();SessionController.query.mockReturnValueOnce(pending.promise);await render();
  expect(element.querySelector('[role="status"]').textContent).toContain('Loading Oura');
  expect([...element.querySelectorAll('button')].find(button=>button.textContent==='Refresh Oura view').disabled).toBe(true);
  await act(async()=>pending.reject({response:{status:403}}));expect(element.textContent).toContain('You do not have access');expect(charts()).toEqual([]);
  SessionController.query.mockResolvedValue({data:{metrics:payload.metrics.map(metric=>({...metric,points:[]}))}});
  await click('Refresh Oura view');expect(element.textContent).toContain('No eligible Oura observations');expect(charts()).toEqual([]);
  SessionController.query.mockResolvedValue({data:{}});await click('Refresh Oura view');expect(element.textContent).toContain('Select an Oura metric');expect(charts()).toEqual([]);
});

test('Oura uses reviewed home records, limits dense overlays and selects complete settings independently of clinical dates',async()=>{
  const transitions=Array.from({length:13},(_,i)=>({id:`r${i}`,time:Date.parse(`2026-08-${String(i+1).padStart(2,'0')}T18:00:00Z`)/1000,label:`Home ${i}`,settings:{group:[],left:[],right:[]}}));
  await render({homeTransitions:transitions,unknownIntervals:[{start:transitions[0].time,end:null,reason:'No evidence'}]});
  expect(element.textContent).toContain('Stimulation settings');expect(element.textContent).toContain('13 records fall');
  expect(charts().every(chart=>chart.transitions.length===1&&chart.transitions[0].id==='r12')).toBe(true);
  expect(charts().every(chart=>chart.homeTransitions.length===13&&chart.unknownIntervals.length===1)).toBe(true);
  await input('Through','2026-08-12');expect(charts().every(chart=>chart.transitions.length===12)).toBe(true);
  await toggle('Stimulation context');expect(element.textContent).not.toContain('Stimulation settings');
  expect(charts().every(chart=>chart.transitions.length===0&&chart.homeTransitions.length===13)).toBe(true);
});
