import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import HomeNeuralChart from './HomeNeuralChart';
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
const time=Date.parse('2026-09-01T19:00:00Z')/1000;
const segment={id:'a',start:time,end:time+7200,mode:'Single threshold',sensing_side:'right',sensing_contacts:'8–10',power_band_label:'18–22 Hz',center_frequency_hz:20,mapping_status:'Contralateral',threshold_status:'Configured threshold guide',thresholds:[{value:12}],points:[{time,power:10,amplitude:3}]};
const props={panel:{side:'left',segments:[segment]},window:{id:'current',label:'Current settings',start:time,end:time+7200},participant:'RCS08'};
let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;Plotly.react.mockReset();Plotly.purge.mockClear();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));

test('modern responsive dual-axis chart keeps the source label and local detail key',()=>{
 act(()=>root.render(<HomeNeuralChart {...props}/>));
 const call=Plotly.react.mock.calls.at(-1);
 expect(call[1][0].name).toBe('R MD Thal biomarker');expect(call[2].yaxis2.side).toBe('right');expect(call[3].responsive).toBe(true);
 expect(element.querySelector('[role="img"]').style.width).toBe('100%');expect(element.textContent).toContain('Configured threshold(s)');
 expect(element.textContent).toContain('Sensing: R MD Thal · contacts 8 and 10');expect(element.textContent).toContain('18–22 Hz');expect(element.textContent).toContain('Control mapping: Contralateral');
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
 expect(element.querySelectorAll('[data-sensing-interval]')).toHaveLength(2);expect(element.textContent).toContain('Recorded sensing intervals · 2');expect(element.textContent).toContain('Control mapping: Not established');
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
 expect(cards[0].textContent).toContain('R MD Thal · contacts 8 and 10');
 expect(cards[0].textContent).toContain('20 Hz center');
 expect(cards[1].textContent).toContain('L GPe · contacts 1 and 3');
 expect(cards[1].textContent).toContain('13.67 Hz center');
 expect(element.querySelector('details, [role="combobox"]')).toBeNull();
 expect(later.sensing_contacts).toBe('1-3');
});
