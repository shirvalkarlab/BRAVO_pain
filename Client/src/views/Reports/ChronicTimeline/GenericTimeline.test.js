import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import GenericTimeline, {prepareTimelineData} from './GenericTimeline';
import StatisticalTable from './StatisticalTable';
import {PlotlyRenderManager} from 'graphing-utility/Plotly';
import {annotationValues} from 'graphing-utility/annotationValues';

jest.mock('components/MDBox', () => ({__esModule:true, default:require('react').forwardRef(({children, id}, ref) => <div id={id} ref={ref}>{children}</div>)}));
jest.mock('components/MDTypography', () => ({__esModule:true, default:({children}) => <span>{children}</span>}));
jest.mock('components/MDButton', () => ({__esModule:true, default:({children}) => <button>{children}</button>}));
jest.mock('context', () => ({usePlatformContext:() => [{language:'en'}]}));
jest.mock('react-resize-detector', () => ({useResizeDetector:() => ({ref:null})}));
jest.mock('graphing-utility/annotationValues', () => ({annotationValues:jest.fn(jest.requireActual('graphing-utility/annotationValues').annotationValues)}));
jest.mock('graphing-utility/Plotly', () => ({PlotlyRenderManager:jest.fn().mockImplementation(() => {
  const fig={fresh:true, ax:[], layout:{}, plot:jest.fn(), scatter:jest.fn(), setYlabel:jest.fn(),
    setSubtitle:jest.fn(), setLegend:jest.fn(), setLayoutProps:jest.fn(), setYlim:jest.fn(),
    setScaleType:jest.fn(), setAxisProps:jest.fn(), clearData:jest.fn(), refresh:jest.fn(),
    onClick:jest.fn(), render:jest.fn(() => {fig.fresh=false;})};
  fig.subplots=n => (fig.ax=Array.from({length:n},(_,i)=>({id:String(i),xaxis:'x',yaxis:'y'+i,ylayout:'yaxis'+i})));
  fig.setSubplotId=ids => fig.ax.forEach((ax,i)=>{ax.id=ids[i];});
  fig.getAxes=id => fig.ax.find(ax=>ax.id===id);
  fig.addDualYAxis=ax=>{const dual={...ax,ylayout:'yaxisOverlay'};fig.ax.push(dual);return dual;};
  return fig;
})}));
const timeline=(names,values,time=[1,2,3])=>({AnalysisType:'CustomizedTimelineData',ChannelNames:names,ChannelUnits:names.map(()=>'Power'),Time:time,Duration:1,Data:values});

test('unselected streams are not decoded and selected missing values remain gaps',()=>{
  const hidden={ChannelNames:['Oura'],get Time(){throw new Error('Unselected stream accessed');}};
  const selected=timeline(['L GPi','R VIM'],[[0,null,4],[10,20,30]]);
  const out=prepareTimelineData([hidden,selected],['L GPi']);
  expect(out).toHaveLength(1);
  expect(out[0].y).toEqual([0,0,null,null,4,4]);
  expect(out[0].x.map(d=>d.getTime())).toEqual([1000,2000,2000,3000,3000,4000]);
  expect(out[0].range).toEqual([0,4]);
  expect(out[0].options.connectgaps).toBe(false);
  expect(selected.Data[0]).toEqual([0,null,4]);
});

test('dense traces retain all samples and every recording separator',()=>{
  const count=3000, time=Array.from({length:count},(_,i)=>i), values=time.map(i=>i===10?null:i-20);
  const out=prepareTimelineData([timeline(['L GPi'],[values],time),timeline(['L GPi'],[values],time)],['L GPi']);
  expect(out).toHaveLength(1);
  expect(out[0].options.type).toBe('scattergl');
  expect(out[0].y).toHaveLength(count*4+2);
  expect(out[0].y.slice(20,22)).toEqual([null,null]);
  expect(out[0].x[count*2]).toBeNull();
  expect(out[0].x[count*4+1]).toBeNull();
  expect(out[0].range).toEqual([-20,count-21]);
});

test('survey markers retain zero and spectrum matrices are reused without data reduction',()=>{
  const matrix=[[1,2],[3,4]];
  const data=[{AnalysisType:'CustomizedSurveyData',ChannelNames:['Pain','Empty'],Time:[1,2,3],Data:[[0,null,5],[null,null,null]]},
    {AnalysisType:'ChronicSpectrum',ChannelNames:['Spectrum','Hidden'],Time:[[1,2],[]],Frequency:[[10,20],[]],Data:[matrix,[]],CLim:[[-3,3],[]]}];
  const out=prepareTimelineData(data,['Pain','Empty','Spectrum']);
  expect(out.map(s=>s.axName)).toEqual(['Pain','Spectrum']);
  expect(out[0].y).toEqual([0,5]);
  expect(out[0].range).toEqual([0,5]);
  expect(out[1].z).toBe(matrix);
});

const createFigure = PlotlyRenderManager.getMockImplementation();
let root, element;
beforeEach(()=>{PlotlyRenderManager.mockImplementation(createFigure);annotationValues.mockImplementation(jest.requireActual('graphing-utility/annotationValues').annotationValues);global.IS_REACT_ACT_ENVIRONMENT=true; element=document.createElement('div');document.body.appendChild(element);root=createRoot(element);});
afterEach(()=>{act(()=>root.unmount());element.remove();});

test('overlay changes reuse prepared neural arrays and switching sources draws only selected channels',async()=>{
  const data=[timeline(['Neural'],[[0,null,4]]),{AnalysisType:'CustomizedSurveyData',ChannelNames:['Pain'],Time:[1,2,3],Data:[[1,2,3]]}];
  const props={data,availableChannels:{active:['Neural'],options:['Neural','Pain']},annotations:[{Date:2,Duration:0,Id:'event',Name:'Pain event'}],updateColor:jest.fn(),figureTitle:'test-timeline'};
  await act(async()=>root.render(<GenericTimeline {...props} showEventOverlays={false}/>));
  const fig=PlotlyRenderManager.mock.results.at(-1).value;
  const neural=fig.plot.mock.calls.at(-1)[1];
  fig.plot.mockClear();
  await act(async()=>root.render(<GenericTimeline {...props} showEventOverlays={true}/>));
  expect(fig.plot.mock.calls[0][1]).toBe(neural);
  expect(fig.ax.filter(ax=>ax.annotationOverlay)).toHaveLength(1);
  fig.plot.mockClear();
  await act(async()=>root.render(<GenericTimeline {...props} availableChannels={{...props.availableChannels,active:['Pain']}} showEventOverlays={false}/>));
  expect(fig.plot).not.toHaveBeenCalled();
  expect(fig.scatter.mock.calls.at(-1)[1]).toEqual([1,2,3]);
  expect(fig.ax.map(ax=>ax.id)).toEqual(['Pain']);
});

test('interval summaries are unchanged and are not recomputed for unrelated rerenders',async()=>{
  annotationValues.mockClear();
  const data=[timeline(['Neural'],[[0,2,4]],[1,2,3])], annotations=[{Date:0,Duration:4,Name:'Interval',Id:'a'},{Date:1,Duration:0,Name:'Point',Id:'b'}];
  const active=['Neural'], props={data,annotations,availableChannels:{active,options:active}};
  await act(async()=>root.render(<StatisticalTable {...props}/>));
  expect(element.textContent).toContain('2.00 ± 2.00');
  expect(element.textContent).not.toContain('Point');
  expect(annotationValues).toHaveBeenCalledTimes(1);
  await act(async()=>root.render(<StatisticalTable {...props} availableChannels={{active,options:['Neural','Other']}}/>));
  expect(annotationValues).toHaveBeenCalledTimes(1);
  await act(async()=>root.render(<StatisticalTable {...props} availableChannels={{active:['Other'],options:['Other']}}/>));
  expect(annotationValues).toHaveBeenCalledTimes(2);
  expect(element.textContent).not.toContain('Interval');
});

test('categorical channels retain transitions, variable durations, gaps and source boundaries',()=>{
  const first={AnalysisType:'CustomizedTimelineData',ChannelNames:['Sleep','State'],ChannelUnits:['Category','Category'],
    Time:[1,2,6],Duration:[1,2,1],Data:[['light','light','wake'],['rest','active','rest']]};
  const second={AnalysisType:'CustomizedTimelineData',ChannelNames:['Sleep'],ChannelUnits:['Category'],
    Time:[10],Duration:[2],Data:[['light']]};
  const before=JSON.stringify([first,second]);
  const out=prepareTimelineData([first,second],['Sleep','State']);
  expect(out.map(series=>[series.axName,series.type])).toEqual([['Sleep','bar'],['State','bar']]);
  expect(out[0].x).toEqual([3000,1000,2000]);
  expect(out[0].y).toEqual(['light','wake','light']);
  expect(out[0].base.map(date=>date.getTime())).toEqual([1000,6000,10000]);
  expect(out[1].x).toEqual([1000,2000,1000]);
  expect(out[1].y).toEqual(['rest','active','rest']);
  expect(out[1].base.map(date=>date.getTime())).toEqual([1000,2000,6000]);
  expect(JSON.stringify([first,second])).toBe(before);
});

test('variable numeric windows preserve valid zero while wholly missing channels remain absent',()=>{
  const source={...timeline(['Value','Missing'],[[null,0],[null,Infinity]],[10,20]),Duration:[2,5]};
  const out=prepareTimelineData([source],['Value','Missing']);
  expect(out.map(series=>series.axName)).toEqual(['Value']);
  expect(out[0].x.map(date=>date.getTime())).toEqual([10000,12000,20000,25000]);
  expect(out[0].y).toEqual([null,null,0,0]);
  expect(out[0].range).toEqual([0,0]);
  expect(out[0].options.connectgaps).toBe(false);
});

test('unselected survey fields and unsupported stream types cannot leak into displayed measurements',()=>{
  const rows=[[0,3]];
  Object.defineProperty(rows,1,{get(){throw new Error('Unselected survey field read');}});
  const survey={AnalysisType:'CustomizedSurveyData',ChannelNames:['Pain','Hidden'],Time:[1,3],Data:rows};
  const unsupported={AnalysisType:'FutureUnknownType',ChannelNames:['Pain'],get Time(){throw new Error('Unsupported stream decoded');}};
  const out=prepareTimelineData([survey,unsupported],['Pain']);
  expect(out).toHaveLength(1);
  expect(out[0].type).toBe('scatter');
  expect(out[0].y).toEqual([0,3]);
  expect(out[0].x.map(date=>date.getTime())).toEqual([1000,3000]);
});
