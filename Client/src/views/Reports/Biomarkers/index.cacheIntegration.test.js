import {render,screen,fireEvent,act} from '@testing-library/react';
import {ThemeProvider} from '@mui/material/styles';
import {PlatformContextProvider} from 'context';
import theme from 'assets/theme';
import Biomarkers from './index';
import StimOptimizer from '../StimOptimizer';
import {useCachedResult} from 'database/useCachedResult';
import {MODULES} from 'database/resultCache';
const mockQuery=jest.fn();
const mockCache={data:null,loading:false,err:null,errRaw:null,stale:false,staleReasons:[],hasCached:false,recompute:jest.fn()};
jest.mock('./queryAnalysis',()=>({useAnalysisQuery:()=>mockQuery}));
jest.mock('react-router-dom',()=>({useNavigate:()=>jest.fn(),useParams:()=>({participant_uid:'synthetic-cache-participant'})}));
jest.mock('database/useCachedResult',()=>({useCachedResult:jest.fn(()=>mockCache)}));
jest.mock('views/Reports/moduleCacheKeys',()=>({recomputeSlots:jest.fn(),markClosedLoopFamilyStale:jest.fn()}));
jest.mock('layouts/DatabaseLayout',()=>({children})=><div>{children}</div>);
jest.mock('./BiomarkerAnalytics',()=>()=>null);
jest.mock('./BiomarkerTimeline',()=>()=>null);
jest.mock('./BiomarkerDataTimeline',()=>()=>null);
jest.mock('./BinarizationPreview',()=>()=>null);
jest.mock('../ClosedLoopSim/PsdLsbPanel',()=>()=> <div>Observed calibration panel</div>);
jest.mock('../ClosedLoopSim/ConversionModelPanel',()=>()=> <div>Model calibration panel</div>);
jest.mock('plotly.js-dist',()=>({react:jest.fn(),purge:jest.fn()}));
function View({children}){return <ThemeProvider theme={theme}><PlatformContextProvider initialStates={{darkMode:false}}>{children}</PlatformContextProvider></ThemeProvider>;}
beforeEach(()=>{jest.clearAllMocks();useCachedResult.mockImplementation(()=>mockCache);localStorage.clear();mockCache.data=null;mockCache.hasCached=false;mockQuery.mockImplementation(()=>Promise.resolve({status:200,data:{}}));mockQuery.cancel=jest.fn();});

test('biomarker compute keys the complete selected request and obtains payloads through completed-response polling',async()=>{
  render(<View><Biomarkers/></View>);
  expect(useCachedResult.mock.calls.at(-1)[0]).toMatchObject({moduleKey:MODULES.biomarkers,uid:'synthetic-cache-participant',enabled:false,autoFetch:false});
  expect(mockQuery.mock.calls.some(([url])=>url==='/api/queryBiomarkerAnalysis')).toBe(false);
  expect(screen.getByText('Observed calibration panel')).toBeTruthy();expect(screen.getByText('Model calibration panel')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:/Start exploratory analysis/}));
  const options=useCachedResult.mock.calls.at(-1)[0];expect(options.enabled).toBe(true);expect(options.settings).toMatchObject({LabelMetric:'nrs',LabelStrategy:'tertile',MatchToleranceMin:60});
  expect(mockCache.recompute).toHaveBeenCalledTimes(1);
  const payload={available:true,InputManifest:{revision:'clean-v3'}};mockQuery.mockResolvedValueOnce({status:200,data:payload});
  await expect(options.fetcher()).resolves.toBe(payload);
  expect(mockQuery).toHaveBeenLastCalledWith('/api/queryBiomarkerAnalysis',{ParticipantId:'synthetic-cache-participant',...options.settings});
  await act(async()=>{});
});

test('optimizer cache keys explicit scientific parameters and uses the canonical completed-response query',async()=>{
  render(<View><StimOptimizer/></View>);
  const options=useCachedResult.mock.calls.at(-1)[0];
  expect(options).toMatchObject({moduleKey:MODULES.stimOptimizer,uid:'synthetic-cache-participant',enabled:true,autoFetch:false,settings:{Sites:['left_leg','back'],Hemispheres:['Left','Right'],WashinMin:1,Backend:'plotly',NBatches:3,Q:4}});
  expect(mockQuery).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Start analysis'}));
  expect(mockCache.recompute).toHaveBeenCalledTimes(1);
  const data={available:true,arms:{},InputManifest:{revision:'clean-v4'}};mockQuery.mockResolvedValueOnce({status:200,data});
  await expect(options.fetcher()).resolves.toBe(data);
  expect(mockQuery).toHaveBeenCalledWith('/api/queryStimOptimizer',{ParticipantId:'synthetic-cache-participant',...options.settings});
});

test('restoring saved biomarker controls does not automatically rebuild missing results',async()=>{
  localStorage.setItem('bravo.biomarkerControls.synthetic-cache-participant',JSON.stringify({schema:'biomarker_controls_v1',metric:'vas',requestParams:{LabelMetric:'vas',MatchToleranceMin:30}}));
  render(<View><Biomarkers/></View>);await act(async()=>{});
  expect(useCachedResult.mock.calls.at(-1)[0]).toMatchObject({enabled:true,autoFetch:false,settings:{LabelMetric:'vas',MatchToleranceMin:30}});
  expect(mockQuery.mock.calls.some(([url])=>url==='/api/queryBiomarkerAnalysis')).toBe(false);expect(mockCache.recompute).not.toHaveBeenCalled();
});
