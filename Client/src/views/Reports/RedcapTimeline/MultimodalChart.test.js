import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import MultimodalChart from './MultimodalChart';
jest.mock('plotly.js-dist',()=>({react:jest.fn(),relayout:jest.fn(),purge:jest.fn()}));
let root,element,handlers,remove;
const props=()=>({title:'Summary plot',traces:[{x:['2026-08-01'],y:[5]}],range:{start:'2026-08-01',end:'2026-08-28'},events:[],left:'Steps',right:'Sleep (hours)',onRange:jest.fn(),onTransition:jest.fn(),onCursor:jest.fn()});
const mount=p=>act(()=>root.render(<MultimodalChart {...p}/>));
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;element=document.createElement('div');root=createRoot(element);handlers={};remove=jest.fn();Object.values(Plotly).forEach(mock=>mock.mockReset());Plotly.react.mockImplementation(node=>{node.on=(name,fn)=>{handlers[name]=fn;};node.removeListener=remove;node._fullLayout={};});});
afterEach(()=>act(()=>root.unmount()));

test('uses responsive shared dual axes and propagates zoom, annotation selection, hover and reset without changing source traces',()=>{
 const p=props();mount(p);const [node,traces,layout,config]=Plotly.react.mock.calls.at(-1);
 expect(node.getAttribute('aria-label')).toBe('Summary plot');expect(node.style.width).toBe('100%');expect(node.style.minWidth).toBe('0');
 expect(traces).toBe(p.traces);expect(layout.yaxis2.side).toBe('right');expect(config).toMatchObject({responsive:true,scrollZoom:false,displaylogo:false});
 handlers.plotly_relayout({'xaxis.range[0]':'start','xaxis.range[1]':'end'});expect(p.onRange).toHaveBeenLastCalledWith(['start','end']);
 handlers.plotly_relayout({width:342});expect(p.onRange).toHaveBeenCalledTimes(1);
 handlers.plotly_relayout({'xaxis.autorange':true});expect(p.onRange).toHaveBeenLastCalledWith(null);
 handlers.plotly_clickannotation({annotation:{name:'record-a'}});expect(p.onTransition).toHaveBeenCalledWith('record-a');
 handlers.plotly_hover({points:[{x:Date.parse('2026-08-03T12:00:00Z')}]});expect(p.onCursor).toHaveBeenLastCalledWith('2026-08-03 12:00:00.000');
 handlers.plotly_hover({points:[]});handlers.plotly_hover({});expect(p.onCursor).toHaveBeenCalledTimes(1);
 handlers.plotly_unhover();expect(p.onCursor).toHaveBeenLastCalledWith(null);
 const prior=handlers.plotly_relayout;mount({...p,xRange:['start','end']});expect(Plotly.react.mock.calls.at(-1)[2].xaxis.range).toEqual(['start','end']);expect(remove).toHaveBeenCalledWith('plotly_relayout',prior);
});

test('shared hover guide is added to and removed from existing stimulation shapes',()=>{
 const p={...props(),events:[{id:'a',number:1,time:Date.parse('2026-08-02T19:00:00Z')/1000,label:'Observed settings',settings:{}}]};
 mount({...p,cursor:'2026-08-03 12:00:00'});let shapes=Plotly.relayout.mock.calls.at(-1)[1].shapes;
 expect(shapes).toHaveLength(2);expect(shapes[0].line.dash).toBe('dash');expect(shapes[1]).toMatchObject({x0:'2026-08-03 12:00:00',x1:'2026-08-03 12:00:00',line:{dash:'dot'}});
 mount({...p,cursor:null});shapes=Plotly.relayout.mock.calls.at(-1)[1].shapes;expect(shapes).toHaveLength(1);expect(shapes[0].line.dash).toBe('dash');
});

test('resize adapts compact label density and cleans listeners, observer and plot on unmount',()=>{
 const saved={resize:global.ResizeObserver,raf:global.requestAnimationFrame,cancel:global.cancelAnimationFrame};let resize,frame;const disconnect=jest.fn();
 global.ResizeObserver=jest.fn(fn=>{resize=fn;return {observe:jest.fn(),disconnect};});global.requestAnimationFrame=jest.fn(fn=>{frame=fn;return 8;});global.cancelAnimationFrame=jest.fn();
 try {const p=props();mount(p);const node=element.querySelector('[role="img"]');Object.defineProperty(node,'clientWidth',{value:342,configurable:true});act(()=>{resize();frame();});
 expect(Plotly.react.mock.calls.at(-1)[2].xaxis.nticks).toBe(3);Object.defineProperty(node,'clientWidth',{value:1000});act(()=>{resize();frame();});expect(Plotly.react.mock.calls.at(-1)[2].xaxis.nticks).toBe(7);
 act(()=>root.unmount());expect(disconnect).toHaveBeenCalled();expect(Plotly.purge).toHaveBeenCalledWith(node);expect(remove.mock.calls.map(call=>call[0])).toEqual(expect.arrayContaining(['plotly_relayout','plotly_hover','plotly_unhover','plotly_clickannotation']));root=createRoot(element);
 } finally {global.ResizeObserver=saved.resize;global.requestAnimationFrame=saved.raf;global.cancelAnimationFrame=saved.cancel;}
});

test('uninitialized Plotly surface safely waits for layout before drawing hover guide',()=>{
 Plotly.react.mockImplementation(()=>{});mount({...props(),cursor:'2026-08-03'});expect(Plotly.relayout).not.toHaveBeenCalled();
});

test('neural observation selection uses segment identity and ignores missing point data',()=>{
 const p={...props(),onPoint:jest.fn(),neuralPeriod:{id:'past28',start:1,end:2}};mount(p);
 expect(Plotly.react.mock.calls.at(-1)[2].yaxis.rangemode).toBeUndefined();
 handlers.plotly_click({points:[{customdata:['segment-a','details']}]});expect(p.onPoint).toHaveBeenCalledWith('segment-a');
 handlers.plotly_click({points:[{customdata:[null]}]});handlers.plotly_click({points:[{}]});handlers.plotly_click({points:[]});handlers.plotly_click({});expect(p.onPoint).toHaveBeenCalledTimes(1);
 mount(props());handlers.plotly_click({points:[{customdata:['value']}]});
});
