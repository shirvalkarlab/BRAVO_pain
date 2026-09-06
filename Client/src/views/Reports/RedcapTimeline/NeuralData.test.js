import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import NeuralData from './NeuralData';
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children})=><span>{children}</span>}));
jest.mock('./NeuralChart',()=>({__esModule:true,default:props=><div><pre data-chart={props.metric.key}>{JSON.stringify(props)}</pre><button onClick={()=>props.onSelect('first')}>Choose first {props.metric.key}</button></div>}));
jest.mock('./StimulationContext',()=>({__esModule:true,default:props=><div data-context>{JSON.stringify(props)}<button onClick={()=>props.onDetailsChange(!props.openDetails)}>Details</button></div>}));
const home=(id,day)=>({id,time:Date.parse(`${day}T19:00:00Z`)/1000,settings:{left:[],right:[],group:[]}});
const homes=[home('first','2025-07-01'),home('last','2026-08-15')];
let root,element;
const charts=()=>[...element.querySelectorAll('[data-chart]')].map(n=>JSON.parse(n.textContent));
const render=props=>act(async()=>root.render(<NeuralData participant="p" homeTransitions={homes} {...props}/>));
async function toggle(label){await act(async()=>[...element.querySelectorAll('label')].find(n=>n.textContent===label).querySelector('input').click());}
async function click(label){await act(async()=>[...element.querySelectorAll('button')].find(n=>n.textContent===label).click());}
async function input(label,value){const n=[...element.querySelectorAll('input')].find(n=>document.querySelector(`label[for="${n.id}"]`)?.textContent===label);await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(n,value);n.dispatchEvent(new Event('input',{bubbles:true}));});}
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);jest.spyOn(Date,'now').mockReturnValue(Date.parse('2026-09-04T06:00:00Z'));});
afterEach(()=>{act(()=>root.unmount());element.remove();jest.restoreAllMocks();});
test('five ordered unsmoothed settings timelines have exactly two toggles and all original source records',async()=>{
 await render();expect(charts().map(c=>c.metric.key)).toEqual(['contacts','mode','frequency','amplitude','pulse_width']);
 expect(element.querySelectorAll('input[type="checkbox"]')).toHaveLength(2);expect(element.textContent).not.toContain('median');
 expect(charts().every(c=>c.range.start==='2025-07-01'&&c.range.end==='2026-09-03'&&c.events.length===2)).toBe(true);
 await toggle('Past 28 days');expect(charts()[0].range.start).toBe('2026-08-07');expect(charts()[0].events).toEqual(homes);expect(charts()[0].transitions.map(e=>e.id)).toEqual(['last']);
 expect(element.querySelector('[data-context]').textContent).toContain('"previous":{"id":"first"');
 await toggle('Stimulation context');expect(element.querySelector('[data-context]')).toBeNull();expect(charts()[0].transitions).toEqual([]);
 await click('Choose first contacts');expect(element.querySelector('[data-context]').textContent).toContain('"openDetails":true');
 await toggle('Past 28 days');expect(charts()[0].range.start).toBe('2025-07-01');
});
test('dense records limit annotations; date errors suppress plots and restore full history',async()=>{
 const many=Array.from({length:13},(_,i)=>home(`r${i}`,`2026-08-${String(i+1).padStart(2,'0')}`));
 await render({homeTransitions:many,unknownIntervals:[{start:many[0].time,end:null}]});expect(charts()[0].transitions.map(e=>e.id)).toEqual(['r12']);expect(element.textContent).toContain('do not carry settings through those gaps');
 await input('From','2026-08-14');expect(charts()[0].transitions).toEqual([]);expect(charts()[0].events).toHaveLength(13);
 await input('Through','2026-08-13');expect(charts()).toEqual([]);expect(element.textContent).toContain('Choose valid dates');
 await click('Full settings history');expect(charts()).toHaveLength(5);
 await input('Through','2027-01-01');expect(charts()).toEqual([]);await click('Full settings history');
 await input('From','');expect(charts()).toEqual([]);
});
test('settings can be removed and restored and unavailable records do not fabricate charts',async()=>{
 await render();await act(async()=>element.querySelector('button[title="Clear"]').click());expect(charts()).toEqual([]);expect(element.textContent).toContain('Select a setting above');
 await click('Default settings');expect(charts()).toHaveLength(5);
 await render({homeTransitions:[]});expect(charts()).toEqual([]);expect(element.textContent).toContain('No reviewed home-program records');
});
