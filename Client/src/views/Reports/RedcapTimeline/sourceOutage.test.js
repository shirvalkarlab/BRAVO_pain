import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {SessionController} from 'database/session-control';
import RedcapTimeline from './index';

jest.mock('./requestScope',()=>({cacheScope:()=> 'synthetic-outage-account'}));
const mockDispatch=jest.fn();
jest.mock('database/session-control',()=>({SessionController:{query:jest.fn()}}));
jest.mock('react-router-dom',()=>({useParams:()=>({participant_uid:'synthetic-outage'})}));
jest.mock('context.js',()=>({usePlatformContext:()=>[{},mockDispatch],setContextState:jest.fn()}));
jest.mock('layouts/DatabaseLayout',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDBox',()=>({__esModule:true,default:({children})=><div>{children}</div>}));
jest.mock('components/MDTypography',()=>({__esModule:true,default:({children})=><span>{children}</span>}));
// Keep real page components and source hooks; only replace Plotly render surfaces.
jest.mock('./MultimodalChart',()=>({__esModule:true,default:()=>null}));
jest.mock('./HomeNeuralChart',()=>({__esModule:true,default:()=>null,NeuralLegend:()=>null,NeuralSensingIntervals:()=>null}));
jest.mock('./OuraChart',()=>({__esModule:true,default:()=>null}));
jest.mock('./NeuralChart',()=>({__esModule:true,default:()=>null}));
jest.mock('./MetricChart',()=>({__esModule:true,default:()=>null}));
jest.mock('./ComparisonChart',()=>({__esModule:true,default:()=>null}));

test('real independent hooks render successful wearable and native responses while survey service rejects',async()=>{
 global.IS_REACT_ACT_ENVIRONMENT=true;
 SessionController.query.mockImplementation(endpoint=>{
   if(endpoint==='/api/queryRedcapTimeline')return Promise.reject({response:{status:503}});
   if(endpoint==='/api/queryOuraTimeline')return Promise.resolve({data:{metrics:[],message:'Synthetic wearable source connected'}});
   if(endpoint==='/api/queryHomeNeuralTimeline')return Promise.resolve({data:{windows:[],visit_days:[],message:'Synthetic native source connected'}});
   throw new Error(`Unexpected endpoint: ${endpoint}`);
 });
 const element=document.createElement('div');document.body.appendChild(element);const root=createRoot(element);
 try{
   await act(async()=>root.render(<RedcapTimeline/>));
   expect(element.textContent).toContain('The REDCap timeline could not be loaded');
   expect(element.textContent).toContain('Synthetic wearable source connected');
   expect(element.textContent).toContain('Synthetic native source connected');
   for(const label of ['Oura','Neural Data']){
     const tab=[...element.querySelectorAll('[role="tab"]')].find(node=>node.textContent===label);
     await act(async()=>tab.dispatchEvent(new MouseEvent('click',{bubbles:true})));
     expect(element.textContent).toContain(label==='Oura'?'Synthetic wearable source connected':'Synthetic native source connected');
   }
   expect(new Set(SessionController.query.mock.calls.map(call=>call[0]))).toEqual(new Set(['/api/queryRedcapTimeline','/api/queryOuraTimeline','/api/queryHomeNeuralTimeline']));
 }finally{act(()=>root.unmount());element.remove();}
});
