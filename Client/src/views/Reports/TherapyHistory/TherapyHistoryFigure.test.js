import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import TherapyHistoryFigure from './TherapyHistoryFigure';

const mockManagers=[],mockResize={};
jest.mock('react-resize-detector',()=>({useResizeDetector:options=>{mockResize.current=options.onResize;return {ref:require('react').useRef(null)};}}));
jest.mock('context',()=>({usePlatformContext:()=>[{language:'en'},jest.fn()]}));
jest.mock('components/MDBox',()=>require('react').forwardRef(({children,id,style},ref)=><div ref={ref} id={id} style={style}>{children}</div>));
jest.mock('components/MDTypography',()=>({children})=><span>{children}</span>);
jest.mock('@mui/material',()=>({Card:({children,onClick})=><button onClick={onClick}>{children}</button>,Grid:({children})=><div>{children}</div>}));
jest.mock('assets/translation',()=>({dictionary:{TherapyHistory:{Figure:{}}},dictionaryLookup:()=> 'Therapy change log'}));
jest.mock('graphing-utility/Plotly',()=>({PlotlyRenderManager:class {
  constructor(){this.layout={xaxis:{},yaxis:{}};this.fresh=true;this.renders=[];mockManagers.push(this);}
  clearData=jest.fn();subplots=jest.fn();setXlabel=jest.fn();setTitle=jest.fn();setLegend=jest.fn();
  setAxisProps=(props,axis)=>{Object.assign(this.layout[axis+'axis'],props);};
  setLayoutProps=props=>{for(const key of Object.keys(props)){this.layout[key]=Array.isArray(props[key])?props[key]:(typeof props[key]==='object'?{...this.layout[key],...props[key]}:props[key]);}};
  setTickValue=jest.fn();setTickLabel=jest.fn();setYlim=jest.fn();
  setXlim=range=>{this.layout.xaxis.range=range;};
  render=()=>{this.renders.push(JSON.parse(JSON.stringify(this.layout)));this.fresh=false;};
  refresh=jest.fn();onClick=()=>{};
}}));
const device=id=>({Id:id,Name:`Device ${id}`,Date:1700000000});
const dataset=ids=>({TherapyDevices:ids.map(device),TherapyModification:ids.map(id=>({Device:device(id),History:[
  {Type:'TherapyChangeGroup',Date:1710000000,Previous:'GroupIdDef.GROUP_A',New:'GroupIdDef.GROUP_B'},
  {Type:'TherapyChangeGroup',Date:1720000000,Previous:'GroupIdDef.GROUP_B',New:'GroupIdDef.GROUP_C'},
]}))});
let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockManagers.length=0;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});
const render=data=>act(()=>root.render(<TherapyHistoryFigure dataToRender={data} height={400} figureTitle="history-test" onTimeClick={()=>{}}/>));

test('first graph render contains dated group intervals instead of an empty default date axis',()=>{
  const data=dataset(['one']);const before=JSON.stringify(data);render(data);
  const first=mockManagers[0].renders[0];
  expect(first.shapes).toHaveLength(1);
  expect(first.shapes[0].x0).toBe(new Date(1710000000*1000).toISOString());
  expect(first.xaxis.range).toEqual([new Date(1710000000*1000).toISOString(),new Date(1720000000*1000).toISOString()]);
  expect(first.xaxis.autorange).toBe(false);
  act(()=>mockResize.current(390));
  const narrow=mockManagers[0].renders.at(-1);
  expect(narrow.shapes).toEqual(first.shapes);
  expect(narrow.xaxis.range).toEqual(first.xaxis.range);
  expect(narrow.margin.l).toBe(75);
  expect(JSON.stringify(data)).toBe(before);
});

test('late-arriving devices are selected and existing user visibility choices survive data refresh',()=>{
  render(dataset([]));render(dataset(['one','two']));
  const manager=mockManagers[0];expect(manager.renders.at(-1).shapes).toHaveLength(2);
  act(()=>[...element.querySelectorAll('button')].find(button=>button.textContent.includes('Device one')).click());
  expect(manager.renders.at(-1).shapes).toHaveLength(1);
  render(dataset(['one','two','three']));
  expect(manager.renders.at(-1).shapes).toHaveLength(2);
  render(dataset(['one','three']));expect(manager.renders.at(-1).shapes).toHaveLength(1);
});
