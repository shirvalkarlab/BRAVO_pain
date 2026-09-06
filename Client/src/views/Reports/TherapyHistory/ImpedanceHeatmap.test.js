import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import ImpedanceHeatmap from './ImpedanceHeatmap';

const mockManagers=[],mockResize={};
jest.mock('react-resize-detector',()=>({useResizeDetector:options=>{mockResize.current=options.onResize;return {ref:require('react').useRef(null)};}}));
jest.mock('context',()=>({usePlatformContext:()=>[{language:'en'},jest.fn()]}));
jest.mock('components/MDBox',()=>require('react').forwardRef(({children,id,style},ref)=><div ref={ref} id={id} style={style}>{children}</div>));
jest.mock('assets/translation',()=>({dictionary:{},dictionaryLookup:jest.fn()}));
jest.mock('graphing-utility/Plotly',()=>({PlotlyRenderManager:class {
  constructor(){this.layout={annotations:[]};this.axes=[{id:0},{id:1}];this.coloraxis=[];mockManagers.push(this);}
  clearData=jest.fn(()=>{this.layout.annotations=[];});
  subplots=jest.fn();getAxes=()=>this.axes;getColorAxis=()=>this.coloraxis;
  createColorAxis=jest.fn(options=>{this.coloraxis.push(options);return this.coloraxis.length;});
  setColorAxis=jest.fn((_,axis)=>{this.coloraxis=this.coloraxis.filter(item=>item!==axis);});
  setLayoutProps=jest.fn(props=>{this.layout={...this.layout,...props};});
  surf=jest.fn();setSubtitle=jest.fn(text=>{this.layout.annotations.push({text});});setAxisProps=jest.fn();render=jest.fn();refresh=jest.fn();purge=jest.fn();
}}));

test('resizing stacks the same two impedance matrices without changing contacts, measurements or color limits',()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;
  const element=document.createElement('div'),root=createRoot(element);
  const left=[[0,100,200,300],[100,0,200,300],[200,200,0,300],[300,300,300,0]],right=left.map(row=>row.map(value=>value*2));
  const data=[{Recording:[{Metadata:{Left:{Bipolar:left},Right:{Bipolar:right}}}]}],before=JSON.stringify(data);
  act(()=>root.render(<ImpedanceHeatmap dataToRender={data} figureTitle="synthetic-impedance" logType="Bipolar" height={420} onContactSelect={()=>{}}/>));
  const manager=mockManagers[0];
  act(()=>mockResize.current(390));
  expect(manager.subplots).toHaveBeenLastCalledWith(2,1,expect.any(Object));
  expect(manager.surf.mock.calls.at(-2)[2]).toBe(left);
  expect(manager.surf.mock.calls.at(-1)[2]).toBe(right);
  expect(manager.createColorAxis.mock.calls.at(-1)[0]).toMatchObject({colorscale:'Jet',clim:[0,6000]});
  expect(manager.coloraxis).toHaveLength(2);
  expect(element.querySelector('#synthetic-impedance').style.minWidth).toBe('0');
  expect(manager.layout.annotations.map(annotation=>annotation.font.size)).toEqual([14,14]);
  act(()=>mockResize.current(1100));
  expect(manager.subplots).toHaveBeenLastCalledWith(1,2,expect.any(Object));
  expect(manager.surf.mock.calls.at(-2)[2]).toBe(left);
  expect(manager.coloraxis).toHaveLength(2);
  expect(JSON.stringify(data)).toBe(before);
  act(()=>root.unmount());
});
