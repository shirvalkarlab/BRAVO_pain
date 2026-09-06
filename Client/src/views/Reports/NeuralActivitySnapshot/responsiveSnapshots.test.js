import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import ChronicSnapshots from './ChronicSnapshots';
import SnapshotPSDs from './SnapshotPSDs';

const mockManagers=[],mockResize={};
jest.mock('react-resize-detector',()=>({useResizeDetector:options=>{mockResize.current=options.onResize;return {ref:require('react').useRef(null)};}}));
jest.mock('context',()=>({usePlatformContext:()=>[{language:'en'},jest.fn()]}));
jest.mock('@mui/material',()=>({Grid:({children})=><div>{children}</div>}));
jest.mock('components/MDBox',()=>require('react').forwardRef(({children,id,style},ref)=><div ref={ref} id={id} style={style}>{children}</div>));
jest.mock('assets/translation',()=>({dictionary:{FigureStandardText:{},FigureStandardUnit:{}},dictionaryLookup:(_,key)=>key}));
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
jest.mock('graphing-utility/Plotly',()=>({PlotlyRenderManager:class {
  constructor(name){this.divName=name;this.fresh=true;this.traces=[];this.layout={};mockManagers.push(this);}
  subplots=jest.fn(()=>[{}]); clearData=jest.fn();setAxisProps=jest.fn();setYlabel=jest.fn();setXlabel=jest.fn();setScaleType=jest.fn();setTickValue=jest.fn();setYlim=jest.fn();setXlim=jest.fn();setSubtitle=jest.fn();
  setLayoutProps=jest.fn(props=>{this.layout={...this.layout,...props};});
  shadedErrorBar=jest.fn();bar=jest.fn();render=jest.fn();refresh=jest.fn();
}}));

let root,element;
beforeEach(()=>{global.IS_REACT_ACT_ENVIRONMENT=true;mockManagers.length=0;element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});

test.each([ChronicSnapshots,SnapshotPSDs])('both snapshot managers adapt to panel width without changing supplied spectra (%#)',async Component=>{
  const data=[{Date:'2025-08-01',DateTimestamp:100,Frequency:[0,22,100],Power:[1,2,3],stdPower:[0.1,0.2,0.3],ChannelName:'Demo: Left GPi E01-E02'}];
  const before=JSON.stringify(data);
  await act(async()=>root.render(<Component figureTitle="synthetic-spectrum" dataToRender={data} monopolarEstimate={false}/>));
  expect(mockManagers).toHaveLength(2);
  act(()=>mockResize.current(390));
  for(const manager of mockManagers){expect(manager.refresh).toHaveBeenCalled();expect(manager.layout.width).toBeUndefined();expect(manager.layout.margin.l).toBe(60);}
  expect(mockManagers[0].shadedErrorBar.mock.calls.at(-1).slice(0,2)).toEqual([[0,22,100],[1,2,3]]);
  for(const id of ['synthetic-spectrum','synthetic-spectrum_Boxplot'])expect(document.getElementById(id).style.minWidth).toBe('0');
  act(()=>mockResize.current(1100));
  expect(mockManagers[0].layout.legend.orientation).toBe('h');
  expect(JSON.stringify(data)).toBe(before);
});
