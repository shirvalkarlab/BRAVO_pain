import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import NeuralChart from './NeuralChart';
import {NEURAL_METRICS} from './neuralTimelineData';
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn(),Plots:{resize:jest.fn()}}));
let root,element;
const event={id:'a',time:Date.parse('2026-08-15T19:00:00Z')/1000,label:'Home',settings:{left:[{label:'Stimulation contacts',value:'C+2-'},{label:'Frequency',value:'130 Hz'}],right:[],group:[]}};
const props={events:[event],range:{start:'2026-08-01',end:'2026-09-03'},participant:'p',phases:[{key:'stage2',label:'Stage 2',color:'#aaa',start:event.time}],unknownIntervals:[],transitions:[],onSelect:jest.fn()};
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;Plotly.react.mockReset();Plotly.purge.mockClear();element=document.createElement('div');root=createRoot(element);});
afterEach(()=>act(()=>root.unmount()));
test('categorical and numeric timelines fit their container and carry local phase labels',()=>{
 act(()=>root.render(<NeuralChart {...props} metric={NEURAL_METRICS[0]}/>));
 let call=Plotly.react.mock.calls.at(-1);expect(call[2].yaxis.showticklabels).toBe(false);expect(call[2].images).toHaveLength(1);expect(decodeURIComponent(call[2].images[0].source)).toContain('Geometry');expect(call[2].showlegend).toBe(false);expect(call[3].responsive).toBe(true);expect(element.textContent).toContain('Stage 2');expect(element.querySelector('[role="img"]').style.width).toBe('100%');
 act(()=>root.render(<NeuralChart {...props} metric={NEURAL_METRICS[2]}/>));
 call=Plotly.react.mock.calls.at(-1);expect(call[2].yaxis.title).toBe('Hz');expect(call[2].showlegend).toBe(true);expect(call[1][0].y).toContain(130);expect(Plotly.purge).not.toHaveBeenCalled();
});
test('point and context clicks select complete settings and old handlers are removed',()=>{
 const handlers={},removeListener=jest.fn(),onSelect=jest.fn();Plotly.react.mockImplementation(node=>{node.on=(n,h)=>{handlers[n]=h;};node.removeListener=removeListener;});
 act(()=>root.render(<NeuralChart {...props} metric={NEURAL_METRICS[2]} transitions={[{...event,number:1}]} onSelect={onSelect}/>));
 const old=handlers.plotly_click;old({points:[{customdata:['a','details']}]});expect(onSelect).toHaveBeenCalledWith('a');old({points:[]});expect(onSelect).toHaveBeenCalledTimes(1);
 handlers.plotly_clickannotation({annotation:{name:'a'}});expect(onSelect).toHaveBeenCalledTimes(2);
 act(()=>root.render(<NeuralChart {...props} metric={NEURAL_METRICS[2]} onSelect={onSelect}/>));expect(removeListener).toHaveBeenCalledWith('plotly_click',old);expect(Plotly.react.mock.calls.at(-1)[2].annotations).toEqual([]);
});
test('ambiguous source values remain available for inspection without plotting a guessed value',()=>{
 const onSelect=jest.fn();act(()=>root.render(<NeuralChart {...props} metric={NEURAL_METRICS[2]} events={[{...event,settings:{left:[{label:'Frequency',value:'130 Hz; export: 140 Hz'}]}}]} onSelect={onSelect}/>));
 expect(element.textContent).toContain('without an unambiguous numeric value');expect(element.textContent).toContain('130 Hz; export: 140 Hz');expect(element.textContent).toContain('No recorded values');act(()=>element.querySelector('button').click());expect(onSelect).toHaveBeenCalledWith('a');
});

test('contact lead diagrams move into a complete local key on narrow screens without squeezing the timeline',()=>{
 const original={resize:global.ResizeObserver,request:global.requestAnimationFrame,cancel:global.cancelAnimationFrame};
 let resize,frame;const disconnect=jest.fn();global.ResizeObserver=jest.fn(callback=>{resize=callback;return {observe:jest.fn(),disconnect};});
 global.requestAnimationFrame=jest.fn(callback=>{frame=callback;return 4;});global.cancelAnimationFrame=jest.fn();
 const contacts={...event,settings:{left:[{label:'Stimulation contacts',value:'C+2-' }],right:[{label:'Stimulation contacts',value:'C+10a-'}]}};
 act(()=>root.render(<NeuralChart {...props} events={[contacts]} participant="RCS08" metric={NEURAL_METRICS[0]}/>));
 const node=element.querySelector('[role="img"]');Object.defineProperty(node,'clientWidth',{value:342,configurable:true});act(()=>{resize();frame();});
 const call=Plotly.react.mock.calls.at(-1);expect(call[2].margin.l).toBe(45);expect(call[2].images).toEqual([]);expect(call[2].yaxis.showticklabels).toBe(true);
 const gallery=element.querySelector('[aria-label="Contact configuration schematics"]');expect(gallery.textContent).toContain('L GPe: C+2-');expect(gallery.textContent).toContain('R MD Thal: C+10a-');expect(gallery.querySelector('img').alt).toContain('C1: L GPe');
 Object.defineProperty(node,'clientWidth',{value:1200,configurable:true});act(()=>{resize();frame();});expect(element.querySelector('[aria-label="Contact configuration schematics"]')).toBeNull();expect(Plotly.react.mock.calls.at(-1)[2].images).toHaveLength(1);
 act(()=>root.unmount());expect(disconnect).toHaveBeenCalled();root=createRoot(element);
 global.ResizeObserver=original.resize;global.requestAnimationFrame=original.request;global.cancelAnimationFrame=original.cancel;
});
