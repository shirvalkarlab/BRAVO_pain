import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import OuraChart from './OuraChart';
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn(),Plots:{resize:jest.fn()}}));
let root,element;
const metric={key:'steps',label:'Steps',unit:'steps',points:[{day:'2026-08-01',value:100},{day:'2026-08-03',value:300}]};
const range={start:'2026-08-01',end:'2026-08-03'};
const phases=[{key:'stage',label:'Stage 1',color:'#123456',start:Date.parse('2026-08-02T19:00:00Z')/1000}];
const originalResize=global.ResizeObserver;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;delete global.ResizeObserver;element=document.createElement('div');root=createRoot(element);Plotly.react.mockClear();Plotly.purge.mockClear();Plotly.Plots.resize.mockClear();});
afterEach(()=>{act(()=>root.unmount());global.ResizeObserver=originalResize;});
const render=props=>act(()=>root.render(<OuraChart metric={metric} range={range} phases={phases} smooth={false} markers={true} {...props}/>));

test('Oura renderer fits its container and preserves selected range, units, gap breaks and phase boundaries',()=>{
  render();
  const node=element.querySelector('[role="img"]');expect(node.getAttribute('aria-label')).toBe('Steps Oura timeline');
  expect(node.style.width).toBe('100%');expect(node.style.minWidth).toBe('0');expect(element.querySelector('[style*="overflow-x: auto"]')).toBeNull();
  const [target,traces,layout,config]=Plotly.react.mock.calls.at(-1);
  expect(target).toBe(node);expect(traces[0]).toMatchObject({connectgaps:false,y:[100,null,300]});
  expect(layout.xaxis).toMatchObject({range:['2026-08-01 00:00:00','2026-08-03 23:59:59']});
  expect(layout.yaxis.title).toBe('steps');expect(layout.autosize).toBe(true);expect(layout.showlegend).toBe(false);
  expect(layout.shapes).toHaveLength(2);expect(layout.shapes[0].x0).toBe('2026-08-02 12:00:00');
  expect(config).toMatchObject({responsive:true,displaylogo:false,scrollZoom:false});
  render({smooth:true,markers:false,phases:[]});
  const updated=Plotly.react.mock.calls.at(-1);expect(updated[0]).toBe(node);expect(updated[1]).toHaveLength(2);expect(updated[1][0].mode).toBe('markers');expect(updated[2].shapes).toEqual([]);expect(updated[2].showlegend).toBe(true);
  act(()=>root.unmount());expect(Plotly.purge).toHaveBeenCalledWith(node);root=createRoot(element);
});

test('responsive resize waits for Plotly readiness, coalesces work and releases its observer',()=>{
  let notify,frame;
  const originals={request:global.requestAnimationFrame,cancel:global.cancelAnimationFrame};
  const observer={observe:jest.fn(),disconnect:jest.fn()};
  global.ResizeObserver=jest.fn(callback=>{notify=callback;return observer;});
  global.requestAnimationFrame=jest.fn(callback=>{frame=callback;return 9;});global.cancelAnimationFrame=jest.fn();
  render();const node=element.querySelector('[role="img"]');expect(observer.observe).toHaveBeenCalledWith(node);
  act(()=>{notify();frame();});expect(Plotly.Plots.resize).not.toHaveBeenCalled();
  node._fullLayout={};act(()=>{notify();notify();frame();});expect(Plotly.Plots.resize).toHaveBeenCalledWith(node);expect(global.cancelAnimationFrame).toHaveBeenCalledWith(9);
  act(()=>root.unmount());expect(observer.disconnect).toHaveBeenCalledTimes(1);expect(global.cancelAnimationFrame).toHaveBeenLastCalledWith(9);root=createRoot(element);
  global.requestAnimationFrame=originals.request;global.cancelAnimationFrame=originals.cancel;
});

test('sample charts label Pacific timestamps and retain raw readings alongside the five-point median',()=>{
  const sampleMetric={key:'heart_rate',label:'Heart rate',unit:'bpm',resolution:'sample',points:[{time:Date.parse('2026-08-01T19:00:00Z')/1000,day:'2026-08-01',value:60}]};
  render({metric:sampleMetric,smooth:true});
  const [,traces,layout]=Plotly.react.mock.calls.at(-1);
  expect(traces).toHaveLength(2);expect(traces[0].type).toBe('scattergl');expect(traces[1].name).toBe('5-point rolling median');expect(layout.xaxis.title).toContain('Pacific');expect(layout.showlegend).toBe(true);
});

test('Oura adds clickable reviewed-transition lines without horizontal scrolling',()=>{
  const onTransition=jest.fn(),listeners={};
  Plotly.react.mockImplementationOnce(node=>{node.on=(name,fn)=>listeners[name]=fn;node.removeListener=jest.fn();});
  const event={id:'selected',number:1,time:Date.parse('2026-08-03T18:00:00Z')/1000,label:'Group D',settings:{group:[],left:[],right:[]}};
  render({transitions:[event],onTransition});
  const [node,,layout]=Plotly.react.mock.calls.at(-1);
  expect(layout.shapes).toHaveLength(3);expect(layout.annotations[0].name).toBe('selected');expect(layout.annotations[0].xanchor).toBe('right');
  expect(layout.margin.t).toBe(110);expect(node.style.minWidth).toBe('0');
  listeners.plotly_clickannotation({annotation:{name:'selected'}});expect(onTransition).toHaveBeenCalledWith('selected');
  render({transitions:[],onTransition});expect(node.removeListener).toHaveBeenCalled();expect(Plotly.react.mock.calls.at(-1)[2].annotations).toEqual([]);
});
