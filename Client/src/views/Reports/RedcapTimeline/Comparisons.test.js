import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import StimulationPrograms from './StimulationPrograms';
import Medications from './Medications';
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,variant})=>variant==='h4'?<h4>{children}</h4>:<span>{children}</span>}));
jest.mock('./ComparisonChart',()=>({__esModule:true,default:props=><pre data-plot={props.label}>{JSON.stringify(props.plot)}</pre>}));
let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});
const render=component=>act(async()=>root.render(component));
const plot=label=>JSON.parse(element.querySelector(`[data-plot="${label}"]`).textContent);
const points=Array.from({length:5},(_,i)=>({time:1735758000+i*86400,value:i+1}));
const selected={key:'nrs',label:'Overall NRS',range:[0,10]};
const condition=(id,median,mode='open_loop')=>({id,label:`Program ${id}`,mode,count:5,median,points,settings:[{label:'L frequency',value:'55 Hz'}]});

test('stimulation comparisons stack full-width OL and CL plots with matching program settings and OFF reference',async()=>{
  const metric={...selected,conditions:[condition('a',7),condition('b',2),condition('c',3),condition('d',1,'closed_loop')],top:{open_loop:['a','b','c'],closed_loop:['d']},baseline:{count:2,median:4,points:points.slice(0,2)}};
  await render(<StimulationPrograms comparison={{available:true,metrics:[metric]}} metrics={[selected]}/>);
  const open=plot('Overall NRS open loop program comparison'),closed=plot('Overall NRS closed loop program comparison');
  expect(open.traces.filter(t=>t.type==='box').map(t=>t.name)).toEqual(['Program b','Program c','Program a']);
  expect(closed.traces.filter(t=>t.type==='box').map(t=>t.name)).toEqual(['Program d']);
  expect(open.fitWidth).toBe(true);expect(closed.fitWidth).toBe(true);
  expect(open.layout.xaxis.tickvals).toEqual([0,1,2]);expect(closed.layout.xaxis.tickvals).toEqual([0]);
  expect(element.querySelectorAll('[data-plot]')).toHaveLength(2);
  expect(element.querySelectorAll('section[aria-label$=" settings"]')).toHaveLength(4);expect(element.querySelector('[aria-label="OL 1 settings"]').textContent).toContain('n = 5 surveys (5 days)');
  expect(element.textContent).toContain('Stimulation OFF reference');expect(element.textContent).toContain('Stage 1 onward');expect(element.textContent).toContain('Lower observed medians first');
});

test('stimulation empty, unavailable, sparse-mode and absent-metric states are explicit',async()=>{
  await render(<StimulationPrograms metrics={[selected]}/>);expect(element.textContent).toContain('not available for this participant');
  await render(<StimulationPrograms comparison={{available:false,message:'Needs reviewed stage data'}} metrics={[selected]}/>);expect(element.textContent).toContain('Needs reviewed stage data');
  await render(<StimulationPrograms comparison={{available:true,metrics:[]}} metrics={[]}/>);expect(element.textContent).toContain('Select a clinical metric');
  await render(<StimulationPrograms comparison={{available:true,metrics:[]}} metrics={[selected]}/>);expect(element.textContent).toContain('No eligible comparison data');
  await render(<StimulationPrograms comparison={{available:true,metrics:[{...selected,conditions:[],top:{},baseline:{count:0,points:[]}}]}} metrics={[selected]}/>);
  expect(element.textContent).toContain('No open loop program has five');expect(element.textContent).toContain('No closed loop program has five');expect(element.querySelector('[data-plot]')).toBeNull();
  await render(<StimulationPrograms comparison={{available:true,metrics:[{...selected,conditions:[],top:{}}]}} metrics={[selected]}/>);expect(element.textContent).not.toContain('Stimulation OFF reference');
});

test('medication timeline precedes every condition, groups by class/regimen without top-three truncation and explains overlap/PRN',async()=>{
  const conditions=Array.from({length:7},(_,i)=>({...condition(`med-${i}`,i),drug_class:i<3?'Class Z':'Class A',generic:`Drug ${i}`,status:'PRN available'}));
  const episodes=[{id:'a',name:'Drug A',drug_class:'Class A',start:1735758000,end:null,ongoing:true,dose:'5 mg',frequency:'PRN',prn:true},{id:'b',name:'Drug B',drug_class:'Class Z',start:1735758000,end:1736758000,dose:'10 mg',frequency:'Daily',prn:false}];
  await render(<Medications comparison={{available:true,metrics:[{...selected,conditions}],episodes,provenance:{period_start:1735758000}}} metrics={[selected]} today="2026-09-03"/>);
  expect(element.querySelector('h4').textContent).toBe('Medication timeline');expect(element.querySelector('[data-plot]').getAttribute('data-plot')).toBe('Documented medication regimens over time');
  const boxes=plot('Overall NRS medication conditions').traces.filter(trace=>trace.type==='box');expect(boxes).toHaveLength(7);expect(boxes[0].name).toBe('Program med-3');
  expect(element.textContent).toContain('same survey can contribute to more than one condition');expect(element.textContent).toContain('PRN available');expect(element.textContent).toContain('no top-three selection');
});

test('medication unavailable/missing intervals/missing selected metrics render useful empty states',async()=>{
  await render(<Medications metrics={[selected]} today="2026-09-03"/>);expect(element.textContent).toContain('not available for this participant');
  await render(<Medications comparison={{available:false,message:'Medication reconciliation pending'}} metrics={[selected]} today="2026-09-03"/>);expect(element.textContent).toContain('reconciliation pending');
  await render(<Medications comparison={{available:true,metrics:[],episodes:[]}} metrics={[]} today="2026-09-03"/>);expect(element.textContent).toContain('No documented medication intervals');expect(element.textContent).toContain('Select a clinical metric');
  await render(<Medications comparison={{available:true,metrics:[],episodes:[]}} metrics={[selected]} today="2026-09-03"/>);expect(element.textContent).toContain('No eligible medication-condition surveys');
  await render(<Medications comparison={{available:true,metrics:[{...selected,conditions:[]}],episodes:[]}} metrics={[selected]} today="2026-09-03"/>);expect(element.querySelector('[data-plot]')).toBeNull();
});

test('both comparison views expose available source coverage and handle missing provenance honestly',async()=>{
  const provenance={matched:8,canonical_rows:10,unmatched_canonical:2,source_max_survey:1735758000,source_rows:4,regimens_without_complete_interval:1};
  await render(<StimulationPrograms comparison={{available:true,metrics:[],provenance}} metrics={[]}/>);
  expect(element.textContent).toContain('Matched 8 of 10 reviewed surveys');expect(element.textContent).toContain('Matching source contains surveys through');
  await render(<Medications comparison={{available:true,metrics:[],episodes:[],provenance}} metrics={[]} today="2026-09-03"/>);
  expect(element.textContent).toContain('4 documented medication source rows');expect(element.textContent).toContain('1 regimens lack a complete interval');
  await render(<StimulationPrograms comparison={{available:true,metrics:[]}} metrics={[]}/>);expect(element.textContent).toContain('Source coverage details are not available');
});

test('fixed finalized OL reference renders independently of metric ranking and links the reviewed source',async()=>{
  const finalized_open_loop={available:true,id:'a',mode:'open_loop',settings:[],source:{title:'Latest home settings',url:'https://docs.google.com/spreadsheets/d/example',range:'Home programs!B2:C5'}};
  const metric={...selected,conditions:[condition('a',2)],top:{open_loop:['a'],closed_loop:[]}};
  await render(<StimulationPrograms comparison={{available:true,metrics:[metric],finalized_open_loop}} metrics={[selected]}/>);
  const chart=plot('Overall NRS open loop program comparison');
  expect(chart.layout.xaxis.tickvals).toEqual([0,3]);expect(chart.traces.filter(t=>t.type==='box')).toHaveLength(2);
  expect(element.textContent).toContain('always shown in the fourth open-loop position');
  expect(element.querySelector('a').getAttribute('href')).toBe(finalized_open_loop.source.url);
  expect(element.textContent).toContain('Home programs!B2:C5');
  expect(element.querySelectorAll('section[aria-label$=" settings"]')).toHaveLength(2);
  await render(<StimulationPrograms comparison={{available:true,metrics:[{...metric,conditions:[],top:{}}],finalized_open_loop:{...finalized_open_loop,source:undefined}}} metrics={[selected]}/>);
  expect(plot('Overall NRS open loop program comparison').traces).toHaveLength(0);
  expect(element.textContent).toContain('No eligible surveys');expect(element.textContent).toContain('reviewed home-program settings');
});

test('current CL is independently visible with source provenance even when no metric has an eligible box',async()=>{
  const current_closed_loop={available:true,id:'cl',mode:'closed_loop',settings:[],source:{url:'https://docs.google.com/spreadsheets/d/example',title:'Current home settings',range:'Home!D2:E5'}};
  const metric={...selected,conditions:[],top:{}};
  await render(<StimulationPrograms comparison={{available:true,metrics:[metric],current_closed_loop}} metrics={[selected]}/>);
  expect(plot('Overall NRS closed loop program comparison').layout.xaxis.tickvals).toEqual([3]);
  expect(element.textContent).toContain('fourth closed-loop position');expect(element.textContent).toContain('Home!D2:E5');
  expect(element.querySelector('a').textContent).toBe('Current home settings');
  await render(<StimulationPrograms comparison={{available:true,metrics:[metric],current_closed_loop:{...current_closed_loop,source:undefined}}} metrics={[selected]}/>);
  expect(element.textContent).toContain('reviewed home-program settings');expect(element.textContent).toContain('No eligible surveys');
});


test('historical medication view uses reviewed end, explains ongoing notes and rejects invalid coverage',async()=>{
  const start=Date.parse('2026-08-01T00:00:00-07:00')/1000,end=Date.parse('2026-08-15T00:00:00-07:00')/1000;
  const episodes=[{id:'historical',name:'Synthetic',drug_class:'Class A',start,end:null,ongoing:true,dose:'1 unit',frequency:'Daily'}];
  const comparison={available:true,metrics:[],episodes,provenance:{period_start:start,period_end_exclusive:end}};
  await render(<Medications comparison={comparison} metrics={[]} today="2026-09-03"/>);
  expect(element.textContent).toContain('through 2026-08-14 Pacific');expect(element.textContent).toContain('medication use after this period is unverified');
  expect(plot('Documented medication regimens over time').layout.xaxis.range[1]).toBe('2026-08-15 00:00:00');
  expect(episodes[0].end).toBeNull();expect(episodes[0].ongoing).toBe(true);
  await render(<Medications comparison={{...comparison,provenance:{period_start:start,period_end_exclusive:start}}} metrics={[]} today="2026-09-03"/>);
  expect(element.textContent).toContain('documentation range is invalid');expect(element.querySelector('[data-plot]')).toBeNull();
  await render(<Medications comparison={{...comparison,provenance:{period_start:start,period_end_exclusive:Date.parse('2026-10-15T00:00:00-07:00')/1000}}} metrics={[]} today="2026-09-03"/>);
  expect(plot('Documented medication regimens over time').layout.xaxis.range[1]).toBe('2026-09-03 23:59:59');
});

test('program cards expose details only when supplied rows exist, including home-setting fallback rows',async()=>{
 const source={available:true,id:'reference',mode:'open_loop',settings:[],home_settings:{group:[{label:'Group',value:'GroupIdDef.GROUP_C'}],left:[{label:'Frequency',value:'55 Hz'}],right:[]}};
 const comparison={available:true,metrics:[{...selected,conditions:[],top:{}}],finalized_open_loop:source};
 await render(<StimulationPrograms comparison={comparison} metrics={[selected]}/>);
 const details=element.querySelector('details');expect(details).not.toBeNull();expect(details.textContent).toContain('Group: Group C');expect(details.textContent).toContain('Left · Frequency: 55 Hz');
 await act(async()=>details.querySelector('summary').click());expect(details.open).toBe(true);
 await render(<StimulationPrograms comparison={{...comparison,finalized_open_loop:{...source,home_settings:undefined}}} metrics={[selected]}/>);
 expect(element.querySelector('details')).toBeNull();
});

test('medication regimen and condition details use readable terms and retain recorded dates',async()=>{
 const source={...condition('med',2),drug_class:'opioid_analgesic',label:'Synthetic | 5 mg | bid | oral',status:'prn_available',frequency:'bid'};
 const episode={id:'regimen',name:'Synthetic',drug_class:'opioid_analgesic',dose:'5 mg',frequency:'bid',start:1735758000,end:null,ongoing:true};
 await render(<Medications comparison={{available:true,episodes:[episode],metrics:[{...selected,conditions:[source]}]}} metrics={[selected]} today="2026-09-03"/>);
 expect(element.textContent).toContain('opioid analgesic · Synthetic · 5 mg · Twice daily');
 expect(element.textContent).toContain('Synthetic · 5 mg · Twice daily · Oral');
 expect(element.textContent).toContain('Recorded start');expect(element.textContent).not.toContain('opioid_analgesic');
});

test('automatic comparisons expose eligible/excluded counts, stored source bounds and relief direction without upstream freshness claims',async()=>{
 const relief={key:'relief',label:'Relief',range:[0,100],direction:'higher'};
 const metric={...relief,conditions:[condition('lower',20),condition('higher',80)],top:{open_loop:['higher','lower'],closed_loop:[]},provenance:{total_surveys:15,eligible:12,assigned:10,unassigned:2,excluded_testing:3,missing_value:0,invalid:0,open_loop:10,closed_loop:0,off:0,latest_survey:1735844400,latest_assigned:1735758000,reasons:{testing_day:3,no_same_day_source:2}}};
 const provenance={policy_version:'synthetic-automatic-v1',source_min:1735758000,source_max:1735844400,source_min_survey:1735758000,source_max_survey:1735844400,calendar_verified:true,calendar:{testing_days:['2025-01-02'],first_day:'2025-01-02',last_day:'2025-01-02'}};
 const comparison={available:true,metrics:[metric],provenance,message:'Settings association follows reviewed source boundaries.'};
 const before=JSON.stringify(comparison);
 await render(<StimulationPrograms comparison={comparison} metrics={[relief]}/>);
 expect(plot('Relief open loop program comparison').traces.filter(t=>t.type==='box').map(t=>t.name)).toEqual(['Program higher','Program lower']);
 const coverage=element.querySelector('[aria-label="Relief eligibility and exclusions"]');
 expect(coverage.textContent).toContain('12 eligible non-testing surveys');expect(coverage.textContent).toContain('3 excluded on documented testing days');expect(coverage.textContent).toContain('2 eligible surveys without a verified program');
 expect(element.textContent).toContain('Higher observed medians first');expect(element.textContent).toContain('whether testing occurred in clinic or at home');expect(element.textContent).toContain('Stored device-report observation bounds');
 expect(element.textContent).toContain('does not verify the latest upstream import');expect(element.textContent).toContain(comparison.message);expect(JSON.stringify(comparison)).toBe(before);
 // Exercise all canonical presentation keys with synthetic observations, including relief direction.
 const keys=['nrs_intensity','vas_intensity','left_leg_vas_intensity','back_vas','relief','mpq_sum','mpq_aff','mpq_sen','mpq_standard_sensory_0_33','mpq_standard_affective_0_12','mpq_standard_0_45','electrocuting','tingly'];
 const all=keys.map((key,i)=>({...metric,key,label:`Recorded metric ${i}`,direction:key==='relief'?'higher':'lower'}));
 await render(<StimulationPrograms comparison={{...comparison,metrics:all}} metrics={all}/>);
 expect(element.querySelectorAll('[aria-label$="eligibility and exclusions"]')).toHaveLength(13);
 expect(element.querySelectorAll('[data-plot]')).toHaveLength(13);
 expect(element.textContent.match(/Higher observed medians first/g)).toHaveLength(1);
 expect(element.textContent.match(/Lower observed medians first/g)).toHaveLength(12);
});

test('unverified stored calendar withholds all ranking charts and retains the backend explanation',async()=>{
 const comparison={available:true,metrics:[{...selected,conditions:[condition('a',2)],top:{open_loop:['a']}}],provenance:{calendar_verified:false}};
 await render(<StimulationPrograms comparison={comparison} metrics={[selected]}/>);
 expect(element.textContent).toContain('A verified stored testing calendar is required');expect(element.querySelector('[data-plot]')).toBeNull();
 await render(<StimulationPrograms comparison={{...comparison,message:'Stored calendar receipt is invalid.'}} metrics={[selected]}/>);
 expect(element.textContent).toBe('Stored calendar receipt is invalid.');
});

test('historical CL references remain readable and dated while source labels are rendered as text',async()=>{
 const current_closed_loop={available:true,id:'historic',mode:'closed_loop',settings:[{label:'Frequency',value:'55 Hz'}],source:{as_of:'2025-01-02'}};
 const metric={...selected,conditions:[],top:{},provenance:{eligible:0,assigned:0,reasons:{'long_source_reason_<untrusted>':2}}};
 await render(<StimulationPrograms comparison={{available:true,metrics:[metric],current_closed_loop}} metrics={[selected]}/>);
 expect(element.textContent).toContain('Reviewed CL reference');expect(element.textContent).not.toContain('Current CL is');
 expect(element.textContent).toContain('Reviewed source as of 2025-01-02');expect(element.textContent).toContain('later settings and continuous delivery are not established');
 expect(element.textContent).toContain('long source reason <untrusted>: 2');expect(element.querySelector('untrusted')).toBeNull();
 expect(plot('Overall NRS closed loop program comparison').programs[0].title).toBe('Reviewed CL');
});
