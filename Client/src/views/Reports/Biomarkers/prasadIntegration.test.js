import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import {ThemeProvider} from '@mui/material/styles';
import {PlatformContextProvider} from 'context';
import theme from 'assets/theme';
import Plotly from 'plotly.js-dist';
import {computeMatchedScanModel} from './binarizationModel';
import {resolveStability,stabilityNumbers,ValidationReadout} from './BiomarkerAnalytics';
import {resolutionOf,FigurePanel} from '../StimOptimizer';
import {commitBandCandidate,downloadBandCandidate} from '../ClosedLoopSim/bandCandidateStore';
const mockQuery=jest.fn();
jest.mock('./queryAnalysis',()=>({useAnalysisQuery:()=>mockQuery}));
jest.mock('../ClosedLoopSim/bandCandidateStore',()=>({commitBandCandidate:jest.fn(),downloadBandCandidate:jest.fn()}));
let mockWidth=390;
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
jest.mock('react-resize-detector',()=>({useResizeDetector:()=>({ref:require('react').useRef(null),width:mockWidth})}));
function View(props){return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}><FigurePanel {...props}/></PlatformContextProvider></ThemeProvider>;}
beforeEach(()=>{jest.clearAllMocks();mockWidth=390;});

test('missing matching inputs are unassessed, distinct from a measured zero-match result',()=>{
  const scanIndex=[{t:1000,channel:'LEFT',source:'td'}];
  for(const scan of [undefined,[],{}]){
    const missing=computeMatchedScanModel({scanIndex:scan,toleranceMin:1});
    expect(missing).toMatchObject({matchable:false,unmatchableReason:'no_scan_index',painMatched:[],matchedValues:[]});
  }
  for(const painSeries of [undefined,{}, {t:[]}]) expect(computeMatchedScanModel({scanIndex,painSeries})).toMatchObject({matchable:false,unmatchableReason:'no_pain_series'});
  const noPair=computeMatchedScanModel({scanIndex,painSeries:{t:[10000],y:[7]},toleranceMin:1});
  expect(noPair).toMatchObject({matchable:true,unmatchableReason:null,matchedValues:[],painMatched:[false],counts:{n_sessions:1,n_matched:0}});
  const paired=computeMatchedScanModel({scanIndex,painSeries:{t:[1001],y:[7]},toleranceMin:1});
  expect(paired).toMatchObject({matchable:true,unmatchableReason:null,matchedValues:[7],painMatched:[true]});
});

test('stability distinguishes equivalence, demonstrated differences, inconclusive and untested results',()=>{
  for(const v of ['stable','stim-dependent','inconclusive']){
    expect(resolveStability({stability_verdict:v})).toEqual({key:v,why:null});
    expect(resolveStability({stability_verdict:v,equivalence:{reason:'Measured evidence'}})).toEqual({key:v,why:'Measured evidence'});
  }
  expect(resolveStability(null)).toMatchObject({key:'not_tested'});
  expect(resolveStability({available:false,reason:'Only one era'})).toEqual({key:'not_tested',why:'Only one era'});
  expect(resolveStability({available:false})).toMatchObject({key:'not_tested'});
  expect(resolveStability({stim_stable:true}).key).toBe('not_tested');
  expect(resolveStability({stim_stable:false}).key).toBe('not_tested');
  expect(resolveStability({stability_verdict:'unexpected'}).key).toBe('not_tested');
});

test('stability numeric text reports the declared scale, interval and measured era count without filling missing evidence',()=>{
  expect(stabilityNumbers(null)).toBeNull();expect(stabilityNumbers({})).toBeNull();
  expect(stabilityNumbers({margin_log_or:NaN,max_abs_diff_log_or:Infinity})).toBeNull();
  const complete=stabilityNumbers({margin_log_or:Math.log(2),max_abs_diff_log_or:Math.log(1.2),ci:[0,Math.log(1.4)],ci_level:.95,pair:'A/B',n_eras_compared:2});
  expect(complete).toContain('factor of 1.20 in odds (A/B), 95% interval 1.00 to 1.40');expect(complete).toContain('margin: a factor of 2.00');expect(complete).toContain('2 eras');
  expect(stabilityNumbers({max_abs_diff_log_or:0,n_eras_compared:1})).toContain('1 era had');
  expect(stabilityNumbers({margin_log_or:0})).toBe('declared equivalence margin: a factor of 1.00.');
  expect(stabilityNumbers({max_abs_diff_log_or:0,ci:[0,0]})).toContain('interval 1.00 to 1.00');
  expect(stabilityNumbers({max_abs_diff_log_or:0,ci:[null,0]})).not.toContain('interval');
});

test('optimizer uses served three-state verdict and reports declared margin rather than deriving a recommendation',()=>{
  const comparison={gain:4,sd_of_difference:1,k:2};
  expect(resolutionOf({comparison,optimum_resolved:true})).toMatchObject({state:'resolved',gain:4,sdDiff:1,k:2,derivedLocally:false});
  expect(resolutionOf({comparison,optimum_resolved:false})).toMatchObject({state:'unresolved'});
  expect(resolutionOf({comparison,optimum_resolved:false}).why).toContain('2 standard deviations');
  for(const optimum_resolved of [null,undefined,'true'])expect(resolutionOf({comparison,optimum_resolved})).toMatchObject({state:'undeterminable'});
  expect(resolutionOf(null)).toMatchObject({state:'undeterminable',gain:null,sdDiff:null,k:null});
  expect(resolutionOf({comparison:{gain:1,sd_of_difference:2},optimum_resolved:false}).why).toContain('value not recorded');
  expect(resolutionOf({comparison:{gain:'',sd_of_difference:false,k:'2'}})).toMatchObject({gain:null,sdDiff:null,k:null});
  const legacy={optimum:{posterior_mean:1,posterior_sd:3},incumbent_mu:4,incumbent_sd:4,optimum_resolved:false};
  expect(resolutionOf(legacy)).toMatchObject({gain:3,sdDiff:5,derivedLocally:true,state:'unresolved'});expect(resolutionOf(legacy).why).toContain('reconstructed');
  expect(resolutionOf({...legacy,optimum:{posterior_mean:1,posterior_sd:0},incumbent_sd:0})).toMatchObject({gain:3,sdDiff:null,derivedLocally:false});
  expect(resolutionOf({...legacy,incumbent_mu:null})).toMatchObject({gain:null,sdDiff:null});
  expect(resolutionOf({...legacy,incumbent_sd:null})).toMatchObject({gain:null,sdDiff:null});
  expect(resolutionOf({...legacy,optimum:{posterior_mean:null,posterior_sd:1}})).toMatchObject({gain:null,sdDiff:null});
  expect(resolutionOf({...legacy,optimum:{posterior_mean:1,posterior_sd:null}})).toMatchObject({gain:null,sdDiff:null});
  expect(resolutionOf({comparison:{gain:null,sd_of_difference:2,k:NaN}})).toMatchObject({gain:null,sdDiff:null,k:null});
  expect(resolutionOf({...legacy,optimum:{posterior_mean:1,posterior_sd:1e308}}).sdDiff).toBeNull();
});

test('optimizer figures preserve responsive adaptation and update without purging before final unmount',()=>{
  const figure={data:[{type:'scatter',x:[1,2],y:[3,4]}],layout:{height:450,width:1000,xaxis:{title:'Time'},yaxis:{title:'Observed value'}}};
  const view=render(<View title="Surface" blurb="Observed comparison" figure={figure} prominence="primary"/>);
  const node=screen.getByRole('region',{name:'Surface'}).firstChild;
  expect(node).toBe(Plotly.react.mock.calls.at(-1)[0]);expect(getComputedStyle(node).minWidth).toBe("0");
  expect(Plotly.react.mock.calls.at(-1)[2].width).not.toBe(1000);expect(Plotly.react.mock.calls.at(-1)[2].height).toBeGreaterThanOrEqual(620);expect(Plotly.purge).not.toHaveBeenCalled();
  mockWidth=1200;view.rerender(<View title="Surface" figure={{...figure,data:[{type:'scatter',x:[1,2],y:[5,6]}]}}/>);
  expect(Plotly.react.mock.calls.at(-1)[1][0].y).toEqual([5,6]);expect(Plotly.purge).not.toHaveBeenCalled();
  view.unmount();expect(Plotly.purge).toHaveBeenCalledWith(node);
});

test('failed optimizer figure has an explicit error state; absent unrequested figure is quiet',()=>{
  const view=render(<View title="Surface" error={{error_type:'ValueError',message:'Insufficient observations',builder:'example'}}/>);
  expect(screen.getByText(/ValueError: Insufficient observations/)).toBeTruthy();expect(screen.getByText(/Builder: example/)).toBeTruthy();expect(Plotly.react).not.toHaveBeenCalled();
  view.rerender(<View title="Surface" error={{}}/>);expect(screen.getByText(/Error: no message supplied/)).toBeTruthy();
  view.rerender(<View title="Surface"/>);expect(screen.queryByText('Surface')).toBeNull();
});

function Validation(props){return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}><ValidationReadout {...props}/></PlatformContextProvider></ThemeProvider>;}
test('validation headline does not promote an inconclusive or dependent result to stable',()=>{
  const result={available:true,verdict:'VALIDATED (stim-stable)',glmer:{available:true,odds_ratio:1.5,p:.01,n:20,n_clusters:4},stim:{available:true,stability_verdict:'inconclusive'}};
  const view=render(<Validation validation={result}/>);
  expect(screen.getByText('VALIDATED (stim stability not determinable)')).toBeTruthy();
  view.rerender(<Validation validation={{...result,stim:{available:true,stability_verdict:'stim-dependent'}}}/>);
  expect(screen.getByText('VALIDATED (stim-dependent)')).toBeTruthy();expect(screen.queryByText('VALIDATED (stim stability not tested)')).toBeNull();
  view.rerender(<Validation validation={{...result,stim:{available:true,stability_verdict:'stable'}}}/>);expect(screen.getByText('VALIDATED (stim-stable)')).toBeTruthy();
});

test('band commit preserves reviewed input manifest and request settings while notifying relocated calibration panels',async()=>{
  const candidate={channel:'ZERO_THREE_LEFT',center_hz:10},manifest={revision:'clean-v2'},requestParams={LabelMetric:'nrs',MatchToleranceMin:60};
  mockQuery.mockResolvedValue({status:200,data:{available:true,band_candidate:candidate,InputManifest:manifest}});
  const onCommitted=jest.fn();
  render(<Validation validation={{available:true,verdict:'VALIDATED',glmer:{},stim:{}}} emitContext={{participantUid:'synthetic',channelRaw:'ZERO_THREE_LEFT',centerHz:10,bandWidthHz:5,requestParams}} onCommitted={onCommitted}/>);
  fireEvent.click(screen.getByRole('button',{name:/Commit this band/}));
  await waitFor(()=>expect(onCommitted).toHaveBeenCalledWith(candidate));
  expect(mockQuery).toHaveBeenCalledWith('/api/emitBandCandidate',{ParticipantId:'synthetic',Channel:'ZERO_THREE_LEFT',CenterHz:10,BandWidthHz:5,...requestParams});
  for(const save of [commitBandCandidate,downloadBandCandidate])expect(save).toHaveBeenCalledWith('synthetic',candidate,{InputManifest:manifest,requestParams});
});
