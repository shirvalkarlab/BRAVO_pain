import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import Plotly from 'plotly.js-dist';
import PainScores from './index';

const mockQuery=jest.fn();
mockQuery.cancel=jest.fn();
jest.mock('../Biomarkers/queryAnalysis',()=>({useAnalysisQuery:()=>mockQuery}));
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
jest.mock('react-router-dom',()=>({useParams:()=>({participant_uid:'synthetic'}),useNavigate:()=>()=>{}}));
jest.mock('context.js',()=>({usePlatformContext:()=>[{},()=>{}],setContextState:()=>{}}));
jest.mock('database/session-control',()=>({SessionController:{displayError:jest.fn()}}));
jest.mock('layouts/DatabaseLayout',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDBox',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children})=><span>{children}</span>}));
jest.mock('components/LoadingProgress',()=>({__esModule:true,default:()=> <span>Loading</span>}));

const payload={n_reports:3,metrics:[
  {key:'nrs',label:'NRS',range:[0,10],points:[{t_epoch:1,v:0},{t_epoch:3,v:5},{t_epoch:10,v:7}]},
  {key:'vas',label:'VAS',range:[0,100],points:[{t_epoch:1,v:0},{t_epoch:3,v:50},{t_epoch:10,v:70}]},
], stages:[{key:'testing',name:'Testing stage',start:'1970-01-01T00:00:00Z',end:'1970-01-01T00:00:05Z',color:'#FF0000'}],
correlation:{labels:['NRS','VAS'],matrix:[[1,1],[1,1]]}};
let root,element,resolve;
beforeEach(()=>{
  global.IS_REACT_ACT_ENVIRONMENT=true;
  element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);
  mockQuery.mockImplementation(()=>new Promise(done=>{resolve=done;}));
  Plotly.react.mockResolvedValue();
});
afterEach(()=>{act(()=>root.unmount());element.remove();});
async function load(){
  await act(async()=>root.render(<PainScores/>));
  expect(Plotly.react).not.toHaveBeenCalled();
  await act(async()=>resolve({data:payload}));
}
async function click(label){
  const button=Array.from(element.querySelectorAll('[role="button"],button')).find(node=>node.textContent===label);
  expect(button).toBeDefined();
  await act(async()=>button.dispatchEvent(new MouseEvent('click',{bubbles:true})));
}

test('asynchronous loading draws each complete chart once and releases its captured node on unmount',async()=>{
  await load();
  expect(mockQuery).toHaveBeenCalledTimes(1);
  expect(Plotly.react).toHaveBeenCalledTimes(4);
  const nodes=Plotly.react.mock.calls.map(call=>call[0]);
  expect(new Set(nodes).size).toBe(4);
  expect(Plotly.purge).not.toHaveBeenCalled();
  act(()=>root.unmount());
  expect(Plotly.purge.mock.calls.map(call=>call[0])).toEqual(expect.arrayContaining(nodes));
  expect(Plotly.purge).toHaveBeenCalledTimes(4);
  expect(nodes.every(node=>!node.isConnected)).toBe(true);
  root=createRoot(element);
});

test('metric toggles update only the normalized overlay while keeping every selected observation',async()=>{
  await load();Plotly.react.mockClear();
  await click('NRS');
  expect(Plotly.react).toHaveBeenCalledTimes(1);
  expect(Plotly.react.mock.calls[0][1].map(trace=>trace.name)).toEqual(['VAS']);
  expect(Plotly.react.mock.calls[0][1][0].y).toEqual([0,0.5,0.7]);
  expect(Plotly.purge).not.toHaveBeenCalled();
  await click('NRS');
  expect(Plotly.react).toHaveBeenCalledTimes(2);
  expect(Plotly.react.mock.calls[1][1].map(trace=>trace.name)).toEqual(['NRS','VAS']);
});

test('stage toggles update the time plots in place and preserve excluded-stage semantics',async()=>{
  await load();Plotly.react.mockClear();
  await click('Testing stage');
  expect(Plotly.react).toHaveBeenCalledTimes(3);
  expect(Plotly.purge).not.toHaveBeenCalled();
  for(const [,traces,layout] of Plotly.react.mock.calls){
    expect(layout.shapes).toEqual([]);
    expect(traces.every(trace=>trace.x.map(date=>date.getTime()).join(',')==='10000')).toBe(true);
    expect(traces.every(trace=>trace.mode==='markers'&&trace.connectgaps===false)).toBe(true);
  }
});
