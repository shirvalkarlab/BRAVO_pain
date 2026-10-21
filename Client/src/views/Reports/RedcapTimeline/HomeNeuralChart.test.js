import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import HomeNeuralChart from './HomeNeuralChart';
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
const time=Date.parse('2026-09-01T19:00:00Z')/1000;
const segment={id:'a',start:time,end:time+7200,mode:'Single threshold',sensing_side:'right',sensing_contacts:'8–10',power_band_label:'18–22 Hz',center_frequency_hz:20,mapping_status:'Contralateral',threshold_status:'Configured threshold guide',thresholds:[{value:12}],points:[{time,power:10,amplitude:3}]};
const props={panel:{side:'left',segments:[segment]},window:{id:'current',label:'Current settings',start:time,end:time+7200},participant:'SYNTHETIC_A1'};
let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;Plotly.react.mockReset();Plotly.purge.mockClear();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));

test('modern responsive dual-axis chart keeps the source label and local detail key',()=>{
 act(()=>root.render(<HomeNeuralChart {...props}/>));
 const call=Plotly.react.mock.calls.at(-1);
 expect(call[1][0].name).toBe('Right lead biomarker');expect(call[2].yaxis2.side).toBe('right');expect(call[3].responsive).toBe(true);
 expect(element.querySelector('[role="img"]').style.width).toBe('100%');expect(element.textContent).toContain('Configured threshold(s)');
 expect(element.textContent).toContain('Sensing: Right lead · contacts 8 and 10');expect(element.textContent).toContain('18–22 Hz');expect(element.textContent).toContain('Control mapping: Contralateral');
 expect(element.textContent).not.toContain('No established');expect(element.textContent).toContain('Recorded sensing intervals · 1');expect(element.textContent).toContain('20 Hz center');expect(element.querySelector('details')).toBeNull();
 expect(element.textContent).toContain('Recorded averages: 1 biomarker · 1 amplitude.');expect(element.textContent).toContain('Latest recorded average: 2026-09-01 12:00 Pacific.');
 expect(element.querySelector('[data-sensing-interval]').textContent).toContain('Configured threshold guide');
});

test('point clicks and configuration buttons select the full settings; listeners clean up on re-render',()=>{
 const handlers={},removeListener=jest.fn(),onSegment=jest.fn();
 Plotly.react.mockImplementation(node=>{node.on=(n,h)=>{handlers[n]=h;};node.removeListener=removeListener;});
 act(()=>root.render(<HomeNeuralChart {...props} onSegment={onSegment}/>));
 const old=handlers.plotly_click;old({points:[{customdata:['a','details']}]});
 act(()=>element.querySelector('button').click());expect(onSegment).toHaveBeenCalledTimes(2);expect(onSegment).toHaveBeenLastCalledWith('a');
 old({points:[]});old({points:[{}]});old({points:[{customdata:[null]}]});old({});expect(onSegment).toHaveBeenCalledTimes(2);
 act(()=>root.render(<HomeNeuralChart {...props}/>));expect(removeListener).toHaveBeenCalledWith('plotly_click',old);
 handlers.plotly_click({points:[{customdata:['a']}]});expect(element.querySelector('button')).toBeNull();
});

test('unknown and empty records report missing evidence; plural configuration details remain accessible',()=>{
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[]}}/>));
 expect(element.textContent).toContain('No established biomarker samples');expect(element.textContent).toContain('No established stimulation-amplitude samples');
 expect(element.querySelector('details')).toBeNull();expect(element.textContent).not.toContain('Configured threshold(s)');
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[{...segment,thresholds:[],mapping_status:null,threshold_status:null},{...segment,id:'b'}]}}/>));
 expect(element.querySelectorAll('[data-sensing-interval]')).toHaveLength(2);expect(element.textContent).toContain('Recorded sensing intervals · 2');expect(element.textContent).toContain('Control mapping: Sensing-to-stimulation control relationship not established');
});

test('resize changes tick density and font size without a width floor and releases its observer',()=>{
 const original={resize:global.ResizeObserver,request:global.requestAnimationFrame,cancel:global.cancelAnimationFrame};
 let resize,frame;const disconnect=jest.fn();global.ResizeObserver=jest.fn(callback=>{resize=callback;return {observe:jest.fn(),disconnect};});
 global.requestAnimationFrame=jest.fn(callback=>{frame=callback;return 4;});global.cancelAnimationFrame=jest.fn();
 act(()=>root.render(<HomeNeuralChart {...props}/>));
 const node=element.querySelector('[role="img"]');Object.defineProperty(node,'clientWidth',{value:342,configurable:true});act(()=>{resize();frame();});
 expect(Plotly.react.mock.calls.at(-1)[2].xaxis.nticks).toBe(3);expect(Plotly.react.mock.calls.at(-1)[2].font.size).toBe(12);
 Object.defineProperty(node,'clientWidth',{value:1200,configurable:true});act(()=>{resize();frame();});expect(Plotly.react.mock.calls.at(-1)[2].xaxis.nticks).toBe(7);
 act(()=>root.unmount());expect(disconnect).toHaveBeenCalled();expect(Plotly.purge).toHaveBeenCalledWith(node);root=createRoot(element);
 global.ResizeObserver=original.resize;global.requestAnimationFrame=original.request;global.cancelAnimationFrame=original.cancel;
});


test('every interval exposes dates, clinical source, contacts and center without interaction or a settings dropdown',()=>{
 const later={...segment,id:'later',points:[{time:time+3600,power:8,amplitude:2}],start:time+3600,sensing_side:'left',sensing_contacts:'1-3',center_frequency_hz:13.67,power_band_label:'13.67 Hz center · band width not recorded'};
 const first={...segment,end:time+3600};
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[first,later]}}/>));
 const cards=[...element.querySelectorAll('[data-sensing-interval]')];
 expect(cards).toHaveLength(2);
 expect(cards[0].textContent).toContain('2026-09-01 12:00 → 2026-09-01 13:00 Pacific');
 expect(cards[0].textContent).toContain('Right lead · contacts 8 and 10');
 expect(cards[0].textContent).toContain('20 Hz center');
 expect(cards[1].textContent).toContain('Left lead · contacts 1 and 3');
 expect(cards[1].textContent).toContain('13.67 Hz center');
 expect(element.querySelector('details, [role="combobox"]')).toBeNull();
 expect(later.sensing_contacts).toBe('1-3');
});

test('observational chart labels describe native evidence without home eligibility or inferred control',()=>{
 const native={...segment,mode:'Not established',mapping_status:'Not established',threshold_status:'No inferred threshold',thresholds:[]};
 const observations={...props.window,display_basis:'recorded_observations',label:'Current recorded observations'};
 act(()=>root.render(<HomeNeuralChart {...props} window={observations} panel={{side:'left',segments:[native]}}/>));
 const image=element.querySelector('[role="img"]');
 expect(image.getAttribute('aria-label')).toContain('recorded neural power and channel amplitude');
 expect(image.getAttribute('aria-label')).not.toContain('home');
 expect(element.textContent).toContain('Recorded neural power · left axis');expect(element.textContent).toContain('Recorded channel amplitude · right axis');
 expect(element.textContent).toContain('Recorded averages: 1 neural power · 1 amplitude.');
 expect(element.textContent).not.toContain('Configured threshold(s)');
 const call=Plotly.react.mock.calls.at(-1);
 expect(call[2].yaxis.title.text).toBe('Neural power (LSB)');expect(call[2].yaxis2.title.text).toBe('Recorded amp (mA)');
 expect(call[1].filter(trace=>trace.line.dash)).toHaveLength(0);
 expect(call[1][0].y).toEqual([10]);expect(call[1][1].y).toEqual([3]);
 expect(call[1][0].name).toBe('Right lead recorded neural power');
 expect(call[1][1].name).toBe('Left lead recorded channel amplitude');
 for(const trace of call[1]) {
  const hover=trace.customdata[0][1];
  expect(hover).toContain('Recorded neural power: 10 LSB');
  expect(hover).toContain('Recorded channel amplitude: 3 mA');
  expect(hover).toContain('Sensing source: Right lead');
  expect(hover).not.toContain('Biomarker');expect(hover).not.toContain('Stimulation amplitude:');
 }
 act(()=>root.render(<HomeNeuralChart {...props} window={observations} panel={{side:'left',segments:[]}}/>));
 expect(element.textContent).toContain('No recorded neural-power samples');expect(element.textContent).toContain('No recorded channel-amplitude samples');
 expect(element.textContent).not.toContain('home');
});


test('visible sensing cards identify unverified inherited labels without requiring hover or opening details',()=>{
 const uncertain={...segment,sensing_provenance:{status:'unverified',metadata_available:true,conflicting_settings:false,inherited_settings:true}};
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[uncertain]}}/>));
 const card=element.querySelector('[data-sensing-interval]');
 expect(card.textContent).toContain('(unverified)');expect(card.textContent).toContain('Unverified sensing labels:');
 expect(card.textContent).toContain('inherited without a direct settings record');
 expect(card.textContent).toContain('20 Hz center (unverified)');
 expect(Plotly.react.mock.calls.at(-1)[1][0].y).toEqual([10]);
});

test('independent lead current has an honest legend and provenance even without a neural segment',()=>{
 act(()=>root.render(<HomeNeuralChart {...props} participant="synthetic" panel={{side:'right',segments:[],amplitude_series:[{time,amplitude:0}],amplitude_provenance:'Recorded right lead current; no power alignment inferred.'}}/>));
 expect(element.textContent).toContain('Right lead recorded current');
 expect(element.textContent).toContain('Recorded right lead current; no power alignment inferred.');
 expect(element.textContent).toContain('0 biomarker · 1 amplitude.');
 expect(Plotly.react.mock.calls.at(-1)[1][0].y).toEqual([0]);
});


test('recorded-only card avoids duplicate frequency and empty complete-settings action',()=>{
 const only={...segment,mode:'unknown',sensing_contacts:'ZERO_TWO_LEFT',power_band_label:'25.2 Hz',center_frequency_hz:25.2,mapping_status:'recorded',threshold_status:'unavailable',settings:{},thresholds:[]};
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[only]}} onSegment={jest.fn()}/>));
 const card=element.querySelector('[data-sensing-interval]');
 expect(card.textContent).toContain('contacts 0 and 2');expect(card.textContent.match(/25.2 Hz/g)).toHaveLength(1);
 expect(card.textContent).not.toContain('unknown');expect(card.textContent).not.toContain('unavailable');expect(card.textContent).not.toContain('Complete settings');
 expect(card.querySelector('button').textContent).toBe('Sensing details');
 expect(card.querySelector('button').getAttribute('aria-label')).toContain('Sensing details for');
});


test('unverified sensing frequency is qualified once without duplicating the same center',()=>{
 const only={...segment,power_band_label:'25.2 Hz',center_frequency_hz:25.2,
  sensing_provenance:{status:'unverified',metadata_available:true,conflicting_settings:true,inherited_settings:false}};
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[only]}}/>));
 const card=element.querySelector('[data-sensing-interval]');
 expect(card.textContent.match(/25.2 Hz/g)).toHaveLength(1);
 expect(card.textContent).toContain('25.2 Hz center (unverified)');
 expect(card.textContent).toContain('earlier and later exported sensing settings differ');
});


test('conflicting original-source configurations are visible before opening recorded details',()=>{
 const conflict={...segment,settings_context:{status:'conflict',observations:[{settings:{group:[{label:'Group',value:'Group D'}]}}]}};
 act(()=>root.render(<HomeNeuralChart {...props} panel={{side:'left',segments:[conflict]}} onSegment={jest.fn()}/>));
 const card=element.querySelector('[data-sensing-interval]');
 expect(card.textContent).toContain('Source configurations differ; inspect the dated settings.');
 expect(card.querySelector('button').textContent).toBe('Recorded settings and sensing details');
});
