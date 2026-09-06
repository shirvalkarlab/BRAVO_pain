import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import MultimodalSummary from './MultimodalSummary';
let mockOura,mockNeural,mockRequests,mockCharts,mockContext;
jest.mock('./useOuraTimeline',()=>({useOuraTimeline:()=>mockOura}));
jest.mock('./useHomeNeuralTimeline',()=>({useHomeNeuralTimeline:(...args)=>{mockRequests.push(args);return mockNeural;}}));
jest.mock('./MultimodalChart',()=>({__esModule:true,default:props=>{mockCharts[props.title]=props;return <div data-summary-chart={props.title}/>;}}));
jest.mock('./HomeNeuralChart',()=>({NeuralLegend:()=> <div>Configured threshold(s)</div>, NeuralSensingIntervals:({descriptions})=><div data-sensing>{JSON.stringify(descriptions)}</div>}));
jest.mock('./StimulationContext',()=>({__esModule:true,default:props=>{mockContext=props;return <div data-context>Shared stimulation settings</div>;}}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children,role})=><div role={role}>{children}</div>}));
const point=(day,value)=>({time:Date.parse(`${day}T12:00:00-07:00`)/1000,day,value,source:'QC-approved first-party Oura timeline'});
const event=(id,day)=>({id,time:point(day,0).time,label:`Recorded ${id}`,settings:{}});
const redcap={metrics:[{key:'left_leg_vas_intensity',label:'Left-leg VAS',points:[point('2026-08-10',40),point('2026-08-12',60)]},{key:'mpq_standard_0_45',label:'MPQ total',points:[point('2026-08-10',20)]}],visits:{available:true,metrics:{left_leg_vas_intensity:[point('2026-08-11',50)]}},stimulation:{home_transitions:[event('before','2026-08-01'),event('one','2026-08-11')]} };
const time=point('2026-08-12',0).time;
const period={id:'past28',label:'Past 28 days',start:point('2026-08-07',0).time,end:point('2026-09-04',0).time,panels:['left','right'].map(side=>({side,segments:[{id:side,start:time,end:time+3600,sensing_side:'left',sensing_contacts:'1-3',center_frequency_hz:20,mode:'Open loop',points:[{time,power:20,amplitude:2},{time:time+1200,power:30,amplitude:3}],thresholds:[{value:100}]}]}))};
let element,root;
const mount=async(props={})=>act(async()=>root.render(<MultimodalSummary participant="RCS08" redcap={redcap} revision={2} {...props}/>));
const charts=()=>[...element.querySelectorAll('[data-summary-chart]')].map(node=>mockCharts[node.dataset.summaryChart]);
const toggle=async label=>{const input=[...element.querySelectorAll('label')].find(node=>node.textContent===label)?.querySelector('input');expect(input).toBeDefined();await act(async()=>input.click());};
const input=async(label,value)=>{const node=[...element.querySelectorAll('input')].find(n=>document.querySelector(`label[for="${n.id}"]`)?.textContent===label);expect(node).toBeDefined();await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new Event('input',{bubbles:true}));});};
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockRequests=[];mockCharts={};mockContext=null;mockOura={data:{metrics:[{key:'steps',label:'Steps',unit:'steps',points:[point('2026-08-10',1000),point('2026-08-11',2000)]},{key:'sleep_total',label:'Total sleep including naps',unit:'hours',points:[point('2026-08-10',8.5),point('2026-08-11',9)]}]},loading:false,error:''};mockNeural={data:{windows:[period],visit_days:['2026-08-11']},loading:false,error:''};element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);jest.spyOn(Date,'now').mockReturnValue(Date.parse('2026-09-04T06:00:00Z'));});
afterEach(()=>{act(()=>root.unmount());element.remove();jest.restoreAllMocks();});

test('all toggles start ON with one Pacific 28-day range, correct outcome axes and visible native sensing intervals',async()=>{
 await mount();expect([...element.querySelectorAll('input[type="checkbox"]')].map(n=>n.checked)).toEqual([true,true,true]);
 expect(charts()).toHaveLength(4);expect(charts().every(chart=>chart.range.start==='2026-08-07'&&chart.range.end==='2026-09-03')).toBe(true);
 expect(mockRequests.at(-1)).toEqual(['RCS08',2,'past28']);expect(mockContext.previous.id).toBe('before');expect(mockContext.events.map(e=>e.id)).toEqual(['one']);
 expect(charts()[0].limits).toEqual([[0,100],[0,45]]);expect(charts()[1].right).toBe('Sleep (hours)');
 expect(charts()[0].traces.some(t=>t.marker.symbol==='x'&&t.y[0]===50)).toBe(true);expect(charts()[1].traces.find(t=>t.yaxis==='y2'&&t.mode==='markers').y).toEqual([8.5,9]);
 expect(charts()[2].traces.filter(t=>t.line.dash).map(t=>t.y)).toEqual([[100,100]]);expect(charts()[2].neuralPeriod).toBe(period);expect(charts()[2].traces[0].y).toEqual([20,null,30]);
 expect(element.querySelectorAll('[data-sensing]')).toHaveLength(2);expect(element.textContent).toContain('1 and 3');expect(element.textContent).toContain('20 Hz center');
});

test('global median and context toggles preserve all raw observations and visit X markers while changing only their overlays',async()=>{
 await mount();const raw=charts().slice(0,2).map(c=>c.traces.filter(t=>t.mode==='markers'));
 await toggle('5-point rolling median');expect(charts().slice(0,2).map(c=>c.traces)).toEqual(raw);
 await toggle('Stimulation context');expect(element.querySelector('[data-context]')).toBeNull();expect(charts().every(c=>c.events.length===0)).toBe(true);
 expect(charts().slice(0,2).map(c=>c.traces)).toEqual(raw);expect(charts()[1].traces[0].marker.symbol).toContain('x');
 await toggle('5-point rolling median');expect(charts()[0].traces.some(t=>t.mode==='lines')).toBe(true);expect(charts()[2].traces[0].y).toEqual([20,null,30]);
});

test('zoom and hover propagate from any plot to every plot; reset and date changes clear shared zoom',async()=>{
 await mount();await act(async()=>charts()[3].onRange(['2026-08-10','2026-08-15']));expect(charts().every(c=>JSON.stringify(c.xRange)==='["2026-08-10","2026-08-15"]')).toBe(true);
 await act(async()=>charts()[1].onCursor('2026-08-11 12:00:00'));expect(charts().every(c=>c.cursor==='2026-08-11 12:00:00')).toBe(true);
 await act(async()=>charts()[0].onCursor(null));expect(charts().every(c=>c.cursor===null)).toBe(true);
 const reset=[...element.querySelectorAll('button')].find(n=>n.textContent==='Reset shared zoom');await act(async()=>reset.click());expect(charts().every(c=>c.xRange===null)).toBe(true);
 await act(async()=>charts()[0].onTransition('one'));expect(mockContext.selected.id).toBe('one');expect(mockContext.openDetails).toBe(true);
 await act(async()=>charts()[0].onRange(['a','b']));await input('Summary from','2026-08-10');expect(charts().every(c=>c.range.start==='2026-08-10'&&c.xRange===null)).toBe(true);
 expect(mockRequests.at(-1)).toEqual(['RCS08',2,{window:'custom',start_date:'2026-08-10',end_date:'2026-09-03'}]);
 await toggle('Past 28 days');expect(charts()[0].range.start).toBe('2026-08-07');expect(mockRequests.at(-1)[2]).toBe('past28');
});

test('invalid or future date ranges do not request neural data or render misleading plots and recover when corrected',async()=>{
 await mount();await input('Summary from','2026-09-04');expect(charts()).toEqual([]);expect(mockRequests.at(-1)[0]).toBeNull();expect(element.textContent).toContain('Choose valid dates');
 await input('Summary from','');expect(charts()).toEqual([]);await input('Summary from','2026-08-07');await input('Summary through','2026-09-05');expect(charts()).toEqual([]);
 await input('Summary through','2026-09-02');expect(charts()).toHaveLength(4);expect(mockRequests.at(-1)[2].end_date).toBe('2026-09-02');
});

test('missing data, calendar and failures stay explicit while independent charts remain usable',async()=>{
 mockOura={data:null,loading:true,error:''};mockNeural={data:null,loading:true,error:''};await mount({redcap:{}});
 expect(charts()).toHaveLength(2);expect(element.textContent).toContain('Loading reviewed Oura');expect(element.textContent).toContain('Loading home neural');expect(element.textContent).toContain('calendar loads');expect(element.textContent).toContain('No reviewed survey');
 mockOura={data:{metrics:[]},loading:false,error:'Oura unavailable'};mockNeural={data:{windows:[{...period,panels:[{side:'left',segments:[]}]}]},loading:false,error:'Neural unavailable'};
 await mount({redcap:{visits:{available:false,message:'Visit QC unavailable'}}});expect(element.textContent).toContain('No reviewed Oura');expect(element.textContent).toContain('Oura unavailable');expect(element.textContent).toContain('Neural unavailable');expect(element.textContent).toContain('Visit QC unavailable');expect(element.textContent).toContain('No established biomarker');expect(element.textContent).toContain('No established amplitude');
});

test('dense transition histories share one selected marker and selection updates all plots',async()=>{
 const events=Array.from({length:13},(_,i)=>event(`event-${i}`,`2026-08-${String(i+10).padStart(2,'0')}`));
 await mount({redcap:{...redcap,stimulation:{home_transitions:events}}});expect(mockContext.limited).toBe(true);expect(charts().every(c=>c.events.length===1&&c.events[0].id==='event-12')).toBe(true);
 await act(async()=>mockContext.onSelect('event-0'));expect(charts().every(c=>c.events[0].id==='event-0')).toBe(true);
});

test('neural point selection opens the source interval and complete settings; missing values keep thresholds independent',async()=>{
 await mount();expect(element.textContent).toContain('Configured threshold(s)');expect(element.textContent).toContain('Latest recorded average:');
 await act(async()=>charts()[2].onPoint('left'));
 expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('true');
 expect(element.textContent).toContain('contacts, sensing, thresholds and complete settings');
 await act(async()=>element.querySelector('.MuiAccordionSummary-root').click());expect(element.querySelector('.MuiAccordionSummary-root').getAttribute('aria-expanded')).toBe('false');
 mockNeural={data:{windows:[{...period,panels:[{side:'left',segments:[{...period.panels[0].segments[0],points:[]}]}]}]}};await mount();expect(charts()[2].traces).toHaveLength(1);expect(element.textContent).toContain('No established biomarker');
});
