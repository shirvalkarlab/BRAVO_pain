import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import ComparisonChart from './ComparisonChart';
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
const originalObserver=global.IntersectionObserver;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;delete global.IntersectionObserver;Plotly.react.mockClear();Plotly.purge.mockClear();});
afterEach(()=>{global.IntersectionObserver=originalObserver;});
test('comparison renderer passes exact traces/layout, updates in place and cleans up its Plotly node',()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;const element=document.createElement('div'),root=createRoot(element);
  const plot={traces:[{type:'box',y:[1,2,3]}],layout:{height:420,yaxis:{range:[0,10]}}};
  act(()=>root.render(<ComparisonChart plot={plot} label="Program comparison"/>));
  const node=element.querySelector('[role="img"]');expect(node.getAttribute('aria-label')).toBe('Program comparison');
  expect(Plotly.react).toHaveBeenLastCalledWith(node,plot.traces,expect.objectContaining({height:420,font:{family:'Roboto, sans-serif',size:16,color:'#344767'},yaxis:{range:[0,10]}}),expect.objectContaining({responsive:true,displaylogo:false}));
  const next={...plot,traces:[{type:'box',y:[4,5]}]};act(()=>root.render(<ComparisonChart plot={next} label="Program comparison"/>));expect(Plotly.react.mock.calls.at(-1)[1]).toEqual(next.traces);
  act(()=>root.unmount());expect(Plotly.purge).toHaveBeenCalledWith(node);
});

test('offscreen charts reserve space and defer Plotly until near the viewport, then preserve the rendered plot',()=>{
  let notify;const observer={observe:jest.fn(),disconnect:jest.fn()};
  global.IntersectionObserver=jest.fn(callback=>{notify=callback;return observer;});
  const element=document.createElement('div'),root=createRoot(element);
  const plot={traces:[{type:'box',y:[1,2,3]}],layout:{height:1700}};
  act(()=>root.render(<ComparisonChart plot={plot} label="Medication conditions"/>));
  expect(global.IntersectionObserver).toHaveBeenCalledWith(expect.any(Function),{rootMargin:'400px'});
  expect(observer.observe).toHaveBeenCalledWith(element.firstChild);expect(element.firstChild.style.minHeight).toBe('1700px');
  expect(element.querySelector('[role="status"]').textContent).toContain('Scroll to view');expect(Plotly.react).not.toHaveBeenCalled();
  act(()=>notify([{isIntersecting:false}]));expect(Plotly.react).not.toHaveBeenCalled();
  const updated={traces:[{type:'box',y:[7,8]}],layout:{height:1800}};
  act(()=>root.render(<ComparisonChart plot={updated} label="Medication conditions"/>));expect(Plotly.react).not.toHaveBeenCalled();expect(element.firstChild.style.minHeight).toBe('1800px');
  act(()=>notify([{isIntersecting:false},{isIntersecting:true}]));
  expect(Plotly.react).toHaveBeenCalledTimes(1);expect(Plotly.react.mock.calls[0][1]).toEqual(updated.traces);expect(observer.disconnect).toHaveBeenCalledTimes(1);
  const node=element.querySelector('[role="img"]');expect(node).not.toBeNull();expect(element.querySelector('[role="status"]')).toBeNull();
  act(()=>notify([{isIntersecting:false}]));expect(Plotly.purge).not.toHaveBeenCalled();expect(element.querySelector('[role="img"]')).toBe(node);
  const next={...updated,traces:[{type:'box',y:[9]}]};act(()=>root.render(<ComparisonChart plot={next} label="Medication conditions"/>));
  expect(Plotly.react).toHaveBeenCalledTimes(2);act(()=>root.unmount());expect(Plotly.purge).toHaveBeenCalledWith(node);expect(observer.disconnect).toHaveBeenCalledTimes(2);
});

test('unmount before visibility disconnects observation and ignores late callbacks without purging an uncreated plot',()=>{
  let notify;const observer={observe:jest.fn(),disconnect:jest.fn()};
  global.IntersectionObserver=jest.fn(callback=>{notify=callback;return observer;});
  const element=document.createElement('div'),root=createRoot(element);
  act(()=>root.render(<ComparisonChart plot={{traces:[],layout:{}}} label="Pending chart"/>));
  expect(element.firstChild.style.minHeight).toBe('350px');act(()=>root.unmount());act(()=>notify([{isIntersecting:true}]));
  expect(observer.disconnect).toHaveBeenCalledTimes(1);expect(Plotly.react).not.toHaveBeenCalled();expect(Plotly.purge).not.toHaveBeenCalled();expect(element.textContent).toBe('');
});

test('fit-width stimulation plots remove the minimum width and horizontal scroll container',()=>{
  const element=document.createElement('div'),root=createRoot(element);
  act(()=>root.render(<ComparisonChart plot={{traces:[],layout:{height:390},fitWidth:true}} label="Stimulation settings"/>));
  expect(element.firstChild.style.overflowX).toBe('visible');expect(element.querySelector('[role="img"]').style.minWidth).toBe('0');expect(element.querySelector('[role="img"]').style.maxWidth).toBe('100%');
  act(()=>root.unmount());
});

test('container resizing coalesces Plotly resize work and disconnects when a visible chart is removed',()=>{
  const originals={resize:global.ResizeObserver,request:global.requestAnimationFrame,cancel:global.cancelAnimationFrame};
  let notify,frame;
  const observer={observe:jest.fn(),disconnect:jest.fn()};
  global.ResizeObserver=jest.fn(callback=>{notify=callback;return observer;});
  global.requestAnimationFrame=jest.fn(callback=>{frame=callback;return 5;});
  global.cancelAnimationFrame=jest.fn();Plotly.Plots={resize:jest.fn()};
  const element=document.createElement('div'),root=createRoot(element);
  act(()=>root.render(<ComparisonChart plot={{traces:[],minWidth:900,layout:{}}} label="Medication layout"/>));
  const node=element.querySelector('[role="img"]');
  expect(node.style.minWidth).toBe('0');expect(element.firstChild.style.overflowX).toBe('visible');
  act(()=>{notify();frame();});expect(Plotly.Plots.resize).not.toHaveBeenCalled();
  node._fullLayout={};act(()=>{notify();notify();frame();});
  expect(Plotly.Plots.resize).toHaveBeenCalledWith(node);expect(global.cancelAnimationFrame).toHaveBeenCalledWith(5);
  act(()=>root.unmount());expect(observer.disconnect).toHaveBeenCalledTimes(1);
  global.ResizeObserver=originals.resize;global.requestAnimationFrame=originals.request;global.cancelAnimationFrame=originals.cancel;
});

test('medication charts fit 390px with numbered rows and complete wrapping labels, preserving traces and restoring full desktop labels',()=>{
  const originals={resize:global.ResizeObserver,request:global.requestAnimationFrame,cancel:global.cancelAnimationFrame};
  let width=390,notify,frame;
  const geometry=jest.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(()=>({width}));
  const observer={observe:jest.fn(),disconnect:jest.fn()};
  global.ResizeObserver=jest.fn(callback=>{notify=callback;return observer;});
  global.requestAnimationFrame=jest.fn(callback=>{frame=callback;return 5;});global.cancelAnimationFrame=jest.fn();
  const element=document.createElement('div'),root=createRoot(element);
  const rowLabels=['1. Antidepressant medicines · Very long full medicine name <reviewed> 25 mg twice per day with dinner and additional source details','2. Other medicine · 5 mg daily'];
  const plot={traces:[{type:'scatter',x:[1,2],y:[0,1],hovertemplate:'complete unchanged evidence'}],rowLabels,fitWidth:true,layout:{height:350,margin:{l:250,r:35,t:45,b:75},yaxis:{tickvals:[0,1],ticktext:['old truncated…','old 2'],range:[1.6,-1]},xaxis:{type:'date'},annotations:[{text:'Class header'}]}};
  act(()=>root.render(<ComparisonChart plot={plot} label="Medication timeline"/>));
  const mobile=Plotly.react.mock.calls.at(-1);expect(mobile[1]).toBe(plot.traces);expect(mobile[2].margin.l).toBe(40);expect(mobile[2].xaxis.nticks).toBe(4);
  expect(mobile[2].yaxis.ticktext).toEqual(['1','2']);expect(mobile[2].yaxis.tickvals).toEqual([0,1]);expect(mobile[2].annotations).toEqual([]);
  expect(element.textContent).toContain(rowLabels[0]);expect(element.textContent).toContain('numbers match chart rows');expect(element.querySelector('li').textContent).toBe(rowLabels[0]);
  const labels=element.querySelector('[aria-label="Medication timeline complete row labels"]');expect(labels.style.overflowWrap).toBe('anywhere');
  width=1200;act(()=>{notify();frame();});
  const desktop=Plotly.react.mock.calls.at(-1);expect(desktop[2].margin.l).toBe(230);expect(desktop[2].xaxis.nticks).toBe(7);expect(desktop[2].height).toBeGreaterThan(350);
  expect(desktop[2].yaxis.ticktext[0].replace(/<br>/g,' ')).toBe(rowLabels[0].replace('<reviewed>','&lt;reviewed&gt;'));
  expect(desktop[2].yaxis.ticktext[0]).not.toContain('…');expect(desktop[2].annotations).toEqual(plot.layout.annotations);expect(desktop[1]).toBe(plot.traces);
  expect(plot.layout.margin.l).toBe(250);expect(plot.layout.yaxis.ticktext[0]).toBe('old truncated…');
  act(()=>root.unmount());geometry.mockRestore();Object.assign(global,{ResizeObserver:originals.resize,requestAnimationFrame:originals.request,cancelAnimationFrame:originals.cancel});
});
