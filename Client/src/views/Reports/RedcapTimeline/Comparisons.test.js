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
  expect(element.querySelectorAll('section')).toHaveLength(4);expect(element.querySelector('[aria-label="OL 1 settings"]').textContent).toContain('n = 5 surveys (5 days)');
  expect(element.textContent).toContain('Stimulation OFF reference');expect(element.textContent).toContain('Stage 1 onward');expect(element.textContent).toContain('lowest observed median');
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
  expect(element.querySelectorAll('section')).toHaveLength(2);
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
  expect(element.textContent).toContain('reviewed current home-program settings');expect(element.textContent).toContain('No eligible surveys');
});
