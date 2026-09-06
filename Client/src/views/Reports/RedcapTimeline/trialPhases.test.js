import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {trialPhasesInRange, trialPhaseBands} from './trialPhases';
import TrialPhaseLegend from './TrialPhaseLegend';

const phase=(key,start,label=key)=>({key,label,start:Date.parse(start)/1000,color:'#356E9B'});
const phases=[phase('pre','2025-01-01T08:00:00Z','Pre-trial'),phase('s0','2025-05-27T07:00:00Z','Stage 0 trial'),phase('post','2025-06-07T07:00:00Z','Post-Stage 0 / pre-Stage 1'),phase('s1','2025-07-16T07:00:00Z','Stage 1 biomarker discovery'),phase('s2','2025-07-30T07:00:00Z','Stage 2 active-stim optimization (ongoing)')];

test('full history labels every intersecting phase with its exact recorded boundary and does not mutate source',()=>{
  const before=JSON.stringify(phases),range={start:'2025-05-15',end:'2026-09-04'};
  const result=trialPhasesInRange([...phases].reverse(),range);
  expect(result.map(p=>p.key)).toEqual(['pre','s0','post','s1','s2']);
  expect(result[0]).toMatchObject({visibleStart:'2025-05-15 00:00:00',visibleEnd:'2025-05-27 00:00:00',throughDay:'2025-05-26'});
  expect(result[0].details).toContain('2025-01-01 00:00:00 Pacific');
  expect(result.at(-1).throughDay).toBe('2026-09-04');expect(JSON.stringify(phases)).toBe(before);
  expect(trialPhaseBands(phases,range)).toHaveLength(5);
});

test('date-window start retains the active phase, omits prior/future sections and respects exact intraday boundaries',()=>{
  expect(trialPhasesInRange(phases,{start:'2026-08-08',end:'2026-09-04'}).map(p=>p.key)).toEqual(['s2']);
  expect(trialPhasesInRange(phases,{start:'2025-05-27',end:'2025-06-06'}).map(p=>p.key)).toEqual(['s0']);
  const withinDay=[phase('a','2025-05-27T07:00:00Z'),phase('b','2025-05-27T19:00:00Z')];
  expect(trialPhasesInRange(withinDay,{start:'2025-05-27',end:'2025-05-27'}).map(p=>p.visibleEnd)).toEqual(['2025-05-27 12:00:00','2025-05-27 23:59:59']);
  expect(trialPhasesInRange(phases,{start:'2024-01-01',end:'2024-12-31'})).toEqual([]);
  expect(trialPhasesInRange(phases,{start:'',end:'2026-09-04'})).toEqual([]);
  expect(trialPhasesInRange(phases,{start:'2026-09-04',end:'2026-08-08'})).toEqual([]);
  expect(trialPhaseBands([],{})).toEqual([]);
});

test('each chart legend shows full names and dates with source timing accessible by hover or focus',()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;
  const element=document.createElement('div'),root=createRoot(element);
  act(()=>root.render(<TrialPhaseLegend phases={phases} range={{start:'2025-05-15',end:'2026-09-04'}}/>));
  expect(element.querySelector('[aria-label="Trial phases in this chart"]')).not.toBeNull();
  expect(element.querySelectorAll('li')).toHaveLength(5);
  expect(element.textContent).toContain('Post-Stage 0 / pre-Stage 1');
  expect(element.textContent).toContain('Shown: 2025-05-15 – 2025-05-26');
  expect(element.querySelector('li').title).toContain('next phase begins');
  expect(element.querySelector('li').tabIndex).toBe(0);
  act(()=>root.render(<TrialPhaseLegend phases={phases} range={{start:'2026-08-08',end:'2026-09-04'}}/>));
  expect(element.querySelectorAll('li')).toHaveLength(1);expect(element.textContent).toContain('Stage 2');
  act(()=>root.unmount());
});
