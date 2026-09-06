import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import RedcapTimeline from './index';
import {DEFAULT_METRICS} from './data';

jest.mock('database/resultCache',()=>({cacheScope:()=> 'account-a'}));
const mockDispatch=jest.fn();
let mockParticipant='synthetic';
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
jest.mock('react-router-dom',()=>({useParams:()=>({participant_uid:mockParticipant})}));
jest.mock('context.js',()=>({usePlatformContext:()=>[{},mockDispatch],setContextState:jest.fn()}));
jest.mock('layouts/DatabaseLayout',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDBox',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,role,variant})=>variant==='h4'?<h4>{children}</h4>:<span role={role}>{children}</span>}));
jest.mock('./ComparisonChart',()=>({__esModule:true,default:props=><pre data-comparison={props.label}>{JSON.stringify(props.plot)}</pre>}));
jest.mock('./MultimodalSummary',()=>({__esModule:true,default:props=><pre data-summary-view>{JSON.stringify(props)}</pre>}));
jest.mock('./HomeNeuralData',()=>({__esModule:true,default:props=><pre data-home-neural-view>{JSON.stringify(props)}</pre>}));
jest.mock('./NeuralData',()=>({__esModule:true,default:props=><pre data-neural-view>{JSON.stringify(props)}</pre>}));
jest.mock('./OuraTimeline',()=>({__esModule:true,default:props=><pre data-oura-view>{JSON.stringify(props)}</pre>}));
jest.mock('./MetricChart',()=>({__esModule:true,default:props=><div><pre data-metric={props.metric.key}>{JSON.stringify(props)}</pre>{props.transitions.map(t=><button key={t.id} onClick={()=>props.onTransition(t.id)}>Select {props.metric.key} {t.id}</button>)}</div>}));

const labels=['Mood VAS','Overall NRS','Overall VAS','Left-leg VAS','Back VAS','MPQ sensory','MPQ affective','MPQ total (0–45)','Fiery','Tingly','Electrocuting'];
const additional=['pain_relief_vas','throbbing','shooting','stabbing','sharp','cramping','gnawing','hot_burning','aching','heavy','tender','splitting','tiring','sickening','fearful','cruel'];
const point=(day,value)=>({time:Date.parse(`${day}T12:00:00-08:00`)/1000,value,phase:'pre',source:'Reviewed',record:'synthetic'});
const payload={metrics:[...DEFAULT_METRICS,...additional].map((key,i)=>({key,label:labels[i]||`Optional ${key}`,range:i===1?[0,10]:i===7?[0,45]:[0,100],points:[point('2024-12-12',i),point('2025-07-16',i+1)]})),
  phases:[{key:'pre',label:'Pre-trial',color:'#123456',start:point('2024-12-12',0).time},{key:'stage1',label:'Stage 1',color:'#234567',start:point('2025-07-16',0).time}]};
let root,element;
const text=()=>element.textContent;
const charts=()=>[...element.querySelectorAll('[data-metric]')].map(n=>JSON.parse(n.textContent));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
async function click(label){const node=[...element.querySelectorAll('button')].find(n=>n.textContent===label);expect(node).toBeDefined();await act(async()=>node.dispatchEvent(new MouseEvent('click',{bubbles:true})));}
async function input(label,value){const node=[...element.querySelectorAll('input')].find(n=>document.querySelector(`label[for="${n.id}"]`)?.textContent===label);expect(node).toBeDefined();await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new Event('input',{bubbles:true}));});}
async function openOptions(){const node=element.querySelector('input[role="combobox"]');await act(async()=>node.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0})));}
async function option(label){const node=[...document.querySelectorAll('[role="option"]')].find(n=>n.textContent.startsWith(`${label} ·`));expect(node).toBeDefined();await act(async()=>node.dispatchEvent(new MouseEvent('click',{bubbles:true})));}
async function mount(redcap=true){await act(async()=>root.render(<RedcapTimeline/>));if(redcap && element.querySelector('[role="tab"]')) await click("REDCap");}
async function toggle(label){const node=[...element.querySelectorAll('label')].find(n=>n.textContent===label)?.querySelector('input[type="checkbox"]');expect(node).toBeDefined();await act(async()=>node.click());}
async function selectTransition(id){const selector=[...element.querySelectorAll('input[role="combobox"]')].find(n=>document.querySelector(`label[for="${n.id}"]`)?.textContent==='Home-program transition');expect(selector).toBeDefined();await act(async()=>{selector.focus();selector.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));});const item=[...document.querySelectorAll('[role="option"]')].find(n=>n.textContent.endsWith(`Changed ${id}`));expect(item).toBeDefined();await act(async()=>item.dispatchEvent(new MouseEvent('click',{bubbles:true})));}
const settings={group:[{label:'Active group',value:'Group B'},{label:'Mode',value:'Adaptive'}],left:[{label:'Amplitude',value:'1.5 mA'},{label:'Frequency',value:'130 Hz'}],right:[{label:'Pulse width',value:'60 µs'},{label:'Sensing band',value:'8–12 Hz'}]};
const transition=(id,day)=>({id,kind:'settings_observed',time:point(day,0).time,label:`Changed ${id}`,evidence:'Recorded snapshot; effective onset unknown',settings});
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockParticipant='synthetic';element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);SessionController.query.mockReset();SessionController.query.mockResolvedValue({data:payload});jest.spyOn(Date,'now').mockReturnValue(Date.parse('2026-09-04T06:00:00Z'));});
afterEach(()=>{act(()=>root.unmount());element.remove();jest.restoreAllMocks();});

test('starts with exactly the user eleven in order, pre-trial through Pacific today, and 16 selectable alternatives',async()=>{
  await mount();
  expect(text()).toContain('Aditya - All Data Streams');
  expect(charts().map(c=>c.metric.key)).toEqual(DEFAULT_METRICS);
  expect([...element.querySelectorAll('h4')].map(n=>n.textContent).filter(t=>t!=='Stimulation settings')).toEqual(labels);
  expect(charts().every(c=>c.range.start==='2024-12-12'&&c.range.end==='2026-09-03'&&c.smooth)).toBe(true);
  await openOptions();
  expect(document.querySelectorAll('[role="option"]')).toHaveLength(27);
  expect([...document.querySelectorAll('[role="option"]')].filter(n=>n.getAttribute('aria-selected')==='true')).toHaveLength(11);
  await option('Optional throbbing');
  expect(charts().map(c=>c.metric.key)).toEqual([...DEFAULT_METRICS,'throbbing']);
  await option('Mood VAS');expect(charts().map(c=>c.metric.key)).toEqual([...DEFAULT_METRICS.slice(1),'throbbing']);
  await click('Default metrics');expect(charts().map(c=>c.metric.key)).toEqual(DEFAULT_METRICS);
});

test('date controls filter observations, reject reversed and missing dates, show empty windows and reset all history',async()=>{
  await mount();await input('From','2025-01-01');
  expect(text()).toContain('1 observations');expect(charts()[0].range.start).toBe('2025-01-01');
  await input('From','2026-09-04');expect(text()).toContain('Choose valid dates');expect(charts()).toHaveLength(0);
  await input('From','2026-08-01');expect(text()).toContain('No reviewed observations for this metric');
  await input('From','');expect(text()).toContain('Choose valid dates');
  await click('Pre-trial to today');expect(charts()).toHaveLength(11);expect(charts()[0].range.start).toBe('2024-12-12');
  await input('Through','2025-01-01');expect(charts()[0].range.end).toBe('2025-01-01');expect(text()).toContain('1 observations');
  await input('Through','');expect(text()).toContain('Choose valid dates');
  await click('Pre-trial to today');await input('Through','2026-09-04');
  expect(text()).toContain('no later than today');expect(charts()).toHaveLength(0);
});

test('median switch changes every rendered plot and explanation while preserving chosen dates',async()=>{
  await mount();await input('From','2025-01-01');
  const toggle=element.querySelector('input[type="checkbox"]');
  await act(async()=>toggle.click());
  expect(charts().every(c=>!c.smooth)).toBe(true);expect(text()).not.toContain('The red line is a centered median');
  expect(charts()[0].range.start).toBe('2025-01-01');
  await act(async()=>toggle.click());expect(charts().every(c=>c.smooth)).toBe(true);
});

test('clear selection is explicit and metrics with no observations are disabled, not ghost features',async()=>{
  SessionController.query.mockResolvedValue({data:{...payload,metrics:payload.metrics.map(m=>m.key==='tingly'?{...m,points:[]}:m)}});
  await mount();await openOptions();
  const unavailable=[...document.querySelectorAll('[role="option"]')].find(n=>n.textContent.startsWith('Tingly ·'));
  expect(unavailable.getAttribute('aria-disabled')).toBe('true');
  const clear=element.querySelector('button[title="Clear"]');expect(clear).not.toBeNull();
  await act(async()=>clear.dispatchEvent(new MouseEvent('click',{bubbles:true})));
  expect(charts()).toHaveLength(0);expect(text()).toContain('Select a clinical metric above');
  await click('Default metrics');expect(charts()).toHaveLength(10);
});

test('loading prevents duplicate refresh, errors expose recovery, and empty data never fabricates charts',async()=>{
  const pending=deferred();SessionController.query.mockReturnValueOnce(pending.promise);
  await mount();expect(element.querySelector('[role="status"]').textContent).toContain('Loading reviewed');
  const refresh=[...element.querySelectorAll('button')].find(n=>n.textContent==='Refresh view');expect(refresh.disabled).toBe(true);
  await act(async()=>pending.reject({response:{status:403}}));
  expect(text()).toContain('You do not have access');expect(charts()).toHaveLength(0);
  SessionController.query.mockResolvedValue({data:{}});
  await click('Refresh view');await click('REDCap');expect(text()).not.toContain('You do not have access');expect(text()).toContain('Select a clinical metric');expect(charts()).toHaveLength(0);
});

test('participant navigation resets custom selection and dates, hides old data until the current response',async()=>{
  await mount();await input('From','2025-01-01');await openOptions();await option('Optional throbbing');
  const pending=deferred();SessionController.query.mockReturnValueOnce(pending.promise);
  mockParticipant='second';await mount();expect(charts()).toHaveLength(0);expect(text()).toContain('Loading reviewed');
  await act(async()=>pending.resolve({data:payload}));
  expect(element.querySelector('[data-summary-view]')).not.toBeNull();await click("REDCap");
  expect(charts().map(c=>c.metric.key)).toEqual(DEFAULT_METRICS);expect(charts()[0].range.start).toBe('2024-12-12');
  expect(SessionController.query).toHaveBeenLastCalledWith('/api/queryRedcapTimeline',{ParticipantId:'second'});
});

test('one past-28-day switch updates every selected chart and restores the full history when turned off',async()=>{
  SessionController.query.mockResolvedValue({data:{...payload,metrics:payload.metrics.map(m=>({...m,points:[...m.points,point('2026-08-07',3),point('2026-09-03',4)]}))}});
  await mount();await toggle('Past 28 days');
  expect(charts()).toHaveLength(11);expect(charts().every(c=>c.range.start==='2026-08-07'&&c.range.end==='2026-09-03')).toBe(true);
  await toggle('Past 28 days');expect(charts().every(c=>c.range.start==='2024-12-12'&&c.range.end==='2026-09-03')).toBe(true);
  await input('From','2026-08-07');await input('Through','2026-09-02');
  const recent=[...element.querySelectorAll('label')].find(n=>n.textContent==='Past 28 days').querySelector('input');expect(recent.checked).toBe(false);
  await toggle('Past 28 days');expect(charts().every(c=>c.range.end==='2026-09-03')).toBe(true);
});

test('visit-only dates render X context, context toggle removes them and unavailable visits are explained',async()=>{
  SessionController.query.mockResolvedValue({data:{...payload,visits:{available:true,metrics:{mood_vas:[point('2026-08-08',100)]}}}});
  await mount();await toggle('Past 28 days');
  expect(charts()).toHaveLength(1);expect(charts()[0].visits[0].value).toBe(100);expect(text()).toContain('0 observations + 1 visit-day surveys (X)');
  await toggle('Stimulation context');expect(charts()).toHaveLength(1);expect(charts()[0].showVisits).toBe(false);expect(charts()[0].visits).toHaveLength(1);expect(text()).not.toContain('Stimulation settings');
  await toggle('Stimulation context');expect(charts()).toHaveLength(1);
  SessionController.query.mockResolvedValue({data:{...payload,visits:{available:false,message:'Reviewed visit records are unavailable'}}});
  await click('Refresh view');expect(text()).toContain('Reviewed visit records are unavailable');
});

test('all recorded changes are passed to charts up to twelve, annotation selection shows exact settings',async()=>{
  const events=[transition('first','2025-01-01'),transition('second','2025-07-16')];
  SessionController.query.mockResolvedValue({data:{...payload,stimulation:{home_transitions:events}}});
  await mount();expect(charts().every(c=>c.transitions.length===2)).toBe(true);
  expect(text()).toContain('Changed second · complete settings');
  expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('false');
  await click('Select mood_vas second');
  expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
  await act(async()=>element.querySelector('.MuiAccordionSummary-root').click());
  expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('false');
  await click('Select mood_vas second');
  expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
  await click('Select mood_vas first');expect(text()).toContain('Changed first · complete settings');
  await selectTransition('second');expect(text()).toContain('Changed second · complete settings');
  await input('From','2025-02-01');expect(text()).toContain('Last record before this window:');
  expect(text()).toContain('This does not establish continuous delivery');expect(charts().every(c=>c.transitions.length===1&&c.transitions[0].id==='second')).toBe(true);
  await toggle('Stimulation context');expect(charts().every(c=>c.transitions.length===0)).toBe(true);
});

test('more than twelve changes displays an explicit readable cap and selection changes the single marked record',async()=>{
  const events=Array.from({length:13},(_,i)=>transition(`record-${i}`,`2025-01-${String(i+1).padStart(2,'0')}`));
  SessionController.query.mockResolvedValue({data:{...payload,stimulation:{home_transitions:events}}});
  await mount();expect(text()).toContain('13 records fall in this window');
  expect(text()).toContain('show all lines (up to 12)');expect(charts().every(c=>c.transitions.length===1&&c.transitions[0].id==='record-12')).toBe(true);
  await selectTransition('record-0');expect(charts().every(c=>c.transitions[0].id==='record-0')).toBe(true);
  await input('Through','2025-01-12');expect(charts().every(c=>c.transitions.length===12)).toBe(true);expect(text()).not.toContain('13 records fall');
});

test('only reviewed home transitions drive lines and all home context remains available when hidden or date-filtered',async()=>{
  const homes=[transition('earlier','2025-01-01'),transition('current','2026-08-10')];
  const raw=[...homes,transition('clinic-only','2026-08-20')];
  SessionController.query.mockResolvedValue({data:{...payload,metrics:payload.metrics.map(m=>({...m,points:[...m.points,point('2026-08-10',1)]})),stimulation:{home_transitions:homes,transitions:raw}}});
  await mount();expect(text()).not.toContain('Include device change logs');await toggle('Past 28 days');
  expect(charts()).toHaveLength(11);expect(charts().every(c=>c.transitions.length===1&&c.transitions[0].id==='current')).toBe(true);
  expect(charts().every(c=>c.homeTransitions.length===2)).toBe(true);
  await toggle('Stimulation context');expect(charts().every(c=>c.transitions.length===0&&c.homeTransitions.length===2)).toBe(true);
  SessionController.query.mockResolvedValue({data:{...payload,stimulation:{transitions:raw}}});
  await click('Refresh view');await click('Pre-trial to today');expect(charts().every(c=>c.homeTransitions.length===0)).toBe(true);
});

test('missing home evidence stays explicit independently of overlay visibility, with a notice only in overlapping dates',async()=>{
  const interval={start:point('2025-05-27',0).time,end:point('2025-05-28',0).time,reason:'Missing reviewed visit snapshot'};
  SessionController.query.mockResolvedValue({data:{...payload,stimulation:{home_transitions:[transition('known','2025-01-01')],home_unknown_intervals:[interval]}}});
  await mount();expect(text()).toContain('Home settings are not established for part of this period');
  expect(charts().every(chart=>chart.unknownIntervals.length===1)).toBe(true);
  await toggle('Stimulation context');expect(text()).toContain('Home settings are not established for part of this period');
  expect(charts().every(chart=>!chart.showVisits&&chart.unknownIntervals.length===1)).toBe(true);
  await input('From','2025-06-01');expect(text()).not.toContain('Home settings are not established for part of this period');
  expect(charts().every(chart=>chart.unknownIntervals.length===1)).toBe(true);
  await input('From','2026-10-01');expect(text()).not.toContain('Home settings are not established for part of this period');
});

test('internal report views share clinical metric selection while comparisons retain Stage 1 scope and timeline dates',async()=>{
  const comparisonMetrics=payload.metrics.map(metric=>({...metric,conditions:[],top:{}}));
  SessionController.query.mockResolvedValue({data:{...payload,comparisons:{stimulation:{available:true,metrics:comparisonMetrics},medications:{available:true,metrics:comparisonMetrics,episodes:[]}}}});
  await mount();await input('From','2025-01-01');await click('Stim Program Boxplots');
  expect(text()).toContain('Stage 1 onward');expect(charts()).toHaveLength(0);expect(element.querySelectorAll('input[type="date"]')).toHaveLength(0);
  expect([...element.querySelectorAll('h4')].map(node=>node.textContent)).toEqual(labels);
  await openOptions();await option('Optional throbbing');expect([...element.querySelectorAll('h4')].at(-1).textContent).toBe('Optional throbbing');
  await click('Default metrics');expect([...element.querySelectorAll('h4')]).toHaveLength(11);
  await click('Medications');expect(element.querySelector('h4').textContent).toBe('Medication timeline');
  await click('REDCap');expect(charts()[0].range.start).toBe('2025-01-01');
  await click('Stim Program Boxplots');mockParticipant='second';await mount();expect(charts()).toHaveLength(11);
});


test('Oura is a separate fourth REDCap tab with participant and study context, independent from clinical controls',async()=>{
  await mount();await input('From','2025-01-01');await openOptions();await option('Optional throbbing');
  await click('Oura');
  expect([...element.querySelectorAll('[role="tab"]')].map(tab=>tab.textContent)).toEqual(['Multimodal Summary','REDCap','Stim Program Boxplots','Stim Program Settings','Neural Data','Medications','Oura']);
  const oura=element.querySelector('[data-oura-view]');expect(oura).not.toBeNull();
  expect(JSON.parse(oura.textContent)).toEqual({participant:'synthetic',phases:payload.phases,homeTransitions:[],unknownIntervals:[]});
  expect(charts()).toEqual([]);expect(element.querySelector('input[role="combobox"]')).toBeNull();
  expect(element.textContent).not.toContain('Clinical metrics');expect(element.textContent).not.toContain('FreeReps');
  await click('REDCap');expect(element.querySelector('[data-oura-view]')).toBeNull();
  expect(charts()[0].range.start).toBe('2025-01-01');expect(charts().at(-1).metric.key).toBe('throbbing');
  await click('Oura');mockParticipant='second';await mount();expect(element.querySelector('[data-oura-view]')).toBeNull();
  await click('Oura');expect(JSON.parse(element.querySelector('[data-oura-view]').textContent).participant).toBe('second');
});

test('Stim Program Settings retains the reviewed settings view, followed by independent chronic Neural Data',async()=>{
  const homes=[transition('one','2025-01-01')],unknown=[{start:1,end:2,reason:'gap'}];
  SessionController.query.mockResolvedValue({data:{...payload,stimulation:{home_transitions:homes,home_unknown_intervals:unknown}}});
  await mount();expect(text()).toContain('Aditya - All Data Streams');await click('Stim Program Settings');
  const view=JSON.parse(element.querySelector('[data-neural-view]').textContent);
  expect(view).toEqual({participant:'synthetic',phases:payload.phases,homeTransitions:homes,unknownIntervals:unknown});
  expect(element.querySelector('input[role="combobox"]')).toBeNull();expect(text()).not.toContain('Clinical metrics');
  await click('Neural Data');expect(element.querySelector('[data-neural-view]')).toBeNull();
  expect(JSON.parse(element.querySelector('[data-home-neural-view]').textContent)).toEqual({participant:'synthetic'});
  expect(element.querySelector('input[role="combobox"]')).toBeNull();
  await click('REDCap');expect(element.querySelector('[data-home-neural-view]')).toBeNull();
});


test('Multimodal Summary is inside All Data Streams, has independent controls, refreshes source revision and preserves specialized tabs',async()=>{
 await mount();await input('From','2025-01-01');await click('Multimodal Summary');
 expect(element.querySelector('input[role="combobox"]')).toBeNull();expect(charts()).toHaveLength(0);
 let summary=JSON.parse(element.querySelector('[data-summary-view]').textContent);expect(summary).toMatchObject({participant:'synthetic',redcap:payload,revision:0});
 await click('Refresh view');summary=JSON.parse(element.querySelector('[data-summary-view]').textContent);expect(summary.revision).toBe(1);
 await click('Neural Data');expect(element.querySelector('[data-summary-view]')).toBeNull();expect(element.querySelector('[data-home-neural-view]')).not.toBeNull();
 await click('REDCap');expect(charts()[0].range.start).toBe('2025-01-01');
 await click('Multimodal Summary');mockParticipant='second';await mount();expect(element.querySelector('[data-summary-view]')).toBeNull();
 await click('Multimodal Summary');expect(JSON.parse(element.querySelector('[data-summary-view]').textContent).participant).toBe('second');
});

 test('summary is the first and initially selected tab, including a newly selected participant',async()=>{
 await mount(false);let tabs=[...element.querySelectorAll('[role="tab"]')];expect(tabs[0].textContent).toBe('Multimodal Summary');expect(tabs[0].getAttribute('aria-selected')).toBe('true');expect(element.querySelector('[data-summary-view]')).not.toBeNull();
 await click('Neural Data');mockParticipant='second';await mount(false);expect(element.querySelector('[data-summary-view]')).not.toBeNull();expect(JSON.parse(element.querySelector('[data-summary-view]').textContent).participant).toBe('second');
 });
